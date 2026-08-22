"""Apprentice MCP sunucusu: "yerel model isi yapar, buyuk model denetler".

Denetci (Claude Code, Cursor, VS Code... IDE'nin kendi modeli) bu sunucuya stdio MCP ile
baglanir ve TEK araci cagirir:

    worker_run(gorev, kabul_kriterleri, ortam="unity")
      -> {yazilan_dosyalar, derleme_durumu, hatalar, tur_sayisi, sure, ozet, olcumler, oturum}

Isci = Ollama'daki yerel model (Qwen3-Coder-Next). Ortam = arac seti + dogrulayici:
  unity  envs/unity/unity_code.one_request dongusu (write_script + Unity derleyicisi +
         opsiyonel play / play_observe). Sunucu bunu envs/unity/panel_runner.py ile
         AYRIK surecte kosturur - tur dakikalar surer, Unity domain reload yapar,
         heredoc/kacis kazalari yasandi; isci cokse sunucu ayakta kalir.
  fake   envs/fake/fake_runner.py - Unity ve Ollama OLMADAN ayni olay semasini ureten
         duman testi ortami (tests/test_server.py).
  code   envs/code/code_runner.py - genel kod (TASLAK): dosya oku/yaz, shell, test; hapis.

Denetci kabul kriterini yazar (iscinin en zayif yeri). Sunucu kriterleri goreve metin
olarak ekler, isciyi kosturur, DOGRULANMIS sonucu (derleyici) ve HAM olcumleri dondurur;
yorumlama ve "yeter mi" karari denetcide kalir. Olculen sebep: isci kendi olcumune bakip
duzeltmeye kalkinca yakinsamadi (1.15 -> 0.01), olcum ozetlenip verilince 2 turda cozdu.

Stdout MCP kanalidir: iscinin ciktisi oraya ASLA karismaz (DEVNULL + dosya).
Bagimlilik yok (stdlib). Calistirma: python server/apprentice_server.py  (istemci baslatir)
Ev: APPRENTICE_HOME (varsayilan ~/.apprentice) -> jobs/<id>/, sessions/<ortam>/.
"""
from __future__ import annotations
import difflib, json, os, subprocess, sys, threading, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from core import config  # noqa: E402

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "apprentice", "version": "0.2.0"}
HOME = os.environ.get("APPRENTICE_HOME") or os.path.join(os.path.expanduser("~"), ".apprentice")
PYTHON = os.environ.get("APPRENTICE_PYTHON") or sys.executable
# Bir tur 60-300 s; play_observe'lu isler daha uzun. Varsayilan ust sinir 30 dk.
DEFAULT_TIMEOUT_S = float(os.environ.get("APPRENTICE_TIMEOUT_S", "1800"))

# Olcum sayilan araclar: sonuclari ham olarak denetciye tasinir.
MEASURE_TOOLS = {"play_observe", "read_console", "scene_objects", "inspect_object"}

ENVS = {
    "unity": {"runner": os.path.join(ROOT, "envs", "unity", "panel_runner.py"),
              "aciklama": "Unity Editor: write_script/read_script + derleme, opsiyonel play/play_observe. MCP for Unity koprusu gerekir."},
    "fake": {"runner": os.path.join(ROOT, "envs", "fake", "fake_runner.py"),
             "aciklama": "Duman testi: Unity/Ollama olmadan ayni olay semasi."},
    "code": {"runner": os.path.join(ROOT, "envs", "code", "code_runner.py"),
             "aciklama": "Genel kod ortami (TASLAK): read/write_file, list_files, run_shell, run_tests; "
                         "dogrulayici py_compile + pytest. calisma_dizini zorunlu."},
}

PROMPT_TMPL = (
    "{gorev}\n\n"
    "KABUL KRITERLERI (denetci yazdi; bitirmeden once her birini sagladigindan emin ol):\n"
    "{kriterler}\n\n"
    "Kurallar: Basariyi derleyici/dogrulayici belirler, senin beyanin degil. Olcum "
    "gerekiyorsa olc ve SONUCU HAM HALIYLE raporla; yorumlamaya ya da olcum-duzeltme "
    "dongusune girme, sinira gelince dur ve raporla. Nihai mesajinda: ne yazdin, "
    "hangi kriteri nasil sagladin, neyi saglayamadin - kisa ve somut."
)


def _diff_stat(before: str | None, after: str) -> tuple[int, int]:
    b = (before or "").splitlines()
    a = (after or "").splitlines()
    ek = sil = 0
    for line in difflib.unified_diff(b, a, lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            ek += 1
        elif line.startswith("-") and not line.startswith("---"):
            sil += 1
    return ek, sil


# --------------------------------------------------------------------------- is
class Job:
    def __init__(self, ortam: str, gorev: str, kriterler: list, oturum: str,
                 play: bool, onarim: int, model: str, url: str, workdir: str = ""):
        self.workdir = workdir
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.dir = os.path.join(HOME, "jobs", self.id)
        os.makedirs(self.dir, exist_ok=True)
        self.ortam, self.gorev, self.kriterler = ortam, gorev, kriterler
        self.oturum = oturum or self.id
        self.play, self.onarim, self.model, self.url = play, onarim, model, url
        self.t0 = time.time()
        self.proc: subprocess.Popen | None = None
        self.done = False
        self.code: int | None = None

    @property
    def events_path(self):
        return os.path.join(self.dir, "events.jsonl")

    def start(self):
        runner = ENVS[self.ortam]["runner"]
        prompt = PROMPT_TMPL.format(
            gorev=self.gorev.strip(),
            kriterler="\n".join("- " + k.strip() for k in self.kriterler) or "- (verilmedi)")
        pf = os.path.join(self.dir, "prompt.txt")
        with open(pf, "w", encoding="utf-8", newline="\n") as f:
            f.write(prompt)
        with open(os.path.join(self.dir, "job.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"id": self.id, "ortam": self.ortam, "gorev": self.gorev,
                       "kabul_kriterleri": self.kriterler, "oturum": self.oturum,
                       "play": self.play, "model": self.model, "baslangic": self.t0,
                       "calisma_dizini": self.workdir},
                      f, ensure_ascii=False, indent=1)
        sess_dir = os.path.join(HOME, "sessions", self.ortam)
        cmd = [PYTHON, runner, "--jsonl", self.events_path, "--prompt-file", pf,
               "--session", self.oturum, "--session-dir", sess_dir,
               "--model", self.model, "--url", self.url, "--repairs", str(self.onarim)]
        if self.play:
            cmd.append("--play")
        if self.workdir:
            cmd += ["--workdir", self.workdir]
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        self.stderr_f = open(os.path.join(self.dir, "stderr.txt"), "w", encoding="utf-8")
        # stdin/stdout=DEVNULL SART: ikisi de MCP kanali. Olculdu: stdin miras alininca
        # cocuk Windows'ta ilk satirini bile yazmadan takildi (yalniz sunucu icinde).
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL,
                                     stderr=self.stderr_f)
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self):
        self.code = self.proc.wait()
        try:
            self.stderr_f.close()
        except Exception:
            pass
        # Isci 'exit' yazmadan oldüyse olay dosyasini biz kapatalim (izleyiciler icin).
        try:
            ev = self.events()
            if not any(e.get("type") == "exit" for e in ev):
                with open(self.events_path, "a", encoding="utf-8") as f:
                    if not any(e.get("type") in ("result", "error") for e in ev):
                        f.write(json.dumps({"type": "error", "message":
                                            "isci sonuc yazmadan cikti (kod %s)" % self.code},
                                           ensure_ascii=False) + "\n")
                    f.write(json.dumps({"type": "exit", "code": self.code}) + "\n")
        except Exception:
            pass
        self.done = True

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def events(self) -> list:
        out = []
        try:
            with open(self.events_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
        return out

    def report(self) -> dict:
        """Sozlesme: yazilan_dosyalar, derleme_durumu, hatalar, tur_sayisi, sure, ozet (+ek)."""
        ev = self.events()
        rep = {"yazilan_dosyalar": [], "derleme_durumu": "bilinmiyor", "hatalar": [],
               "tur_sayisi": 0, "sure": round(time.time() - self.t0, 1), "ozet": "",
               "olcumler": [], "araclar": [], "play": None,
               "oturum": self.oturum, "is_id": self.id, "ortam": self.ortam,
               "kabul_kriterleri": self.kriterler, "is_klasoru": self.dir,
               "durum": "bitti" if self.done else "calisiyor"}
        got_result = False
        for e in ev:
            t = e.get("type")
            if t == "tool":
                rep["araclar"].append("%s %s" % (e.get("name"), e.get("detail") or ""))
            elif t == "tool_result" and e.get("name") in MEASURE_TOOLS:
                rep["olcumler"].append({"arac": e.get("name"), "sonuc": e.get("text", ""),
                                        "sure_s": e.get("sure")})
            elif t == "write":
                ek, sil = _diff_stat(e.get("before"), e.get("after") or "")
                rep["yazilan_dosyalar"].append({
                    "yol": e.get("path"), "yeni": e.get("before") is None,
                    "eklendi": ek, "silindi": sil,
                    "satir": len((e.get("after") or "").splitlines())})
            elif t == "assistant":
                rep["ozet"] = e.get("text", "")
            elif t == "result":
                got_result = True
                errs = list(e.get("errors") or [])
                rep["hatalar"].extend(errs)
                rep["derleme_durumu"] = "derlendi" if not errs else "derleme_hatasi"
                rep["tur_sayisi"] = int(e.get("rounds", 0)) + 1
                rep["play"] = e.get("play")
                if e.get("play") and e["play"].get("hatalar"):
                    rep["hatalar"].extend("calisma zamani: " + h for h in e["play"]["hatalar"])
            elif t == "error":
                rep["hatalar"].append(e.get("message", ""))
                rep["derleme_durumu"] = "calistirilamadi"
        if self.done and not got_result and rep["derleme_durumu"] == "bilinmiyor":
            rep["derleme_durumu"] = "calistirilamadi"
            rep["hatalar"].append("isci sonuc yazmadan cikti (kod %s); bkz. %s" % (
                self.code, os.path.join(self.dir, "stderr.txt")))
        rep["sure"] = round(time.time() - self.t0, 1)
        # Yazilan dosyalar: ayni yol birden cok kez yazildiysa son hali kalsin, ilk 'yeni' korunsun.
        merged: dict[str, dict] = {}
        for d in rep["yazilan_dosyalar"]:
            if d["yol"] in merged:
                m = merged[d["yol"]]
                m["eklendi"] += d["eklendi"]
                m["silindi"] += d["silindi"]
                m["satir"] = d["satir"]
            else:
                merged[d["yol"]] = dict(d)
        rep["yazilan_dosyalar"] = list(merged.values())
        return rep


JOBS: dict[str, Job] = {}


# ----------------------------------------------------------------------- on kosul
def _precheck(ortam: str) -> str:
    """Isciyi baslatmadan once acik bir sebep varsa onu dondur (bos = sorun yok)."""
    import urllib.request, urllib.error
    if ortam == "fake":
        return ""
    ollama = (config.get("ollama.url") or "http://localhost:11434").rstrip("/")
    model = config.env_or("UNITY_CODE_MODEL", "ollama.model")
    try:
        with urllib.request.urlopen(ollama + "/api/tags", timeout=3) as r:
            names = [m.get("name") for m in json.load(r).get("models", [])]
    except Exception as e:
        return "Ollama'ya ulasilamadi (%s): %s" % (ollama, str(e)[:120])
    if model not in names:
        return "model yuklu degil: %s (ollama pull gerekli; yuklu: %s)" % (model, names)
    if ortam == "unity":
        url = config.env_or("UNITY_MCP_URL", "unity.mcp_url")
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=3)
        except urllib.error.HTTPError as he:
            if he.code not in (400, 405, 406):
                return "Unity MCP koprusu beklenmeyen cevap: HTTP %d" % he.code
        except Exception as e:
            return ("Unity MCP koprusune ulasilamadi (%s): %s - Unity acik ve MCP for Unity "
                    "baglandi mi?" % (url, str(e)[:100]))
    return ""


def tool_worker_run(a: dict) -> dict:
    gorev = str(a.get("gorev") or "").strip()
    if not gorev:
        return {"hata": "gorev bos"}
    kriterler = a.get("kabul_kriterleri") or []
    if isinstance(kriterler, str):
        kriterler = [k for k in kriterler.splitlines() if k.strip()]
    ortam = str(a.get("ortam") or "unity")
    if ortam not in ENVS:
        return {"hata": "bilinmeyen ortam %r; secenekler: %s" % (ortam, list(ENVS))}
    if not ENVS[ortam]["runner"]:
        return {"hata": "ortam %r planli, henuz yok" % ortam}
    workdir = str(a.get("calisma_dizini") or "")
    if ortam == "code":
        if not workdir or not os.path.isdir(workdir):
            return {"hata": "ortam 'code' icin calisma_dizini (var olan klasor) zorunlu: %r" % workdir}
        workdir = os.path.realpath(workdir)
    sebep = _precheck(ortam)
    if sebep:
        return {"hata": sebep, "derleme_durumu": "calistirilamadi", "yazilan_dosyalar": [],
                "hatalar": [sebep], "tur_sayisi": 0, "sure": 0.0, "ozet": ""}
    job = Job(ortam, gorev, [str(k) for k in kriterler], str(a.get("oturum") or ""),
              bool(a.get("play", False)),
              int(a.get("onarim", config.get("onarim.compile_rounds", 3))),
              config.env_or("UNITY_CODE_MODEL", "ollama.model"),
              config.env_or("UNITY_MCP_URL", "unity.mcp_url"), workdir)
    JOBS[job.id] = job
    job.start()
    limit = float(a.get("zaman_asimi_s") or DEFAULT_TIMEOUT_S)
    while not job.done and time.time() - job.t0 < limit:
        time.sleep(0.5)
    rep = job.report()
    if not job.done:
        job.kill()
        msg = "zaman asimi (%.0f s): isci durduruldu; olaylar %s" % (limit, job.events_path)
        rep["derleme_durumu"] = "zaman_asimi"
        rep["hatalar"].append(msg)
        # Olay dosyasini kapat ki izleyiciler (clients/web) isi sonsuza kadar "calisiyor" gormesin.
        try:
            with open(job.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"type": "error", "message": msg}, ensure_ascii=False) + "\n")
                f.write(json.dumps({"type": "exit", "code": -9}) + "\n")
        except Exception:
            pass
    return rep


TOOLS = [
    {"name": "worker_run",
     "description": (
         "Yerel isci modele (Ollama, Qwen3-Coder-Next) bir gorev yaptirir ve DOGRULANMIS "
         "sonucu dondurur. Sen denetcisin: gorevi ve KABUL KRITERLERINI sen yazarsin "
         "(somut, olculebilir; isci kriter uretmekte zayif). Donus: yazilan_dosyalar "
         "(+/- satir), derleme_durumu (derlendi | derleme_hatasi | calistirilamadi | "
         "zaman_asimi), hatalar, tur_sayisi, sure, ozet (iscinin kendi anlatimi), olcumler "
         "(play_observe vb. HAM ciktilar), oturum. 'derlendi' yalnizca derleyici onayidir; "
         "kriterlerin saglanip saglanmadigina olcumlere bakarak SEN karar verirsin, "
         "olcumu ozetleyip ayni 'oturum' ile duzeltme istetirsin (baglam korunur). "
         "Bir tur 60-300 s surer, play ile daha uzun; istemci arac zaman asimini buna gore ayarla."),
     "inputSchema": {
         "type": "object",
         "properties": {
             "gorev": {"type": "string", "description": "Ne yapilacak, duz dille. Dosya/obje adlarini ver."},
             "kabul_kriterleri": {"type": "array", "items": {"type": "string"},
                                  "description": "Denetcinin yazdigi somut kriterler, her biri tek cumle."},
             "ortam": {"type": "string", "enum": list(ENVS), "default": "unity"},
             "calisma_dizini": {"type": "string", "description": "code ortami icin zorunlu: iscinin hapsedildigi klasor (mutlak yol)."},
             "oturum": {"type": "string", "description": "Onceki worker_run'in 'oturum' degeri: isci ayni baglamla devam eder. Bos = yeni oturum."},
             "play": {"type": "boolean", "default": False,
                      "description": "unity: derlemeden sonra play moda girip calisma zamani hatasi ara."},
             "onarim": {"type": "integer", "default": 3, "description": "Azami derleme onarim turu."},
             "zaman_asimi_s": {"type": "number", "default": DEFAULT_TIMEOUT_S},
         },
         "required": ["gorev", "kabul_kriterleri"],
     }},
]
HANDLERS = {"worker_run": tool_worker_run}


# ------------------------------------------------------------------ JSON-RPC/stdio
_lock = threading.Lock()


def _send(obj: dict):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    with _lock:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def _log(msg: str):
    sys.stderr.write("[apprentice] %s\n" % msg)
    sys.stderr.flush()


def handle(req: dict) -> dict | None:
    m, rid, p = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": p.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}}
    if m in ("notifications/initialized", "notifications/cancelled"):
        return None
    if m == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if m == "tools/call":
        name = p.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": "bilinmeyen arac %r" % name}}
        try:
            out = fn(p.get("arguments") or {})
        except Exception as e:  # noqa: BLE001
            out = {"hata": "%s: %s" % (type(e).__name__, e)}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}],
            "structuredContent": out,
            "isError": bool(isinstance(out, dict) and out.get("hata"))}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "yok: %s" % m}}


def serve():
    os.makedirs(HOME, exist_ok=True)
    _log("hazir; ev=%s ayar=%s" % (HOME, config.source()))
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue

        def run(r=req):
            resp = handle(r)
            if resp is not None:
                _send(resp)
        # Uzun suren tools/call, ping gibi istekleri bloklamasin.
        if req.get("method") == "tools/call":
            threading.Thread(target=run, daemon=True).start()
        else:
            run()
    for j in JOBS.values():
        j.kill()


if __name__ == "__main__":
    serve()

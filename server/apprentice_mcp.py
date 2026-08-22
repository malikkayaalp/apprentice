"""Apprentice MCP sunucusu: "yerel model isi yapar, buyuk model denetler".

Denetci (Claude Code, Cursor, VS Code... IDE'nin kendi modeli) bu sunucuya stdio
MCP ile baglanir ve TEK is araci cagirir:

    worker_run(gorev, kabul_kriterleri, ortam) -> {ok, dosyalar, derleme, olcumler, ozet}

Isci = Ollama'daki yerel model (Qwen3-Coder-Next). Ortam = arac seti + dogrulayici
(unity: derleme + play + play_observe; code: planli). Denetci kabul kriterini yazar
(iscinin en zayif yeri), sunucu isciyi kosturur, DOGRULANMIS sonucu ve HAM olcumleri
geri verir; yorumlama ve "yeter mi" karari denetcide kalir. Olculen sebep: isci
kendi olcumune bakip duzeltmeye kalkinca yakinsamadi (1.15 -> 0.01), ayni olcum
ozetlenip verilince 2 turda cozdu.

Neden ayrik surec: isci turu dakikalar surer, Unity domain reload yapar, heredoc/
kacis kazalari yasandi. Her is `envs/<ortam>/panel_runner.py` olarak ayri surecte
kosar, olaylarini JSONL'e yazar; sunucu o dosyadan rapor cikarir. Stdout MCP
kanalidir - iscinin ciktisi oraya ASLA karismaz (DEVNULL + dosya).

Bagimlilik yok: stdlib. Calistirma:
    python server/apprentice_mcp.py            (stdio; istemci baslatir)
Ev: APPRENTICE_HOME (varsayilan ~/.apprentice) -> jobs/<id>/, sessions/<ortam>/.
"""
from __future__ import annotations
import difflib, json, os, subprocess, sys, threading, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from core import config  # noqa: E402

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "apprentice", "version": "0.1.0"}
HOME = os.environ.get("APPRENTICE_HOME") or os.path.join(os.path.expanduser("~"), ".apprentice")
PYTHON = os.environ.get("APPRENTICE_PYTHON") or sys.executable

# Olcum sayilan araclar: sonuclari ham olarak denetciye tasinir.
MEASURE_TOOLS = {"play_observe", "read_console", "scene_objects", "inspect_object"}

ENVS = {
    "unity": {
        "runner": os.path.join(ROOT, "envs", "unity", "panel_runner.py"),
        "aciklama": "Unity Editor: write_script/read_script + derleme dogrulamasi, "
                    "opsiyonel play ve play_observe. MCP for Unity koprusu gerekir.",
    },
    "code": {
        "runner": None,
        "aciklama": "Genel kod ortami (dosya, shell, test, git) - PLANLI, henuz yok.",
    },
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


# --------------------------------------------------------------------------- is
class Job:
    def __init__(self, ortam: str, gorev: str, kriterler: list, oturum: str,
                 play: bool, onarim: int, model: str, url: str):
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
        self.err = ""

    @property
    def events_path(self):
        return os.path.join(self.dir, "events.jsonl")

    def start(self):
        runner = ENVS[self.ortam]["runner"]
        prompt = PROMPT_TMPL.format(
            gorev=self.gorev.strip(),
            kriterler="\n".join("- " + k.strip() for k in self.kriterler) or "- (verilmedi)")
        pf = os.path.join(self.dir, "prompt.txt")
        with open(pf, "w", encoding="utf-8") as f:
            f.write(prompt)
        with open(os.path.join(self.dir, "job.json"), "w", encoding="utf-8") as f:
            json.dump({"id": self.id, "ortam": self.ortam, "gorev": self.gorev,
                       "kabul_kriterleri": self.kriterler, "oturum": self.oturum,
                       "play": self.play, "model": self.model, "baslangic": self.t0},
                      f, ensure_ascii=False, indent=1)
        sess_dir = os.path.join(HOME, "sessions", self.ortam)
        cmd = [PYTHON, runner, "--jsonl", self.events_path, "--prompt-file", pf,
               "--session", self.oturum, "--session-dir", sess_dir,
               "--model", self.model, "--url", self.url, "--repairs", str(self.onarim)]
        if self.play:
            cmd.append("--play")
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        self.stderr_f = open(os.path.join(self.dir, "stderr.txt"), "w", encoding="utf-8")
        # stdout=DEVNULL sart: MCP kanali bizim stdout'umuz, iscininki oraya akmamali.
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                     stderr=self.stderr_f)
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self):
        self.code = self.proc.wait()
        try:
            self.stderr_f.close()
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

    def report(self, olaylar: bool = False) -> dict:
        ev = self.events()
        rep = {"is_id": self.id, "ortam": self.ortam, "oturum": self.oturum,
               "durum": "bitti" if self.done else "calisiyor",
               "sure_s": round(time.time() - self.t0, 1),
               "kabul_kriterleri": self.kriterler,
               "ok": None, "ozet": "", "derleme": None, "play": None,
               "dosyalar": [], "olcumler": [], "araclar": [], "hata": self.err or ""}
        for e in ev:
            t = e.get("type")
            if t == "tool":
                rep["araclar"].append("%s %s" % (e.get("name"), e.get("detail") or ""))
            elif t == "tool_result" and e.get("name") in MEASURE_TOOLS:
                rep["olcumler"].append({"arac": e.get("name"), "sonuc": e.get("text", ""),
                                        "sure_s": e.get("sure")})
            elif t == "write":
                b = (e.get("before") or "").splitlines()
                a = (e.get("after") or "").splitlines()
                ek = sil = 0
                for line in difflib.unified_diff(b, a, lineterm="", n=0):
                    if line.startswith("+") and not line.startswith("+++"):
                        ek += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        sil += 1
                rep["dosyalar"].append({"yol": e.get("path"), "yeni": e.get("before") is None,
                                        "eklendi": ek, "silindi": sil, "satir": len(a)})
            elif t == "assistant":
                rep["ozet"] = e.get("text", "")
            elif t == "result":
                rep["ok"] = bool(e.get("ok"))
                rep["derleme"] = {"hatalar": e.get("errors", []), "onarim_turu": e.get("rounds", 0),
                                  "isci_suresi_s": e.get("wall")}
                rep["play"] = e.get("play")
            elif t == "error":
                rep["hata"] = e.get("message", "")
        if self.done and rep["ok"] is None and not rep["hata"]:
            rep["hata"] = "isci sonuc yazmadan cikti (kod %s); bkz. %s" % (
                self.code, os.path.join(self.dir, "stderr.txt"))
            rep["ok"] = False
        if olaylar:
            rep["olaylar"] = ev
        rep["is_klasoru"] = self.dir
        return rep


JOBS: dict[str, Job] = {}


# ----------------------------------------------------------------------- araclar
def _env_check() -> dict:
    import urllib.request
    out = {"python": sys.version.split()[0], "ev": HOME, "ayar_kaynagi": config.source(),
           "model": config.env_or("UNITY_CODE_MODEL", "ollama.model"), "ortamlar": {}}
    ollama = (config.get("ollama.url") or "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(ollama + "/api/tags", timeout=3) as r:
            names = [m.get("name") for m in json.load(r).get("models", [])]
        out["ollama"] = {"url": ollama, "acik": True, "model_yuklu": out["model"] in names,
                         "modeller": names}
    except Exception as e:
        out["ollama"] = {"url": ollama, "acik": False, "hata": str(e)[:120]}
    for ad, e in ENVS.items():
        d = {"aciklama": e["aciklama"], "hazir": bool(e["runner"] and os.path.exists(e["runner"]))}
        if ad == "unity" and d["hazir"]:
            url = config.env_or("UNITY_MCP_URL", "unity.mcp_url")
            try:
                req = urllib.request.Request(url, method="GET")
                urllib.request.urlopen(req, timeout=3)
                d["kopru"] = "acik"
            except urllib.error.HTTPError as he:
                d["kopru"] = "acik" if he.code in (405, 406, 400) else "HTTP %d" % he.code
            except Exception as ex:
                d["kopru"] = "kapali (%s)" % str(ex)[:80]
                d["hazir"] = False
            d["mcp_url"] = url
        out["ortamlar"][ad] = d
    return out


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
    job = Job(ortam, gorev, [str(k) for k in kriterler], str(a.get("oturum") or ""),
              bool(a.get("play", False)), int(a.get("onarim", config.get("onarim.compile_rounds", 3))),
              config.env_or("UNITY_CODE_MODEL", "ollama.model"),
              config.env_or("UNITY_MCP_URL", "unity.mcp_url"))
    JOBS[job.id] = job
    job.start()
    if not a.get("bekle", True):
        return job.report()
    limit = float(a.get("zaman_asimi_s", 1500))
    while not job.done and time.time() - job.t0 < limit:
        time.sleep(1.0)
    if not job.done:
        rep = job.report()
        rep["hata"] = ("zaman asimi (%.0f s): isci hala calisiyor; worker_status('%s') "
                       "ile sonra sor" % (limit, job.id))
        return rep
    return job.report()


def tool_worker_status(a: dict) -> dict:
    jid = str(a.get("is_id") or "")
    job = JOBS.get(jid)
    if job is None:
        return {"hata": "bilinmeyen is_id %r (bu surecte baslatilan isler: %s)" % (jid, list(JOBS))}
    if a.get("durdur"):
        job.kill()
    return job.report(bool(a.get("olaylar", False)))


TOOLS = [
    {"name": "worker_run",
     "description": (
         "Yerel isci modele (Ollama, Qwen3-Coder-Next) bir gorev yaptirir ve DOGRULANMIS "
         "sonucu dondurur. Sen denetcisin: gorevi ve KABUL KRITERLERINI sen yazarsin "
         "(somut, olculebilir; isci kriter uretmekte zayif). Donen raporda derleme sonucu, "
         "yazilan dosyalar (+/- satir), ham olcumler (play_observe vb.) ve iscinin ozeti "
         "var; 'ok' yalnizca derleyici/dogrulayici onayidir, kriterlerin saglanip "
         "saglanmadigina SEN karar verirsin. Olcumleri sen ozetleyip yeni bir worker_run "
         "ile (ayni 'oturum' degeriyle, baglam korunur) duzeltme istetebilirsin. "
         "Dakikalar surebilir; istemci zaman asimi kisaysa bekle=false verip "
         "worker_status ile sor."),
     "inputSchema": {
         "type": "object",
         "properties": {
             "gorev": {"type": "string", "description": "Ne yapilacak, duz dille. Dosya/obje adlarini ver."},
             "kabul_kriterleri": {"type": "array", "items": {"type": "string"},
                                  "description": "Denetcinin yazdigi somut kriterler, her biri tek cumle."},
             "ortam": {"type": "string", "enum": list(ENVS), "default": "unity"},
             "oturum": {"type": "string", "description": "Onceki bir worker_run'in 'oturum' degeri: isci ayni baglamla devam eder. Bos = yeni oturum."},
             "play": {"type": "boolean", "default": False,
                      "description": "unity: derlemeden sonra play moda girip calisma zamani hatasi ara."},
             "onarim": {"type": "integer", "default": 3, "description": "Azami derleme onarim turu."},
             "bekle": {"type": "boolean", "default": True, "description": "false: hemen is_id dondur, worker_status ile sor."},
             "zaman_asimi_s": {"type": "number", "default": 1500},
         },
         "required": ["gorev", "kabul_kriterleri"],
     }},
    {"name": "worker_status",
     "description": "Bir worker_run isinin su anki raporu (calisiyor/bitti). olaylar=true ile ham olay akisi; durdur=true ile isi oldurur.",
     "inputSchema": {"type": "object",
                     "properties": {"is_id": {"type": "string"},
                                    "olaylar": {"type": "boolean", "default": False},
                                    "durdur": {"type": "boolean", "default": False}},
                     "required": ["is_id"]}},
    {"name": "worker_env",
     "description": "Iscinin hazirligi: Ollama acik mi, model yuklu mu, hangi ortamlar hazir (unity koprusu vb.). Ilk worker_run'dan once cagir.",
     "inputSchema": {"type": "object", "properties": {}}},
]

HANDLERS = {"worker_run": tool_worker_run, "worker_status": tool_worker_status,
            "worker_env": lambda a: _env_check()}


# ------------------------------------------------------------------ JSON-RPC/stdio
def _send(obj: dict):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
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
            "isError": bool(isinstance(out, dict) and out.get("hata") and out.get("ok") is None)}}
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
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "parse error"}})
            continue
        # Uzun suren tools/call diger istekleri (ping) bloklamasin diye is parcasinda.
        def run(r=req):
            resp = handle(r)
            if resp is not None:
                with _lock:
                    _send(resp)
        if req.get("method") == "tools/call":
            threading.Thread(target=run, daemon=True).start()
        else:
            run()
    for j in JOBS.values():
        j.kill()


_lock = threading.Lock()

if __name__ == "__main__":
    serve()

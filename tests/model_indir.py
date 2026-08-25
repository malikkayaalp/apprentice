"""MODEL INDIRME + ILK HIZ OLCUMU (gozetimsiz).

    python tests/model_indir.py [--bekle-pid 14180] [--model a,b]

NEDEN AYRI GOREV: gece kusatmasi kosarken indirmek disk G/C'sini paylasir ve kampanyanin
SURE olcumlerini kirletir - kampanyanin butun degeri o sureler. Bu betik once kusatmanin
bitmesini BEKLER, sonra indirir.

DFLASH NEDIR: Muse-Glimmer'in taslak modeli (speculative decoding drafter). Kucuk model
token BLOKLARI onerir (blok-difuzyon, tek gecişte 16 token), ana model paralel dogrular;
kabul edilen token'lar aynen kalir. Cikti dagilimi DEGISMEZ - yalniz hiz. Model karti
RTX-5090'da ~3.1x olcmus; BIZIM donanimda ne oldugunu ANCAK OLCEREK biliriz:
  - 15.9 GB VRAM'de 20 GB'lik paket tam sigmaz, katman paylasimi olur
  - speculative decoding'in kazanci dogrulayicinin hizina baglidir; model kismen CPU'daysa
    kazanc bambaska cikabilir (daha az ya da daha cok)

Bu betik indirdikten sonra HER modele AYNI istemi verip tok/sn olcer. Karar o sayiyla
verilir, model kartindaki baska bir donanimin sayisiyla degil.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(ROOT, "reports")
PZ = 0x08000000 if os.name == "nt" else 0
OLLAMA = "http://localhost:11434"

# (etiket, aciklama) - dflash'li ve dflash'siz AYNI nicemleme: fark yalniz taslak model.
# Boylece "dflash ise yariyor mu" sorusu tek degiskenli olcume doner.
VARSAYILAN = [
    ("muse-glimmer:30b-q4_K_M-dflash", "Muse-Glimmer 30B Q4_K_M + DFlash taslak modeli"),
    ("muse-glimmer:30b-q4_K_M", "ayni model, taslak modelsiz (A/B karsilastirmasi)"),
]


def _log(m: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def _surec_var(pid: int) -> bool:
    if not pid:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        if os.name == "nt":
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            h = k32.OpenProcess(0x1000, False, int(pid))
            if not h:
                return False
            try:
                kod = wintypes.DWORD()
                return bool(k32.GetExitCodeProcess(h, ctypes.byref(kod))) and kod.value == 259
            finally:
                k32.CloseHandle(h)
        os.kill(int(pid), 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _kusatma_pid() -> int:
    """Kosan gece_kusatmasi surecini bul (pid verilmediyse)."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                            "Where-Object { $_.CommandLine -like '*gece_kusatmasi*' } | "
                            "Select-Object -ExpandProperty ProcessId"],
                           capture_output=True, text=True, timeout=60, creationflags=PZ)
        for s in (r.stdout or "").split():
            if s.strip().isdigit():
                return int(s)
    except Exception:  # noqa: BLE001
        pass
    return 0


def _tags() -> set:
    try:
        d = json.load(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=20))
        return {m.get("name", "") for m in d.get("models", [])}
    except Exception:  # noqa: BLE001
        return set()


def indir(etiket: str, zaman_asimi: int = 7200) -> dict:
    """ollama pull. Cikti diske akar - ilerleme sabah gorulebilsin."""
    ham = os.path.join(CIKTI, "indir_%s.log" % etiket.replace(":", "_").replace("/", "_"))
    t0 = time.time()
    try:
        with open(ham, "w", encoding="utf-8") as f:
            r = subprocess.run(["ollama", "pull", etiket], stdout=f, stderr=subprocess.STDOUT,
                               timeout=zaman_asimi, creationflags=PZ)
        return {"etiket": etiket, "cikis": r.returncode, "sure": round(time.time() - t0, 1),
                "ham": ham}
    except subprocess.TimeoutExpired:
        return {"etiket": etiket, "cikis": -1, "hata": "zaman asimi", "sure": zaman_asimi,
                "ham": ham}
    except FileNotFoundError:
        return {"etiket": etiket, "cikis": -2, "hata": "ollama komutu bulunamadi", "sure": 0,
                "ham": ham}
    except Exception as e:  # noqa: BLE001
        return {"etiket": etiket, "cikis": -3, "hata": str(e)[:200],
                "sure": round(time.time() - t0, 1), "ham": ham}


ISTEM = ("Write a Python function `lru_cache_get(cache, key)` that implements an LRU cache "
         "lookup with move-to-front behaviour. Include a short docstring. Code only.")


def hiz_olc(etiket: str, tekrar: int = 2) -> dict:
    """AYNI istem, sabit tohum, temperature 0: uretim hizi (tok/sn).

    Ollama'nin kendi sayaclarini kullaniriz (eval_count / eval_duration) - duvar saati
    yukleme suresini de icerir ve yaniltir. Ilk cagri MODELI YUKLER, o yuzden atilir."""
    olcumler = []
    govde = {"model": etiket, "prompt": ISTEM, "stream": False,
             "options": {"temperature": 0, "seed": 7, "num_predict": 256}}
    for i in range(tekrar + 1):                       # +1: isinma
        try:
            istek = urllib.request.Request(OLLAMA + "/api/generate",
                                           json.dumps(govde).encode(),
                                           {"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(istek, timeout=900))
        except Exception as e:  # noqa: BLE001
            return {"etiket": etiket, "hata": str(e)[:200]}
        if i == 0:
            continue                                   # isinma atilir
        ev_n, ev_sn = d.get("eval_count") or 0, (d.get("eval_duration") or 0) / 1e9
        pr_n, pr_sn = d.get("prompt_eval_count") or 0, (d.get("prompt_eval_duration") or 0) / 1e9
        olcumler.append({
            "uretim_tok": ev_n, "uretim_sn": round(ev_sn, 2),
            "uretim_tok_sn": round(ev_n / ev_sn, 1) if ev_sn else 0,
            "prefill_tok": pr_n,
            "prefill_tok_sn": round(pr_n / pr_sn, 1) if pr_sn else 0,
            "toplam_sn": round((d.get("total_duration") or 0) / 1e9, 2),
        })
    if not olcumler:
        return {"etiket": etiket, "hata": "olcum alinamadi"}
    en_iyi = max(olcumler, key=lambda x: x["uretim_tok_sn"])
    return {"etiket": etiket, "olcumler": olcumler, "en_iyi": en_iyi}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bekle-pid", type=int, default=0)
    ap.add_argument("--model", default="")
    ap.add_argument("--bekleme-siniri", type=int, default=21600, help="en fazla bekleme (sn)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(CIKTI, exist_ok=True)

    hedefler = ([(x.strip(), "") for x in a.model.split(",") if x.strip()]
                if a.model else VARSAYILAN)

    pid = getattr(a, "bekle_pid", 0) or _kusatma_pid()
    if pid:
        _log("gece kusatmasi kosuyor (PID %d) - bitmesini bekliyorum" % pid)
        t0 = time.time()
        while _surec_var(pid) and time.time() - t0 < a.bekleme_siniri:
            time.sleep(30)
        _log("kusatma bitti (ya da bekleme siniri doldu) - %.0f dk beklendi"
             % ((time.time() - t0) / 60))
    else:
        _log("kosan kusatma yok - dogrudan basliyorum")

    varolan = _tags()
    sonuc = {"indirmeler": [], "hizlar": []}
    for etiket, aciklama in hedefler:
        if etiket in varolan:
            _log("%s zaten var - indirme atlandi" % etiket)
            sonuc["indirmeler"].append({"etiket": etiket, "cikis": 0, "sure": 0,
                                        "not": "zaten vardi"})
            continue
        _log("indiriliyor: %s  (%s)" % (etiket, aciklama))
        r = indir(etiket)
        sonuc["indirmeler"].append(r)
        _log("  -> %s (%.0f dk)" % ("TAMAM" if r["cikis"] == 0 else
                                    "BASARISIZ: %s" % r.get("hata", r["cikis"]), r["sure"] / 60))

    varolan = _tags()
    for etiket, _ in hedefler:
        if etiket not in varolan:
            _log("%s yok - hiz olcumu atlandi" % etiket)
            continue
        _log("hiz olcumu: %s" % etiket)
        h = hiz_olc(etiket)
        sonuc["hizlar"].append(h)
        if h.get("en_iyi"):
            _log("  -> uretim %.1f tok/sn · prefill %.1f tok/sn"
                 % (h["en_iyi"]["uretim_tok_sn"], h["en_iyi"]["prefill_tok_sn"]))
        else:
            _log("  -> olculemedi: %s" % h.get("hata"))

    yol = os.path.join(CIKTI, "model_indirme.json")
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=1)
    _log("bitti - %s" % yol)

    hizlar = [h for h in sonuc["hizlar"] if h.get("en_iyi")]
    if len(hizlar) >= 2:
        a_, b_ = hizlar[0], hizlar[1]
        oran = (a_["en_iyi"]["uretim_tok_sn"] / b_["en_iyi"]["uretim_tok_sn"]
                if b_["en_iyi"]["uretim_tok_sn"] else 0)
        _log("DFLASH KARSILASTIRMASI: %s %.1f tok/sn  vs  %s %.1f tok/sn  ->  %.2fx"
             % (a_["etiket"], a_["en_iyi"]["uretim_tok_sn"],
                b_["etiket"], b_["en_iyi"]["uretim_tok_sn"], oran))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""OLCUM TURU: orneklem buyutme + MODEL KIYASI (gozetimsiz).

    python tests/olcum_turu.py [--model a,b] [--kampanya code,zorluk]

NEDEN: telemetri "orneklem KUCUK (19 is)" diye uyariyor ve karar vermek icin 20-30 gercek
is istiyor. Ayrica Muse-Glimmer'in HIZINI olctuk (dflash 2.42x) ama KALITESINI hic
olcmedik - hiz karari tek basina yaniltir.

Bu betik ayni kampanyalari her model icin kosturur. Kiyas tek degiskenli: ayni gorevler,
ayni gizli kontroller, ayni kabul denetimi; degisen yalniz model.

Sonuclar arsive gider (core/olcum.py) - ustune YAZILMAZ, birikir.
"""
from __future__ import annotations
import argparse, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
CIKTI = os.path.join(ROOT, "reports")
PZ = 0x08000000 if os.name == "nt" else 0
SAMPIYON = "hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_XL"


def _log(m: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def _bellegi_bosalt() -> None:
    """Model degistirmeden ONCE oncekini indir: 56 GB + 20 GB ayni anda bellekte kalmasin
    ve olcum bellek baskisi altinda yapilmasin."""
    try:
        import json
        import urllib.request
        d = json.load(urllib.request.urlopen("http://localhost:11434/api/ps", timeout=20))
        for m in d.get("models", []):
            istek = urllib.request.Request(
                "http://localhost:11434/api/generate",
                json.dumps({"model": m.get("name"), "keep_alive": 0}).encode(),
                {"Content-Type": "application/json"})
            urllib.request.urlopen(istek, timeout=120).read()
        if d.get("models"):
            time.sleep(4)
    except Exception:  # noqa: BLE001
        pass


def kos(kampanya: str, model: str, sinir: int) -> dict:
    ad = "%s_%s" % (kampanya, "".join(c for c in model.split("/")[-1] if c.isalnum())[:16])
    ham = os.path.join(CIKTI, "tur_%s.log" % ad)
    ev = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
              APPRENTICE_MODEL=model)
    t0 = time.time()
    try:
        with open(ham, "w", encoding="utf-8") as f:
            r = subprocess.run([sys.executable, "tests/%s_kampanya.py" % kampanya, "--tur", "2"],
                               cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                               timeout=sinir, env=ev, creationflags=PZ)
        kod = r.returncode
        hata = ""
    except subprocess.TimeoutExpired:
        kod, hata = -1, "zaman asimi"
    except Exception as e:  # noqa: BLE001
        kod, hata = -2, str(e)[:150]
    return {"kampanya": kampanya, "model": model, "cikis": kod, "hata": hata,
            "sure": round(time.time() - t0, 1), "ham": ham}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=SAMPIYON + ",muse-glimmer:30b-q4_K_M-dflash")
    ap.add_argument("--kampanya", default="code,zorluk")
    ap.add_argument("--sinir", type=int, default=3600, help="kampanya basina sn")
    a = ap.parse_args()
    os.makedirs(CIKTI, exist_ok=True)
    modeller = [x.strip() for x in a.model.split(",") if x.strip()]
    kampanyalar = [x.strip() for x in a.kampanya.split(",") if x.strip()]

    t0 = time.time()
    _log("OLCUM TURU: %d model x %d kampanya" % (len(modeller), len(kampanyalar)))
    sonuclar = []
    for model in modeller:
        _bellegi_bosalt()
        for k in kampanyalar:
            _log("-> %s / %s" % (k, model.split("/")[-1][:36]))
            r = kos(k, model, a.sinir)
            sonuclar.append(r)
            _log("<- %s (%.0f dk)" % ("TAMAM" if r["cikis"] == 0 else
                                      "BASARISIZ %s" % (r["hata"] or r["cikis"]), r["sure"] / 60))

    _log("--- TUR BITTI (%.0f dk) ---" % ((time.time() - t0) / 60))
    try:
        from core.telemetri import yazdir
        yazdir(os.path.join(ROOT, ".apprentice_test_home", "jobs"), 500)
    except Exception as e:  # noqa: BLE001
        _log("telemetri okunamadi: %s" % str(e)[:120])
    for r in sonuclar:
        if r["cikis"] != 0:
            _log("BASARISIZ: %s / %s -> %s" % (r["kampanya"], r["model"][:30],
                                               r["hata"] or r["cikis"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

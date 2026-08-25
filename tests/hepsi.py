"""Butun birim/sozlesme testlerini kosar (model GEREKTIRMEZ).

    python tests/hepsi.py [--hizli]

Kampanyalar (code_kampanya, zorluk_kampanya, *_ab) BURADA KOSMAZ - onlar Ollama ister ve
dakikalar surer; gece kusatmasinda ayri asama olarak kosarlar.
"""
from __future__ import annotations
import argparse, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Sira: hizlidan yavasa. Pencere acan (GUI) testler EN SONDA - gozetimsiz kosuda
# odagi calmasinlar diye.
TESTLER = [
    "test_server.py", "test_inceleme.py", "test_geri_al.py", "test_telemetri.py",
    "test_harita.py", "test_rag.py", "test_code_env.py", "test_tani.py",
    "test_ozellik.py", "test_senaryo.py", "test_panel.py", "test_izle.py",
    "test_kurulum_gui.py",
]
GUI = {"test_izle.py", "test_kurulum_gui.py"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hizli", action="store_true", help="pencere acan testleri atla")
    a = ap.parse_args()
    ev = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    kalan, gecen, atlanan = [], 0, 0
    for ad in TESTLER:
        yol = os.path.join(ROOT, "tests", ad)
        if not os.path.isfile(yol):
            print("%-24s YOK (atlandi)" % ad)
            atlanan += 1
            continue
        if a.hizli and ad in GUI:
            print("%-24s atlandi (--hizli)" % ad)
            atlanan += 1
            continue
        t0 = time.time()
        r = subprocess.run([sys.executable, yol], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ev,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        sure = time.time() - t0
        if r.returncode == 0:
            n = (r.stdout or "").count(": ok")
            print("%-24s GECTI  (%2d kontrol, %.0f sn)" % (ad, n, sure))
            gecen += 1
        else:
            print("%-24s KALDI  (%.0f sn)" % (ad, sure))
            son = [s for s in ((r.stdout or "") + (r.stderr or "")).splitlines() if s.strip()]
            for s in son[-6:]:
                print("      " + s[:150])
            kalan.append(ad)
    print("")
    print("SONUC: %d gecti, %d kaldi, %d atlandi" % (gecen, len(kalan), atlanan))
    if kalan:
        print("KALANLAR: %s" % ", ".join(kalan))
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())

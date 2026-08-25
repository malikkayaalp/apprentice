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
    "test_olcum_arsiv.py", "test_orkestra.py", "test_harita.py", "test_rag.py", "test_code_env.py", "test_tani.py",
    "test_ozellik.py", "test_senaryo.py", "test_panel.py", "test_izle.py",
    "test_kurulum_gui.py",
]
GUI = {"test_izle.py", "test_kurulum_gui.py"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hizli", action="store_true", help="pencere acan testleri atla")
    a = ap.parse_args()
    ev = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    kalan, kararsiz, gecen, atlanan = [], [], 0, 0
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
        def _kos():
            t = time.time()
            rr = subprocess.run([sys.executable, yol], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=ev,
                                creationflags=0x08000000 if os.name == "nt" else 0)
            return rr, time.time() - t

        r, sure = _kos()
        if r.returncode == 0:
            n = (r.stdout or "").count(": ok")
            print("%-24s GECTI  (%2d kontrol, %.0f sn)" % (ad, n, sure))
            gecen += 1
        else:
            # KARARSIZ mi BOZUK mu? Gozetimsiz kosuda en cok bu ayrim lazim. Bir kez daha
            # denenir: ikinci kosuda geciyorsa test KARARSIZ demektir - "gecti" saymayiz,
            # ayri raporlariz. (Yasandi: test_rag bir kez kaldi, ardindan iki kez gecti;
            # sebebi bulunamadi - kampanya yeni bitmisken kaynak cekismesi olabilir.)
            ilk_cikti = ((r.stdout or "") + (r.stderr or ""))
            r2, sure2 = _kos()
            if r2.returncode == 0:
                print("%-24s KARARSIZ (1. kosu KALDI, 2. kosu gecti; %.0f+%.0f sn)"
                      % (ad, sure, sure2))
                for x in [y for y in ilk_cikti.splitlines() if y.strip()][-4:]:
                    print("      1. kosu: " + x[:140])
                kararsiz.append(ad)
            else:
                print("%-24s KALDI  (iki kosuda da; %.0f+%.0f sn)" % (ad, sure, sure2))
                son = [y for y in ((r2.stdout or "") + (r2.stderr or "")).splitlines() if y.strip()]
                for y in son[-6:]:
                    print("      " + y[:150])
                kalan.append(ad)
    print("")
    print("SONUC: %d gecti, %d kaldi, %d KARARSIZ, %d atlandi"
          % (gecen, len(kalan), len(kararsiz), atlanan))
    if kalan:
        print("KALANLAR: %s" % ", ".join(kalan))
    if kararsiz:
        # Kararsiz test BASARI SAYILMAZ: ya testte ya sistemde bir yaris/kaynak sorunu var.
        print("KARARSIZ: %s  (ikinci kosuda gecti - sebebi arastirilmali)" % ", ".join(kararsiz))
    return 1 if (kalan or kararsiz) else 0


if __name__ == "__main__":
    sys.exit(main())

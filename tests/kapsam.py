"""KAPSAM OLCUMU: testler cekirdek modullerin NE KADARINI gercekten kosuyor?

    python tests/kapsam.py

Isim taramasi ("fonksiyon adi testte geciyor mu") YANILTIR: bir fonksiyon testte adiyla
gecmeden de kosabilir (baska fonksiyon cagirir) ya da adiyla gecip HIC kosmayabilir
(yalniz dizge icinde). Bu yuzden stdlib `trace` ile GERCEKTEN calisan satirlar sayilir.

Ek paket YOK - `trace` standart kutuphanede. Kampanyalar kosmaz (Ollama ister).
"""
from __future__ import annotations
import io, os, re, runpy, sys, trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
sys.path.insert(0, os.path.join(ROOT, "envs", "code"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

IZLENEN = ["core/inceleme.py", "core/geri_al.py", "core/telemetri.py"]
TESTLER = ["tests/test_inceleme.py", "tests/test_geri_al.py", "tests/test_telemetri.py",
           "tests/test_senaryo.py", "tests/test_ozellik.py"]


def _fonksiyon_araliklari(yol: str) -> list:
    """(ad, ilk_satir, son_satir) - basit ve yeterli: def'ten sonraki def'e kadar."""
    with io.open(yol, encoding="utf-8") as f:
        satirlar = f.read().splitlines()
    basliklar = []
    for i, s in enumerate(satirlar, 1):
        m = re.match(r"^(def|class) (\w+)", s)
        if m:
            basliklar.append((m.group(2), i))
    out = []
    for k, (ad, bas) in enumerate(basliklar):
        son = basliklar[k + 1][1] - 1 if k + 1 < len(basliklar) else len(satirlar)
        out.append((ad, bas, son))
    return out


def main() -> int:
    izleyici = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix, sys.exec_prefix])
    eski_argv = sys.argv[:]
    for t in TESTLER:
        yol = os.path.join(ROOT, t)
        if not os.path.isfile(yol):
            print("  (yok, atlandi) %s" % t)
            continue
        sys.argv = [yol]
        try:
            izleyici.runfunc(runpy.run_path, yol, run_name="__main__")
        except SystemExit:
            pass
        except Exception as e:  # noqa: BLE001
            print("  (%s kosarken hata: %s)" % (t, str(e)[:120]))
    sys.argv = eski_argv

    sayimlar = izleyici.results().counts        # {(dosya, satir): kac_kez}
    kosan = {}
    for (dosya, satir), n in sayimlar.items():
        if n:
            kosan.setdefault(os.path.normcase(os.path.abspath(dosya)), set()).add(satir)

    print("\n%-22s %-28s %s" % ("MODUL", "FONKSIYON", "durum"))
    print("-" * 66)
    hic = []
    for goreli in IZLENEN:
        tam = os.path.normcase(os.path.join(ROOT, goreli.replace("/", os.sep)))
        satirlar = kosan.get(tam, set())
        for ad, bas, son in _fonksiyon_araliklari(os.path.join(ROOT, goreli)):
            icinde = [x for x in satirlar if bas <= x <= son]
            durum = "kostu (%d satir)" % len(icinde) if icinde else "HIC KOSMADI"
            if not icinde:
                hic.append("%s::%s" % (goreli.split("/")[-1], ad))
            print("%-22s %-28s %s" % (goreli.split("/")[-1], ad, durum))
    print("-" * 66)
    if hic:
        print("HIC KOSMAYAN (%d): %s" % (len(hic), ", ".join(hic)))
    else:
        print("Izlenen modullerdeki her fonksiyon en az bir kez kostu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

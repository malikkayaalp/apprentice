"""GIZLILIK testi (core/gizlilik.py + rapor akisi) - denetim bulgusu 13.

YASANDI: rapor, cirak'in yazdigi her dosyanin TAM ICERIGINI tasiyordu ve bu rapor
`worker_run`/`worker_status` ile IDE'deki UZAK modele gidiyordu. README ise "kod makineden
cikmaz, denetciye yalnizca ozetler ve olcumler gider" diyordu. Iddia YANLISTI ve
`tests/test_server.py` bu davranisi DOGRU diye cakiyordu.

Cakilan yeni sozlesme:
  1. VARSAYILAN olarak tam dosya icerigi rapora GIRMEZ.
  2. Fark girer - ama fark da KAYNAK KODDUR: sinirlidir, maskelidir ve rapor bunu SOYLER.
  3. Tam icerik yalnizca ACIKCA acilirsa girer.
  4. Bilinen sir bicimleri maskelenir; kac tane maskelendigi RAPORDA gorunur.
  5. Iki rapor yolu (canli `report()` ve `rapor_diskten()`) AYNI kurala uyar.
  6. Belge ile davranis uyusur: kosulsuz "kod makineden cikmaz" ifadesi KALMAZ.
"""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.gizlilik import (VARSAYILAN, ayar, dosya_ozeti,  # noqa: E402
                           fark_uret, maskele, rapor_notu)

GIZLI_KOD = ('import os\n'
             'OPENAI = "sk-abcdefghijklmnopqrstuvwx"\n'
             'GH = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"\n'
             'password = "cok-gizli-parola"\n'
             'DB = "postgres://kadir:parolam123@sunucu:5432/db"\n'
             'AWS = "AKIAIOSFODNN7EXAMPLE"\n')


def varsayilan_kapali() -> bool:
    """TAM ICERIK VARSAYILAN OLARAK GITMEZ. Bu maddenin cekirdegi."""
    assert VARSAYILAN["tam_icerik"] is False, "tam icerik varsayilan ACIK - sizinti"
    assert VARSAYILAN["gizli_maskele"] is True

    a = dict(VARSAYILAN)
    k = dosya_ozeti("app.py", "x = 1\n", "x = 2\ny = 3\n", a)
    assert "icerik" not in k, "varsayilan raporda TAM ICERIK var: %s" % sorted(k)
    assert k["fark"] and "+y = 3" in k["fark"], k["fark"]
    assert k["eklendi"] == 2 and k["silindi"] == 1, k

    # ACIKCA acilinca gelir - ve o zaman da maskeli olur
    a2 = dict(VARSAYILAN, tam_icerik=True)
    k2 = dosya_ozeti("app.py", None, GIZLI_KOD, a2)
    assert "icerik" in k2, "acikca acildi ama icerik gelmedi"
    assert "sk-abcdefghijklmnopqrstuvwx" not in k2["icerik"], "tam icerik MASKELENMEMIS"
    print("varsayilan kapali: ok (tam icerik gitmiyor, acilinca maskeli geliyor)")
    return True


def sirlar_maskeleniyor() -> bool:
    """Bilinen sir bicimleri maskelenir; NORMAL KOD bozulmaz (maskeleme denetciyi kor etmemeli)."""
    metin, bulunan = maskele(GIZLI_KOD)
    for sir in ("sk-abcdefghijklmnopqrstuvwx", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
                "cok-gizli-parola", "parolam123", "AKIAIOSFODNN7EXAMPLE"):
        assert sir not in metin, "maskelenmedi: %s" % sir
    assert len(set(bulunan)) >= 4, bulunan
    # ADI kalir ki denetci "burada bir sir var" diyebilsin
    assert "password" in metin and "OPENAI" in metin, metin

    # NORMAL KOD DEGISMEZ - yanlis pozitif denetimi korlestirir
    duz = ("def kdv(tutar, oran=0.20):\n"
           "    return round(tutar * oran, 2)\n"
           "SABIT = 'merhaba dunya'\n"
           "yol = 'https://ornek.com/api/v1/kaynak'\n")
    m2, b2 = maskele(duz)
    assert m2 == duz, "normal kod maskelendi (yanlis pozitif):\n%s" % m2
    assert not b2, b2

    # FARK icindeki sir de maskelenir (asil sizinti yolu buydu)
    k = dosya_ozeti("gizli.py", "", GIZLI_KOD, dict(VARSAYILAN))
    assert "sk-abcdefghijklmnopqrstuvwx" not in k["fark"], "FARK sir sizdiriyor"
    assert k.get("maskelenen"), "maskelenen turler rapora yazilmamis"
    print("sirlar maskeleniyor: ok (%d tur yakalandi, normal kod bozulmadi)" % len(set(bulunan)))
    return True


def fark_sinirli() -> bool:
    """Fark SINIRLI: fark da kaynak koddur, sinirsiz gonderilemez."""
    buyuk = "".join("satir %d\n" % i for i in range(4000))
    f, kirpik = fark_uret("", buyuk, "buyuk.py", sinir=1000)
    assert kirpik and len(f) <= 1100, (kirpik, len(f))
    assert "kirpildi" in f, f[-80:]

    k = dosya_ozeti("buyuk.py", "", buyuk, dict(VARSAYILAN, fark_siniri=500))
    assert k["fark_kirpildi"] is True and len(k["fark"]) <= 620, len(k["fark"])

    # DEGISIKLIK YOKSA fark bos - gereksiz kod gondermeyiz
    assert fark_uret("ayni\n", "ayni\n", "a.py")[0] == "", "degismeyen dosya icin fark uretildi"
    print("fark sinirli: ok (kirpiliyor, degismeyen dosya icin bos)")
    return True


def rapor_ne_gonderdigini_soyluyor() -> bool:
    """Rapor NE gonderdigini kendisi soyler - kullanici tahmin etmesin."""
    n = rapor_notu(dict(VARSAYILAN))
    assert n["gonderilen"] == "yalniz_fark", n
    assert n["maskeleme"] is True and n["fark_siniri"] == VARSAYILAN["fark_siniri"]
    assert "KAYNAK KOD" in n["not"], "not, farkin kaynak kod oldugunu soylemiyor"
    n2 = rapor_notu(dict(VARSAYILAN, tam_icerik=True))
    assert n2["gonderilen"] == "tam_icerik+fark", n2

    # Ayar okunamazsa GUVENLI tarafa dus
    class Patlak:
        def get(self, k, d=None):
            raise RuntimeError("ayar yok")
    a = ayar(Patlak())
    assert a["tam_icerik"] is False and a["gizli_maskele"] is True, a

    # Bozuk deger guvenli varsayilana duser
    class Bozuk:
        def get(self, k, d=None):
            return {"tam_icerik": "evet", "fark_siniri": "abc"} if k == "gizlilik" else d
    b = ayar(Bozuk())
    assert b["fark_siniri"] == 4000, b
    print("rapor ne gonderdigini soyluyor: ok (bozuk ayarda guvenli varsayilan)")
    return True


def iki_rapor_yolu_ayni() -> bool:
    """Canli rapor ile disk raporu AYNI gizlilik kuralina uymali.

    Iki farkli kural, "hangi rapora bakiyorum" sorusunu dogurur ve sizintiyi bir yolda
    acik birakir - denetimde bulunan tam da bu turden bir tutarsizlikti."""
    kaynak = open(os.path.join(ROOT, "server", "apprentice_server.py"), encoding="utf-8").read()
    assert kaynak.count("dosya_ozeti(") >= 2, "iki rapor yolundan biri gizlilik suzgecini kullanmiyor"
    assert '"icerik": icerik if len(icerik)' not in kaynak, "eski tam-icerik yolu duruyor"
    assert "ic[:ICERIK_SINIRI]" not in kaynak, "disk raporu hala tam icerik kesiyor"
    assert kaynak.count("_gizlilik_notu()") >= 2, "rapor gizlilik alanini tasimiyor"
    print("iki rapor yolu ayni: ok")
    return True


def belge_gercegi_soyluyor() -> bool:
    """BELGE ile DAVRANIS uyusmali - biri duzelip digeri kalirsa madde COZULMEMISTIR."""
    for ad in ("README.md", os.path.join("server", "README.md")):
        with open(os.path.join(ROOT, ad), encoding="utf-8") as f:
            m = f.read()
        # kosulsuz iddia KALMAMALI (yalniz "boyle demiyoruz" diyen cumle serbest)
        for yasak in ("Your code never leaves the machine and",
                      "the supervisor only ever sees summaries",
                      "Kod dışarı çıkmaz, kota yoktur"):
            assert yasak not in m, "%s hala kosulsuz gizlilik iddiasi tasiyor: %r" % (ad, yasak)
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        r = f.read()
    assert "diff is still source code" in r or "Fark da kaynak koddur" in r, \
        "README farkin kaynak kod oldugunu soylemiyor"
    assert "tam_icerik" in r, "README tam icerik anahtarindan bahsetmiyor"
    # DENETCI KURALI da guncel olmali - yoksa usta olmayan alani okumaya calisir
    with open(os.path.join(ROOT, "kur.py"), encoding="utf-8") as f:
        k = f.read()
    assert "yazilan_dosyalar[].fark" in k, "denetci kurali hala 'icerik' okumayi soyluyor"
    assert "yazilan_dosyalar[].icerik'i oku" not in k, "eski kural metni duruyor"
    # Ayar sablonunda alan gercekten var mi (sablonda olup kodda okunmayan alan birakmayiz)
    with open(os.path.join(ROOT, "apprentice.config.template.json"), encoding="utf-8") as f:
        t = json.load(f)
    assert t.get("gizlilik", {}).get("tam_icerik") is False, t.get("gizlilik")
    print("belge gercegi soyluyor: ok (README, server/README, denetci kurali, sablon)")
    return True


def panel_kullaniciya_soyluyor() -> bool:
    """Panel de soylemeli: kullanici belgeyi degil, kullandigi ANI gorur."""
    with open(os.path.join(ROOT, "clients", "web", "panel.html"), encoding="utf-8") as f:
        h = f.read()
    assert 'id="gizNot"' in h, "panelde gizlilik notu yok"
    assert "değişen kod" in h, "panel ne gonderildigini soylemiyor"
    assert "/api/gizlilik" in h, "panel notu GERCEK ayardan okumuyor (sabit metin yalan soyleyebilir)"
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        p = f.read()
    assert '"/api/gizlilik"' in p, "panel sunucusunda gizlilik ucu yok"
    print("panel kullaniciya soyluyor: ok")
    return True


def main() -> int:
    denemeler = [varsayilan_kapali, sirlar_maskeleniyor, fark_sinirli,
                 rapor_ne_gonderdigini_soyluyor, iki_rapor_yolu_ayni,
                 belge_gercegi_soyluyor, panel_kullaniciya_soyluyor]
    kalan = 0
    for fn in denemeler:
        try:
            fn()
        except AssertionError as e:
            print("KALDI - %s: %s" % (fn.__name__, str(e)[:400]))
            kalan += 1
        except Exception as e:  # noqa: BLE001
            print("PATLADI - %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]))
            kalan += 1
    print("SONUC:", "GECTI" if not kalan else "KALDI (%d)" % kalan)
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())

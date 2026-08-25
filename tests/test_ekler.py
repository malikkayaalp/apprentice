"""EKLER testi (core/ekler.py + hapis okuma izni) - denetim bulgusu 1.

YASANDI: panelden yuklenen dosya adiyla DOGRUDAN proje klasorune yaziliyordu. Projede
ayni adli dosya varsa SESSIZCE eziliyordu. Ustelik yazim, isin ANLIK GORUNTUSUNDEN once
oldugu icin anlik goruntu o dosyayi "baslarken zaten kirli" goruyor, geri alma da onu
"kullanicinin kendi degisikligi" sayip ATLIYORDU: Apprentice hem uzerine yaziyor hem geri
getirmeyi reddediyordu.

Cakilan sozlesme:
  1. Mevcut proje dosyasi HICBIR ZAMAN sessizce ezilmez (ek projeye HIC yazilmaz).
  2. Ekler ise ozel, calisma agacinin DISINDAKI bir klasorde durur.
  3. Cirak eki OKUYABILIR (yoksa ek islevsiz) ama oraya YAZAMAZ.
  4. Ek adi temizlenir: yol kacisi, surucu harfi, denetim karakteri, Windows ayrilmis adi.
  5. Ek yazimi isin anlik goruntusunu KIRLETMEZ.
"""
from __future__ import annotations
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "envs", "code"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.ekler import METIN_UZANTILAR, ad_temizle, gorev_notu, kaydet  # noqa: E402


def ayni_isimli_dosya_ezilmez() -> bool:
    """ASIL SENARYO: projede `kdv.py` var, kullanici `kdv.py` ekliyor."""
    proje = tempfile.mkdtemp()
    ozgun = "def kdv(t):\n    return t * 0.20   # KULLANICININ KODU\n"
    with open(os.path.join(proje, "kdv.py"), "w", encoding="utf-8") as f:
        f.write(ozgun)

    is_dizini = tempfile.mkdtemp()                     # <HOME>/jobs/<id>/ karsiligi
    ek_dizin = os.path.join(is_dizini, "ekler")
    yollar, red = kaydet([{"ad": "kdv.py", "icerik": "EKLENEN BASKA ICERIK\n"}],
                         ek_dizin, uzantilar=METIN_UZANTILAR)
    assert yollar and not red, (yollar, red)

    # 1) PROJEDEKI DOSYA DOKUNULMAMIS
    with open(os.path.join(proje, "kdv.py"), encoding="utf-8") as f:
        assert f.read() == ozgun, "KULLANICININ DOSYASI EZILDI"
    # 2) proje klasorune HICBIR yeni dosya girmemis
    assert sorted(os.listdir(proje)) == ["kdv.py"], os.listdir(proje)
    # 3) ek, calisma agacinin DISINDA
    assert os.path.realpath(yollar[0]).startswith(os.path.realpath(ek_dizin)), yollar[0]
    with open(yollar[0], encoding="utf-8") as f:
        assert "EKLENEN BASKA ICERIK" in f.read()

    # gorev notu MUTLAK yol vermeli - ek calisma dizininde degil, goreli yol onu bulmaz
    not_ = gorev_notu(yollar)
    assert os.path.normpath(yollar[0]) in not_, not_
    assert "DISINDA" in not_ and "yazamazsin" in not_, not_
    print("ayni isimli dosya ezilmez: ok (proje dosyasi duruyor, ek disarida)")
    return True


def ad_temizligi() -> bool:
    """Ek adi kullanicidan gelir: yol kacisi hedef klasorun disina yazamamali."""
    for ham, olmamali in ((r"..\..\gizli.py", ".."), ("/etc/passwd", "/"),
                          ("C:evil.py", ":"), ("alt/klasor/x.py", "/"),
                          ("kotu\x00ad.py", "\x00")):
        temiz = ad_temizle(ham)
        assert olmamali not in temiz, "%r -> %r (hala %r iceriyor)" % (ham, temiz, olmamali)
        assert os.path.basename(temiz) == temiz, temiz
    assert ad_temizle("CON.txt").upper().startswith("_CON"), ad_temizle("CON.txt")
    assert ad_temizle("") == "ek" and ad_temizle("...") == "ek"
    assert ad_temizle("a" * 300 + ".py").endswith(".py")
    assert len(ad_temizle("a" * 300 + ".py")) <= 100

    # KACIS DENEMESI gercekten hedef klasorde mi kaliyor
    d = tempfile.mkdtemp()
    hedef = os.path.join(d, "ekler")
    yollar, _ = kaydet([{"ad": r"..\..\kacis.py", "icerik": "x"}], hedef,
                       uzantilar=METIN_UZANTILAR)
    assert yollar and os.path.dirname(os.path.realpath(yollar[0])) == os.path.realpath(hedef), yollar
    print("ad temizligi: ok (yol kacisi, surucu harfi, ayrilmis ad, uzun ad)")
    return True


def ayni_ad_iki_kez() -> bool:
    """Ayni ad iki kez gelirse ikincisi ayrilir - ek de ek'i ezmemeli."""
    d = os.path.join(tempfile.mkdtemp(), "ekler")
    yollar, red = kaydet([{"ad": "a.py", "icerik": "birinci"},
                          {"ad": "a.py", "icerik": "ikinci"}], d, uzantilar=METIN_UZANTILAR)
    assert len(yollar) == 2 and yollar[0] != yollar[1], yollar
    icerikler = []
    for y in yollar:
        with open(y, encoding="utf-8") as f:
            icerikler.append(f.read())
    assert sorted(icerikler) == ["birinci", "ikinci"], icerikler

    # metin olmayan ek REDDEDILIR (cirak yalniz metin alir) ve sebebi yazilir
    _, red2 = kaydet([{"ad": "resim.png", "b64": "AAAA"}], d, uzantilar=METIN_UZANTILAR)
    assert red2 and "metin" in red2[0], red2
    print("ayni ad iki kez: ok (ek de ek'i ezmiyor, metin disi reddediliyor)")
    return True


def hapis_okur_ama_yazmaz() -> bool:
    """Cirak eki OKUYABILIR, oraya YAZAMAZ. Yazma hapsi genisletilmedi."""
    import code_runner as CR

    calisma = tempfile.mkdtemp()
    ek_dizin = tempfile.mkdtemp()
    ek = os.path.join(ek_dizin, "girdi.txt")
    with open(ek, "w", encoding="utf-8") as f:
        f.write("ek icerigi")
    disari = tempfile.mkdtemp()
    yabanci = os.path.join(disari, "yabanci.txt")
    with open(yabanci, "w", encoding="utf-8") as f:
        f.write("baska yer")

    jail = CR.Jail(calisma, ek_dizin)
    # OKUMA: calisma dizini + ek klasoru SERBEST
    assert jail.oku_yolu("kendi.py").startswith(os.path.realpath(calisma))
    assert os.path.realpath(jail.oku_yolu(ek)) == os.path.realpath(ek), "ek okunamiyor"
    # OKUMA: baska hicbir yer OLMAZ
    for kotu in (yabanci, os.path.join(disari, ".."), disari):
        try:
            jail.oku_yolu(kotu)
            raise AssertionError("ek klasoru disi okundu: %s" % kotu)
        except ValueError:
            pass
    # YAZMA: ek klasoru bile YASAK - hapis genisletilmedi
    try:
        jail.path(ek)
        raise AssertionError("ek klasorune YAZMA yolu acildi")
    except ValueError:
        pass
    # ek dizini verilmemisse eski davranis aynen surer
    dar = CR.Jail(calisma)
    try:
        dar.oku_yolu(ek)
        raise AssertionError("ek dizini yokken disari okundu")
    except ValueError:
        pass
    print("hapis okur ama yazmaz: ok (okuma dar genisledi, yazma hic degismedi)")
    return True


def kabuk_eki_goremez() -> bool:
    """Kabuk korumasi ek klasorunu de reddeder - mutlak yol zaten yasak."""
    import code_runner as CR
    ek = os.path.join(tempfile.mkdtemp(), "girdi.txt")
    sebep = CR.kabuk_guvenli('type "%s"' % ek, tempfile.mkdtemp())
    assert sebep, "kabuk ek klasorunu okuyabiliyor - okuma yolu yalniz read_file olmali"
    print("kabuk eki goremez: ok (okuma yolu tek: read_file)")
    return True


def akis_sirasi_dogru() -> bool:
    """Ek yazimi ISIN ANLIK GORUNTUSUNDEN once projeye dokunmamali.

    Kaynak denetimi: panel artik ekleri Job olusturulduktan SONRA ve job.start()'tan
    ONCE, job.dir altina yaziyor. Eski sira (calisma dizinine, is olusmadan) geri
    gelirse bu test duser."""
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        p = f.read()
    assert "def _ekleri_kaydet(" not in p, "eski guvensiz yazici geri gelmis"
    govde = p[p.index("def _gorev_baslat("):p.index("def _cirak_sohbet(")]
    # GERCEK cagriyi ara, metni gecen yorumu degil: "\n    job.start()" satir basindadir.
    # (Ilk surum duz `index("job.start()")` kullaniyordu ve aciklama yorumunu yakaliyordu -
    # test kodu degil KENDINI olcuyordu.)
    i_job = govde.index("\n    job = srv.Job(")
    i_ek = govde.index("\n        from core.ekler import")
    i_start = govde.index("\n    job.start()")
    assert i_job < i_ek < i_start, "ekler Job ile start arasinda yazilmiyor"
    assert "os.path.join(job.dir" in govde, "ekler isin KENDI klasorune yazilmiyor"
    # calisma dizinine ek yazan eski cagri kalmamis olmali
    assert "kaydet(ekler_istegi, tam_dizin" not in govde, "ekler hala calisma dizinine yaziliyor"
    print("akis sirasi dogru: ok (Job -> ekler -> start)")
    return True


def main() -> int:
    denemeler = [ayni_isimli_dosya_ezilmez, ad_temizligi, ayni_ad_iki_kez,
                 hapis_okur_ama_yazmaz, kabuk_eki_goremez, akis_sirasi_dogru]
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

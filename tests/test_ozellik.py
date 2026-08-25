"""OZELLIK (property) TESTLERI - Hypothesis.

Elle yazilan testler DUSUNULEN girdileri dener. Bu depodaki gercek hatalarin cogu
dusunulmemis girdiden cikti:

    ntpath.isabs("/x") Python 3.13'te FALSE doner -> "/mutlak" sessizce koke goreli sayildi
    "C:foo" surucu-goreli yoldur -> ntpath.join(r"D:\\ws", "C:foo") == "C:foo" (hapis ucar)
    silme kara listesinde os.remove var, os.unlink YOK

Ucu de elle bulundu. Hypothesis bunlari aramak icin binlerce varyasyon uretir ve bir hata
bulunca girdiyi KUCULTUP en kucuk bozan ornegi verir.

CALISTIRMA: python tests/test_ozellik.py   (hypothesis yoksa ATLANIR - gelistirme
bagimliligidir, kullanicinin kurulumunda ARANMAZ; proje "ek paket yok" sozu verir).

DEGISMEZ KURAL (hepsinin ortak sozu):
    kullanicidan gelen hicbir dize, calisma alani disina cikan bir yola cozulemez.
"""
from __future__ import annotations
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:
    print("ozellik testleri: hypothesis yok, atlandi  (pip install hypothesis)")
    sys.exit(0)

from core.geri_al import _guvenli                    # noqa: E402
from core.inceleme import _kapsam_disi               # noqa: E402
from core.telemetri import sinifla                   # noqa: E402
from goruntuleyici import _yol_gecerli               # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "envs", "code"))
from code_runner import Jail                         # noqa: E402

# Ornek sayisi disaridan ayarlanir: gunluk kosuda 400 (hizli), gece kusatmasinda
# APPRENTICE_OZELLIK=5000 ile derin tarama. Hypothesis bulduklarini .hypothesis/
# altinda saklar; bir kez bulunan bozan ornek sonraki kosularda ONCE denenir.
ORNEK = int(os.environ.get("APPRENTICE_OZELLIK") or 400)
AYAR = settings(max_examples=ORNEK, deadline=None,
                suppress_health_check=[HealthCheck.function_scoped_fixture])

# Yol parcalari: gercek tuzaklar HAVUZDA olsun ki Hypothesis onlari birlestirsin.
PARCA = st.sampled_from([
    "a", "b.py", "alt", "..", ".", "", "/", "\\", "//", "\\\\", "~", "*",
    "C:", "C:\\", "C:x", "D:", "\\\\sunucu", "\\\\?\\C:", ":", "...",
    " ", "\t", "\n", "%2e%2e", "..%2f", "con", "nul", "a b", "ü", "🙂",
])
YOL = st.lists(PARCA, min_size=0, max_size=6).map(lambda p: "/".join(p))
HAM = st.one_of(YOL, st.text(max_size=40))


def _kok() -> str:
    return _duz(tempfile.mkdtemp())


def _duz(yol: str) -> str:
    r"""realpath Windows'ta bazen UZUN-YOL onekiyle doner (\\?\C:\...). Onek ayni yeri
    gosterir ama dize karsilastirmasini bozar - testin YANLIS ALARM vermemesi icin kirpilir.
    YASANDI: '.../a' kacis sanildi; oysa Test\a'ya, yani ICERIYE cozuluyordu - hatayi
    bulan test degil, testin kendisiydi."""
    t = os.path.realpath(yol)
    for onek in (r"\\?\UNC" + os.sep, "\\\\?\\"):
        if t.startswith(onek):
            t = t[len(onek):]
            break
    return t


@given(p=HAM)
@AYAR
def jail_hapsi(p):
    """Jail.path YA calisma alani icinde bir yol doner YA DA reddeder. Ucuncu ihtimal yok.

    Bu, harness'in en kritik guvenlik sozu: cirak yalniz kendi calisma alanina yazabilir."""
    jail = Jail(_kok())
    try:
        tam = _duz(jail.path(p))
    except (ValueError, OSError):
        return                                        # reddetmek DOGRU cevap
    kok = jail.root
    assert tam == kok or tam.startswith(kok + os.sep), \
        "HAPIS UCTU: %r -> %r (kok %r)" % (p, tam, kok)


@given(p=HAM)
@AYAR
def geri_al_guvenligi(p):
    """Geri alma yalniz calisma alani icindeki yolu isler; disariyi None ile reddeder.
    Bu fonksiyon DOSYA SILEBILIYOR - kacis buradan olursa zarar geri alinamaz."""
    kok = _kok()
    tam = _guvenli(kok, p)
    tam = _duz(tam) if tam else tam
    if tam is None:
        return
    kg = os.path.realpath(kok)
    assert tam == kg or tam.startswith(kg + os.sep), "GERI ALMA DISARI CIKTI: %r -> %r" % (p, tam)


@given(p=HAM)
@AYAR
def goruntuleyici_yolu(p):
    """Goruntuleyici yolu ya reddeder ya da GORELI, '..' icermeyen bir yol doner."""
    y = _yol_gecerli(p)
    if not y:
        return
    assert ".." not in y.split("/"), "'..' gecti: %r -> %r" % (p, y)
    assert not os.path.isabs(y) and not os.path.splitdrive(y)[0], "mutlak yol gecti: %r" % y
    # Kabul edilen her yol, koke eklendiginde hala icerde olmali
    kok = _kok()
    tam = _duz(os.path.join(kok, y))
    assert tam == kok or tam.startswith(kok + os.sep), "kabul edilen yol disari cikti: %r" % y


@given(yol=HAM, izin=st.lists(PARCA, min_size=1, max_size=3))
@AYAR
def kapsam_kacisi(yol, izin):
    """Yazma kapsami: kapsam ICINDE sayilan her yol, izin verilen bir kokun altinda olmali.

    Yanlis NEGATIF (icerdekine 'disarda' demek) zararsizdir - fazladan uyari cikar.
    Yanlis POZITIF (disardakine 'iceride' demek) guvenlik hatasidir; aranan budur."""
    kapsam = {"liste": izin, "sinirli": True}
    if _kapsam_disi(yol, kapsam):
        return                                        # disarida demek: guvenli taraf
    y = (yol or "").replace("\\", "/").lstrip("./")
    uydu = False
    for i in izin:
        n = str(i).replace("\\", "/").rstrip("/*").lstrip("./")
        if not n or y == n or y.startswith(n + "/"):
            uydu = True
            break
    assert uydu, "KAPSAM DISI yol iceride sayildi: %r (izin %r)" % (yol, izin)


@given(m=st.text(max_size=200))
@AYAR
def siniflandirici_daima_cevap(m):
    """Hata siniflandirici HER girdide bilinen bir sinif doner, ASLA patlamaz.
    Telemetri her isten sonra kosuyor; burada bir istisna butun olcumu durdurur."""
    s = sinifla(m)
    assert isinstance(s, str) and s, "bos sinif: %r" % m
    assert s in {"duraganlik", "zaman_asimi", "bagimlilik", "sozdizimi", "tanimsiz_ad",
                 "olu_kod", "test_beklentisi", "tip", "calisma_zamani", "bilinmeyen"}, s


def main() -> int:
    denemeler = [("Jail hapsi", jail_hapsi), ("geri alma guvenligi", geri_al_guvenligi),
                 ("goruntuleyici yolu", goruntuleyici_yolu), ("kapsam kacisi", kapsam_kacisi),
                 ("siniflandirici", siniflandirici_daima_cevap)]
    for ad, fn in denemeler:
        try:
            fn()
        except AssertionError as e:
            print("ozellik testi KALDI - %s:\n%s" % (ad, str(e)[:900]))
            return 1
        print("%-22s ok (%d uretilmis girdi)" % (ad, ORNEK))
    print("SONUC: GECTI")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""POLITIKA testi (core/politika.py).

Cakilan sozlesme:
  1. Karari MODEL degil DOGRULAYICI verir - "beyan" alanina bakilmaz.
  2. "bilinmiyor" MESRU sonuctur: is kosuyorsa ya da ozet yoksa uydurmayiz.
  3. VARSAYILAN MUHAFAZAKAR: otomatik kabul KAPALI - KABUL kararini insan verir.
  4. Duraganlik/kapsam ihlali/ust uste hata kuyrugu DURDURUR (para yakmayi keser).
  5. Politika kuyruga takilabilir ve kararini inceleme.json'a YAZAR.
"""
from __future__ import annotations
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.politika import VARSAYILAN, Politika, ayar_yukle, degerlendir, karar  # noqa: E402
from core.kuyruk import Kuyruk  # noqa: E402


def _ozet(durum="bitti", dogrulama=None, disi=(), duragan=False, beyan=""):
    """inceleme() ciktisinin politika icin anlamli alt kumesi."""
    return {"sema": 1, "is_id": "is1", "durum": durum, "beyan": beyan,
            "dogrulama": dogrulama if dogrulama is not None
            else [{"ad": "derleme", "durum": "gecti", "kanit": "derlendi"},
                  {"ad": "testler", "durum": "gecti", "kanit": "6 gecti"}],
            "degisen_dosyalar": [{"yol": y, "kapsam_disi": True} for y in disi]
            or [{"yol": "a.py", "kapsam_disi": False}],
            "duraganlik": {"var": True, "imza": "_kazanan() beklenen True gelen False"}
            if duragan else {"var": False}}


def dogrulayici_karar_verir() -> bool:
    """Sinyal DOGRULAYICIDAN gelir; modelin BEYANI karari degistirmez."""
    d = degerlendir(_ozet())
    assert d["sonuc"] == "temiz", d

    # model "her sey harika" dese de dogrulama kaldiysa sonuc KALDI
    kaldi = degerlendir(_ozet(beyan="Her sey mukemmel calisiyor, testler gecti!",
                              dogrulama=[{"ad": "testler", "durum": "kaldi",
                                          "kanit": "2 failed"}]))
    assert kaldi["sonuc"] == "kaldi", kaldi
    assert "testler" in kaldi["kalan_kontroller"], kaldi
    assert "2 failed" in kaldi["sebepler"][0], kaldi

    # tersi de: model kotumser olsa da dogrulama gectiyse TEMIZ
    iyi = degerlendir(_ozet(beyan="Emin degilim, sanirim calismiyor."))
    assert iyi["sonuc"] == "temiz", iyi
    print("dogrulayici karar verir: ok (beyan karari degistirmiyor)")
    return True


def bilinmiyor_mesru() -> bool:
    """Is kosuyorsa ya da ozet yoksa UYDURMAYIZ - ne kabul ne red, kuyruk da durmaz."""
    for o in ({}, {"sema": 1}, None, _ozet(durum="kosuyor")):
        d = degerlendir(o)
        assert d["sonuc"] == "bilinmiyor", (o, d)
        k = karar(d, VARSAYILAN)
        assert k["eylem"] == "devam" and k["isaret"] == "", k
    print("bilinmiyor mesru: ok (uydurma yok, kuyruk durmuyor)")
    return True


def varsayilan_muhafazakar() -> bool:
    """Otomatik kabul KAPALI: temiz iste bile KABUL kararini insan verir."""
    assert VARSAYILAN["otomatik_kabul"] is False
    assert VARSAYILAN["otomatik_reddet"] is False
    k = karar(degerlendir(_ozet()), VARSAYILAN)
    assert k["eylem"] == "devam" and k["isaret"] == "", k

    # acikca acilirsa isaret gelir
    a = dict(VARSAYILAN, otomatik_kabul=True)
    assert karar(degerlendir(_ozet()), a)["isaret"] == "kabul"
    a2 = dict(VARSAYILAN, otomatik_reddet=True)
    kk = karar(degerlendir(_ozet(dogrulama=[{"ad": "testler", "durum": "kaldi", "kanit": "x"}])), a2)
    assert kk["isaret"] == "red", kk        # inceleme.py "red" bekliyor, "reddet" degil
    print("varsayilan muhafazakar: ok (otomatik kabul kapali)")
    return True


def durdurma_kurallari() -> bool:
    """Duraganlik / kapsam ihlali / ust uste hata kuyrugu DURDURUR."""
    kaldi = _ozet(dogrulama=[{"ad": "testler", "durum": "kaldi", "kanit": "1 failed"}])
    assert karar(degerlendir(kaldi), VARSAYILAN)["eylem"] == "dur"
    # "devam" secilirse durmaz - kural ayarla degisir, kodla degil
    assert karar(degerlendir(kaldi), dict(VARSAYILAN, hata_olunca="devam"))["eylem"] == "devam"

    # DURAGANLIK: dogrulama gecmis gorunse bile devam etmek para yakmaktir
    dd = degerlendir(_ozet(duragan=True))
    assert dd["sonuc"] == "kaldi" and dd["duraganlik"], dd
    assert karar(dd, VARSAYILAN)["eylem"] == "dur"
    assert karar(dd, dict(VARSAYILAN, hata_olunca="devam"))["eylem"] == "dur", \
        "duraganlik hata_olunca=devam ile de durdurmali"

    # KAPSAM IHLALI (olculdu: dama gorevinde 11 dosya yazildi, 10'u istenmemisti)
    dk = degerlendir(_ozet(disi=("kur.bat", "temizle.sh")))
    assert dk["sonuc"] == "kaldi" and len(dk["kapsam_disi"]) == 2, dk
    assert karar(dk, VARSAYILAN)["eylem"] == "dur"
    assert "kur.bat" in dk["sebepler"][-1], dk["sebepler"]

    # UST USTE sinir: hata_olunca=devam olsa bile ikinci ust uste hatada dur
    a = dict(VARSAYILAN, hata_olunca="devam", ust_uste_hata_siniri=2)
    assert karar(degerlendir(kaldi), a, ust_uste=1)["eylem"] == "devam"
    assert karar(degerlendir(kaldi), a, ust_uste=2)["eylem"] == "dur"
    assert karar(degerlendir(kaldi), dict(a, ust_uste_hata_siniri=0), ust_uste=9)["eylem"] == "devam"
    print("durdurma kurallari: ok (duraganlik, kapsam, ust uste)")
    return True


def kuyruga_takiliyor() -> bool:
    """Politika kuyrukla birlikte calisir: temiz is gecer, kalan is kuyrugu durdurur."""
    ozetler = {"is1": _ozet(), "is2": _ozet(dogrulama=[{"ad": "derleme", "durum": "kaldi",
                                                        "kanit": "SyntaxError satir 4"}])}
    yazilan = []
    p = Politika("", dict(VARSAYILAN, otomatik_kabul=True),
                 ozet_al=lambda j: dict(ozetler.get(j, {}), is_id=j),
                 karar_yaz=lambda j, i, s: yazilan.append((j, i, s)))

    sayac = {"n": 0}
    biten = set()

    def calistir(istek):
        sayac["n"] += 1
        return {"is_id": "is%d" % sayac["n"]}

    k = Kuyruk(tempfile.mkdtemp(), calistir, lambda j: j in biten, politika=p)
    k.ekle({"gorev": "temiz is"}); k.ekle({"gorev": "bozuk is"}); k.ekle({"gorev": "ucuncu"})

    k.adim(); biten.add("is1"); k.adim()          # is1 bitti -> temiz
    assert not k.liste()["duraklatildi"], "temiz isten sonra kuyruk durdu"
    assert yazilan == [("is1", "kabul", "butun dogrulamalar gecti")], yazilan

    k.adim(); biten.add("is2"); k.adim()          # is2 bitti -> kaldi
    assert k.liste()["duraklatildi"], "kalan isten sonra kuyruk DURMADI"
    assert k.adim() == "bosta", "duraklatilmis kuyruk ucuncuyu baslatti"
    assert sayac["n"] == 2, "ucuncu is kosturuldu"
    assert p.gecmis[-1]["sonuc"] == "kaldi" and p.gecmis[-1]["eylem"] == "dur", p.gecmis
    assert "SyntaxError" in p.gecmis[-1]["sebep"], p.gecmis[-1]

    # kuyrugun kendi 'hata' yolu (is HIC baslamadi) da ust uste sayilir
    p2 = Politika("", VARSAYILAN, ozet_al=lambda j: {}, karar_yaz=lambda *a: None)
    assert p2({"no": 1, "is_id": ""}) == "dur"
    print("kuyruga takiliyor: ok (temiz gecer, kalan durdurur, karar yazilir)")
    return True


def ayar_okuma() -> bool:
    """Ayar dosyasindan okunur; eksik anahtarlar varsayilandan, bilinmeyen anahtar YOK SAYILIR."""
    class SahteCfg:
        def get(self, k, d=None):
            return {"hata_olunca": "devam", "otomatik_kabul": True,
                    "bilinmeyen_anahtar": 5, "_not": "aciklama"} if k == "politika" else d
    a = ayar_yukle(SahteCfg())
    assert a["hata_olunca"] == "devam" and a["otomatik_kabul"] is True
    assert a["duraganlikta"] == "dur", "eksik anahtar varsayilandan gelmedi"
    assert "bilinmeyen_anahtar" not in a and "_not" not in a, a

    class Patlak:
        def get(self, k, d=None):
            raise RuntimeError("ayar okunamadi")
    assert ayar_yukle(Patlak()) == dict(VARSAYILAN), "ayar patlayinca varsayilan gelmedi"
    print("ayar okuma: ok")
    return True


def main() -> int:
    ok = (dogrulayici_karar_verir() and bilinmiyor_mesru() and varsayilan_muhafazakar()
          and durdurma_kurallari() and kuyruga_takiliyor() and ayar_okuma())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

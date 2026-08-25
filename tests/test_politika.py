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


def bilinmiyor_tamamlanmis_sayilmaz() -> bool:
    """Is kaydi eksik/bozuk ya da is hala kosuyorsa: UYDURMA YOK, DEVAM DA YOK.

    ILK SURUM BU TESTI YANLIS CAKMISTI ("bilinmiyor mesru"): bilinmeyen durumda kuyrugun
    DEVAM etmesini dogru sayiyordu. Ama bozuk bir is kaydi, kuyrugun sonraki isi
    baslatmasina sessizce izin veriyordu - "tamamlanmis sayilmamali" kuralinin tersi."""
    for o in ({}, {"sema": 1}, None, _ozet(durum="kosuyor")):
        d = degerlendir(o)
        assert d["sonuc"] == "bilinmiyor", (o, d)
        k = karar(d, VARSAYILAN)
        assert k["isaret"] == "", "bilinmeyen durumda karar yazildi: %s" % k
        assert k["eylem"] == "dur", "bilinmeyen durumda kuyruk DEVAM etti: %s" % k
        assert "BILINMIYOR" in k["sebep"], k
    gevsek = dict(VARSAYILAN, bilinmeyince="devam")   # acikca istenirse devam edilebilir
    assert karar(degerlendir({}), gevsek)["eylem"] == "devam"
    print("bilinmiyor tamamlanmis sayilmaz: ok (varsayilan DUR)")
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
    assert yazilan and yazilan[0][:2] == ("is1", "kabul"), yazilan
    assert "gecti" in yazilan[0][2], yazilan

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


def dogrulanmamis_basari_sayilmaz() -> bool:
    """DENETLENMEMIS is BASARI DEGILDIR (denetim bulgusu 3).

    Eski `degerlendir()` yalnizca "kaldi" satirlarina bakiyordu. `_kabul_satiri`
    denetlenmemis kritere "yok" yazar - yani hicbir "kaldi" olmaz - ve is TEMIZ sayilirdi.
    otomatik_kabul acikken bu, DOGRULANMAMIS isin KABUL edilmesi demekti: telemetride
    duzelttigimiz "%100 dogrulayici / gercek %81,6" yalani politika kapisindan geri
    giriyordu.

    "temiz" artik POZITIF KANIT ister: en az bir dogrulama GECMIS olmali."""
    riskli = dict(VARSAYILAN, otomatik_kabul=True)      # EN RISKLI ayar

    # 1) GECTI -> tek kabul edilebilir hal
    d = degerlendir(_ozet())
    assert d["sonuc"] == "temiz", d
    k = karar(d, riskli)
    assert k["eylem"] == "devam" and k["isaret"] == "kabul", k

    # 2) KALDI -> kabul yok, dur
    d2 = degerlendir(_ozet(dogrulama=[{"ad": "testler", "durum": "kaldi", "kanit": "2 failed"}]))
    k2 = karar(d2, riskli)
    assert d2["sonuc"] == "kaldi" and k2["eylem"] == "dur" and k2["isaret"] != "kabul", (d2, k2)

    # 3) YOK (kabul kriteri verilmis, DENETLENMEMIS) -> kabul YOK, dur
    yok = _ozet(dogrulama=[{"ad": "derleme", "durum": "gecti", "kanit": "derlendi"},
                           {"ad": "kabul kriterleri", "durum": "yok",
                            "kanit": "3 kriter verildi, DOGRULANMADI"}])
    d3 = degerlendir(yok)
    k3 = karar(d3, riskli)
    assert d3["sonuc"] == "dogrulanmadi", d3
    assert k3["isaret"] == "", "DOGRULANMAMIS is KABUL edildi: %s" % k3
    assert k3["eylem"] == "dur", k3
    assert "DOGRULANMADI" in k3["sebep"], k3
    assert d3["denetlenmeyen"], d3

    # 4) HIC dogrulama kaydi yok -> basari iddia edilemez
    d4 = degerlendir(_ozet(dogrulama=[]))
    assert d4["sonuc"] == "dogrulanmadi", d4
    assert karar(d4, riskli)["isaret"] == "", "kanitsiz is KABUL edildi"

    # 5) EKSIK/BOZUK kayit -> tamamlanmis SAYILMAZ
    for bozuk in ({}, {"sema": 1}, None, {"is_id": "x", "durum": "calisiyor"}):
        db = degerlendir(bozuk)
        kb = karar(db, riskli)
        assert db["sonuc"] == "bilinmiyor", (bozuk, db)
        assert kb["isaret"] == "", "bilinmeyen durum KABUL edildi: %s" % kb
        assert kb["eylem"] == "dur", "bozuk kayitta kuyruk DEVAM etti: %s" % kb
    print("dogrulanmamis basari sayilmaz: ok (gecti/kaldi/yok/bilinmiyor ayri)")
    return True


def politika_patlarsa_kuyruk_durur() -> bool:
    """POLITIKA PATLARSA KUYRUK DURUR.

    Eski surum istisnayi yutup `return` ediyordu: koruma katmani coktugu halde kuyruk
    devam ediyordu. Yani en cok korumaya ihtiyac duyulan anda koruma YOKTU ve kimse
    bilmiyordu. Bu testin ilk surumu bu davranisi DOGRU diye cakiyordu - guvenli
    davranisa cevrildi."""
    def patlak(oge, kuyruk):
        raise ValueError("politika bozuk")

    sayac = {"n": 0}
    biten = set()

    def calistir(istek):
        sayac["n"] += 1
        return {"is_id": "is%d" % sayac["n"]}

    k = Kuyruk(tempfile.mkdtemp(), calistir, lambda j: j in biten, politika=patlak)
    k.ekle({"gorev": "bir"}); k.ekle({"gorev": "iki"})
    k.adim(); biten.add("is1"); k.adim()

    d = k.liste()
    assert d["duraklatildi"], "politika PATLADI ama kuyruk devam etti"
    assert k.adim() == "bosta", "duraklatilmis kuyruk sonrakini baslatti"
    assert sayac["n"] == 1, "ikinci is baslatildi: %d" % sayac["n"]
    # SEBEP GORUNUR OLMALI - sessizce yutulmamali
    ds = d.get("durma_sebebi") or {}
    assert "PATLADI" in (ds.get("sebep") or ""), "istisna sebebi kaydedilmemis: %s" % ds
    assert "politika bozuk" in ds["sebep"], ds
    print("politika patlarsa kuyruk durur: ok (sebep kayitli, sessiz yutma yok)")
    return True


def durma_sebebi_gorunur() -> bool:
    """Kuyruk NEDEN durdu - kullanici panelde GORMELI.

    Durduran oge cogu zaman "bitti" gorunur; panel yalnizca hatali/yarim ogelerin
    sebebine bakiyordu ve kullanici sebebi HIC goremiyordu."""
    ozetler = {"is1": _ozet(dogrulama=[{"ad": "kabul kriterleri", "durum": "yok",
                                        "kanit": "2 kriter verildi, DOGRULANMADI"}])}
    p = Politika("", VARSAYILAN, ozet_al=lambda j: dict(ozetler.get(j, {}), is_id=j),
                 karar_yaz=lambda *a: None)
    biten = set()

    def calistir(istek):
        return {"is_id": "is1"}

    k = Kuyruk(tempfile.mkdtemp(), calistir, lambda j: j in biten, politika=p)
    k.ekle({"gorev": "bir"}, baslik="KDV hesabı"); k.ekle({"gorev": "iki"})
    k.adim(); biten.add("is1"); k.adim()

    d = k.liste()
    assert d["duraklatildi"], "denetlenmemis is sonrasi kuyruk durmadi"
    ds = d.get("durma_sebebi") or {}
    assert ds.get("baslik") == "KDV hesabı", ds
    assert "DOGRULANMADI" in (ds.get("sebep") or ""), ds
    assert ds.get("is_id") == "is1", ds
    # DURDURAN oge "bitti" durumunda - yani sebebi ogeden okumak YETMEZ
    durduran = [o for o in d["ogeler"] if o.get("no") == ds["no"]][0]
    assert durduran["durum"] == "bitti", durduran

    # SURDURUNCE sebep temizlenir (bayat sebep gostermeyelim)
    k.duraklat(False)
    assert k.liste().get("durma_sebebi") is None, k.liste().get("durma_sebebi")

    # PANEL bu alani gercekten cizmeli
    with open(os.path.join(ROOT, "clients", "web", "panel.html"), encoding="utf-8") as f:
        h = f.read()
    assert "durma_sebebi" in h, "panel kuyrugun durma sebebini okumuyor"
    assert "Kuyruk durduruldu" in h, "panel durma sebebini gostermiyor"
    print("durma sebebi gorunur: ok (kuyruk duzeyinde + panelde)")
    return True


def main() -> int:
    ok = (dogrulayici_karar_verir() and bilinmiyor_tamamlanmis_sayilmaz()
          and varsayilan_muhafazakar() and durdurma_kurallari() and kuyruga_takiliyor()
          and ayar_okuma() and dogrulanmamis_basari_sayilmaz()
          and politika_patlarsa_kuyruk_durur() and durma_sebebi_gorunur())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

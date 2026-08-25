"""KUYRUK testi (core/kuyruk.py).

Cakilan sozlesme:
  1. SIRA korunur ve es zamanlilik 1'dir - iki is ayni anda kosmaz (tek GPU).
  2. DURAKLATMA gercekten durdurur; surdurunce kaldigi yerden devam eder.
  3. COKME KURTARMA: yarida kalan is SESSIZCE YENIDEN KOSTURULMAZ (dosya yazmis olabilir).
  4. Baslatilamayan is kuyrugu KILITLEMEZ - 'hata' isaretlenir, sira ilerler.
  5. POLITIKA 'dur' derse kuyruk duraklatilir - ayni hata 12 kez tekrarlanmaz.
"""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.kuyruk import Kuyruk  # noqa: E402


class Sahte:
    """Panel yerine gecen sahte kosucu: is baslatir, biten isleri elle isaretleriz."""

    def __init__(self, patlayanlar=()):
        self.baslatilan, self.biten, self.patlayanlar = [], set(), set(patlayanlar)
        self.sayac = 0

    def calistir(self, istek):
        gorev = str(istek.get("gorev") or "")
        if gorev in self.patlayanlar:
            return {"hata": "model yuklenemedi"}
        self.sayac += 1
        jid = "is%d" % self.sayac
        self.baslatilan.append((jid, gorev))
        return {"is_id": jid, "klasor": "C:/ws"}

    def bitti_mi(self, jid):
        return jid in self.biten

    def bitir(self, jid):
        self.biten.add(jid)


def _kuyruk(patlayanlar=(), politika=None):
    ev = tempfile.mkdtemp()
    s = Sahte(patlayanlar)
    return Kuyruk(ev, s.calistir, s.bitti_mi, politika=politika), s, ev


def sira_ve_tek_is() -> bool:
    """Sira korunur; IKI IS AYNI ANDA KOSMAZ (tek GPU - olculmus karar)."""
    k, s, _ = _kuyruk()
    for ad in ("bir", "iki", "uc"):
        k.ekle({"gorev": ad})
    assert k.liste()["sayim"]["bekliyor"] == 3

    assert k.adim() == "baslatildi"
    assert [g for _, g in s.baslatilan] == ["bir"], s.baslatilan
    # ikinci adim IKINCI ISI BASLATMAZ - birincisi hala kosuyor
    assert k.adim() == "bekleniyor"
    assert len(s.baslatilan) == 1, "iki is ayni anda kostu"
    assert k.liste()["sayim"]["kosuyor"] == 1

    s.bitir("is1")
    assert k.adim() == "bitti"
    assert k.adim() == "baslatildi"
    assert [g for _, g in s.baslatilan] == ["bir", "iki"], s.baslatilan
    s.bitir("is2"); k.adim(); k.adim()
    s.bitir("is3"); k.adim()
    assert k.adim() == "bosta", "kuyruk bitince bosta donmeli"
    assert k.liste()["sayim"]["bitti"] == 3, k.liste()["sayim"]
    print("sira ve tek is: ok (sira korundu, es zamanlilik 1)")
    return True


def duraklatma() -> bool:
    """Duraklatma gercekten durdurur; surdurunce KALDIGI YERDEN devam eder."""
    k, s, _ = _kuyruk()
    k.ekle({"gorev": "bir"}); k.ekle({"gorev": "iki"})
    k.duraklat(True)
    assert k.adim() == "bosta", "duraklatilmis kuyruk is baslatti"
    assert not s.baslatilan
    k.duraklat(False)
    assert k.adim() == "baslatildi"
    s.bitir("is1"); k.adim()
    # kosarken duraklatilirsa KOSAN is oldurulmez, sirdaki BASLAMAZ
    k.duraklat(True)
    assert k.adim() == "bosta"
    assert len(s.baslatilan) == 1, s.baslatilan
    print("duraklatma: ok (durdurur, surdurunce devam eder)")
    return True


def silme_ve_sira_degistirme() -> bool:
    """Bekleyen oge silinir/tasinir; KOSAN oge silinemez."""
    k, s, _ = _kuyruk()
    a = k.ekle({"gorev": "bir"}); k.ekle({"gorev": "iki"}); k.ekle({"gorev": "uc"})
    # "uc"u basa al
    assert k.tasi(3, -1).get("ok"), k.tasi(3, -1)
    assert k.tasi(3, -1).get("ok")
    sira = [o["baslik"] for o in k.liste()["ogeler"] if o["durum"] == "bekliyor"]
    assert sira == ["uc", "bir", "iki"], sira
    # ucta tasima sessizce yerinde birakir (hata degil)
    assert k.tasi(3, -1).get("ok")

    assert k.sil(2).get("ok"), "bekleyen oge silinemedi"
    assert k.liste()["sayim"]["iptal"] == 1
    k.adim()                                   # "uc" kosmaya basladi
    kosan = [o for o in k.liste()["ogeler"] if o["durum"] == "kosuyor"][0]
    assert "KOSUYOR" in (k.sil(kosan["no"]).get("hata") or ""), "kosan is silindi"
    assert k.sil(999).get("hata"), "olmayan oge silindi"
    assert a["no"] == 1
    print("silme ve sira: ok (bekleyen silinir/tasinir, kosan korunur)")
    return True


def cokme_kurtarma() -> bool:
    """Panel kapanirsa yarida kalan is SESSIZCE YENIDEN KOSTURULMAZ.

    O is calisma alanina dosya YAZMIS olabilir; yeniden kosturmak ayni dosyayi ikinci kez
    ezmek demektir. 'yarim' isaretlenir, karar kullanicinin."""
    k, s, ev = _kuyruk()
    k.ekle({"gorev": "bir"}); k.ekle({"gorev": "iki"})
    k.adim()
    assert k.liste()["sayim"]["kosuyor"] == 1

    # panel coktu: ayni ev klasoruyle YENI kuyruk nesnesi
    s2 = Sahte()
    k2 = Kuyruk(ev, s2.calistir, s2.bitti_mi)
    d = k2.liste()
    assert d["sayim"]["yarim"] == 1, d["sayim"]
    assert d["sayim"]["kosuyor"] == 0, "yarim kalan is hala kosuyor gorunuyor"
    yarim = [o for o in d["ogeler"] if o["durum"] == "yarim"][0]
    assert "yeniden kosturulmadi" in yarim["sebep"], yarim
    # sonraki is normal devam eder
    assert k2.adim() == "baslatildi"
    assert [g for _, g in s2.baslatilan] == ["iki"], "yarim kalan is TEKRAR kosturuldu"

    # bozuk kuyruk dosyasi COKMEZ
    with open(os.path.join(ev, "kuyruk.json"), "w", encoding="utf-8") as f:
        f.write("{yarim json")
    k3 = Kuyruk(ev, s2.calistir, s2.bitti_mi)
    assert k3.liste()["ogeler"] == [], "bozuk dosya kuyrugu cokertti"
    print("cokme kurtarma: ok (yarim is tekrar kosmaz, bozuk dosya cokertmez)")
    return True


def hata_kuyrugu_kilitlemez() -> bool:
    """Baslatilamayan is kuyrugu KILITLEMEZ - isaretlenir, sira ilerler."""
    k, s, _ = _kuyruk(patlayanlar={"bozuk"})
    k.ekle({"gorev": "bozuk"}); k.ekle({"gorev": "saglam"})
    assert k.adim() == "hata"
    o = k.liste()["ogeler"][0]
    assert o["durum"] == "hata" and "model yuklenemedi" in o["sebep"], o
    assert k.adim() == "baslatildi", "hatadan sonra kuyruk ilerlemedi"
    assert [g for _, g in s.baslatilan] == ["saglam"], s.baslatilan

    # calistir ISTISNA firlatirsa da kuyruk olmez
    def patlak(istek):
        raise RuntimeError("baglanti koptu")
    k2 = Kuyruk(tempfile.mkdtemp(), patlak, lambda j: False)
    k2.ekle({"gorev": "x"})
    assert k2.adim() == "hata"
    assert "baglanti koptu" in k2.liste()["ogeler"][0]["sebep"]
    print("hata kuyrugu kilitlemez: ok")
    return True


def politika_durdurur() -> bool:
    """Politika 'dur' derse kuyruk DURAKLATILIR - ayni hata 12 kez tekrarlanmaz."""
    gorulen = []

    def politika(oge, kuyruk):
        gorulen.append(oge["baslik"])
        return "dur" if oge["baslik"] == "kotu" else "devam"

    k, s, _ = _kuyruk(politika=politika)
    k.ekle({"gorev": "iyi"}); k.ekle({"gorev": "kotu"}); k.ekle({"gorev": "sonraki"})
    k.adim(); s.bitir("is1"); k.adim()
    assert not k.liste()["duraklatildi"], "iyi isten sonra kuyruk durdu"
    k.adim(); s.bitir("is2"); k.adim()
    d = k.liste()
    assert d["duraklatildi"], "politika 'dur' dedi ama kuyruk devam etti"
    assert k.adim() == "bosta", "duraklatilmis kuyruk sonrakini baslatti"
    assert len(s.baslatilan) == 2, s.baslatilan
    assert gorulen == ["iyi", "kotu"], gorulen

    # POLITIKA PATLARSA kuyruk durmaz (politika bir yardimci, tek nokta arizasi degil)
    def patlak_politika(oge, kuyruk):
        raise ValueError("politika bozuk")
    k2, s2, _ = _kuyruk(politika=patlak_politika)
    k2.ekle({"gorev": "a"}); k2.ekle({"gorev": "b"})
    k2.adim(); s2.bitir("is1"); k2.adim()
    assert not k2.liste()["duraklatildi"], "patlayan politika kuyrugu durdurdu"
    assert k2.adim() == "baslatildi"
    print("politika: ok (dur karari uygulanir, patlayan politika kuyrugu durdurmaz)")
    return True


def kalicilik() -> bool:
    """Kuyruk diske ATOMIK yazilir ve yeniden okunur."""
    k, s, ev = _kuyruk()
    k.ekle({"gorev": "bir", "ortam": "code"}, baslik="Elle baslik")
    yol = os.path.join(ev, "kuyruk.json")
    assert os.path.isfile(yol), "kuyruk diske yazilmadi"
    assert not os.path.exists(yol + ".gecici"), "gecici dosya birakildi"
    with open(yol, encoding="utf-8") as f:
        d = json.load(f)
    assert d["sema"] == 1 and len(d["ogeler"]) == 1
    assert d["ogeler"][0]["baslik"] == "Elle baslik"
    assert d["ogeler"][0]["istek"]["ortam"] == "code", "istek kaybolmus"

    k2 = Kuyruk(ev, s.calistir, s.bitti_mi)
    assert len(k2.liste()["ogeler"]) == 1
    # temizle: bitmisler dususur, bekleyen kalir
    k2.ekle({"gorev": "iki"})
    k2.adim(); s.bitir("is1"); k2.adim()
    r = k2.temizle()
    assert r["silinen"] == 1, r
    assert k2.liste()["sayim"]["bekliyor"] == 1
    print("kalicilik: ok (atomik yazim, yeniden okuma, temizleme)")
    return True


def main() -> int:
    ok = (sira_ve_tek_is() and duraklatma() and silme_ve_sira_degistirme()
          and cokme_kurtarma() and hata_kuyrugu_kilitlemez() and politika_durdurur()
          and kalicilik())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

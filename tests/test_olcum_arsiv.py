"""OLCUM ARSIVI testi (core/olcum_arsiv.py).

YASANDI: kampanyalar sonucu `tests/<ad>.son.json`'a yaziyordu ve her kosu oncekini
EZIYORDU. 2026-08-23 temel cizgisi (6 gorev, 8 tur, 2416 sn) 2026-08-25 kosusuyla
(883 sn) degistirildi; aradaki 2.39 katlik farkin sebebi olculemez oldu - kiyas noktasi
silinmisti. Olcum iddiasindaki bir projede kabul edilemez.

Cakilan sozlesme: ARSIV ASLA EZILMEZ.
"""
from __future__ import annotations
import json, os, re, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import core.olcum_arsiv as O  # noqa: E402


def _temiz_kok(ad: str) -> str:
    """Her kosu TEMIZ klasorle baslar. Yoksa onceki kosunun arsivi birikir ve sayimlar
    kayar - test flaky olur (yasandi: ikinci kosuda "2 kosu" beklerken 4 buldu)."""
    kok = os.path.join(ROOT, ".apprentice_test_home", ad)
    shutil.rmtree(kok, ignore_errors=True)
    os.makedirs(os.path.join(kok, "tests"), exist_ok=True)
    return kok


def _kampanya(baslangic: str, sureler: list, gizli=None) -> dict:
    """Kampanya cikti semasi (code_kampanya bicimi)."""
    return {"baslangic": baslangic, "gorevler": {
        "g%d" % i: {"turlar": [{"tur": 1, "sure": s,
                                "gizli_gecen": (gizli or [6] * len(sureler))[i],
                                "gizli_toplam": 6}]}
        for i, s in enumerate(sureler)}}


def arsiv_ezilmez() -> bool:
    """Ayni ad, ayni saniye: ARSIVDE IKI DOSYA olur. Sessiz ezme YOK."""
    kok = _temiz_kok("olcum_unit")
    eski_arsiv, eski_kok = O.ARSIV, O.ROOT
    O.ARSIV = os.path.join(kok, "arsiv")
    O.ROOT = kok
    try:
        t = time.time()
        a = O.kaydet("dene", _kampanya("2026-08-23 01:00:00", [100, 200]), t)
        b = O.kaydet("dene", _kampanya("2026-08-23 01:00:00", [300]), t)   # AYNI saniye
        assert a["arsiv"] != b["arsiv"], "ayni saniyedeki ikinci kosu oncekini EZDI"
        assert os.path.isfile(a["arsiv"]) and os.path.isfile(b["arsiv"])
        # SON dosyasi guncellenir (kolay erisim), arsiv birikir
        with open(a["son"], encoding="utf-8") as f:
            assert len((json.load(f).get("gorevler") or {})) == 1, "son dosyasi guncellenmedi"
        assert len(O.kosular("dene")) == 2, O.kosular("dene")

        # ad temizlenir: yol kacisi dosya adina giremez
        c = O.kaydet("../../kotu", _kampanya("2026-08-23 02:00:00", [10]), t)
        assert os.path.dirname(os.path.abspath(c["arsiv"])) == os.path.abspath(O.ARSIV), c
        print("arsiv ezilmez: ok (ayni saniyede iki kosu, yol kacisi temizlendi)")
        return True
    finally:
        O.ARSIV, O.ROOT = eski_arsiv, eski_kok


def kiyas_dogru() -> bool:
    """Ozet sayilari iki kampanya semasindan da dogru okunmali (sure / sure_s, gizli)."""
    kok = _temiz_kok("olcum_kiyas")
    eski_arsiv, eski_kok = O.ARSIV, O.ROOT
    O.ARSIV = os.path.join(kok, "arsiv")
    O.ROOT = kok
    try:
        O.kaydet("k", _kampanya("2026-08-23 01:00:00", [300, 302], [5, 6]),
                 time.mktime(time.strptime("2026-08-23 01:00:00", "%Y-%m-%d %H:%M:%S")))
        # zorluk bicimi: sure_s + "gizli": "11/12"
        zor = {"baslangic": "2026-08-25 04:00:00", "gorevler": {
            "dama": {"turlar": [{"tur": 1, "sure_s": 135.0, "gizli": "11/12"},
                                {"tur": 2, "sure_s": 271.0, "gizli": "11/12"}]}}}
        O.kaydet("k", zor, time.mktime(time.strptime("2026-08-25 04:00:00", "%Y-%m-%d %H:%M:%S")))
        ks = O.kosular("k")
        assert len(ks) == 2, ks
        assert ks[0]["baslangic"].startswith("2026-08-23"), "kosular ESKIDEN YENIYE siralanmali"
        assert ks[0]["tur"] == 2 and ks[0]["toplam_sn"] == 602, ks[0]
        assert ks[0]["gizli"] == "11/12", ks[0]           # tek turluk gorevler: 5+6 / 6+6
        assert ks[1]["tur"] == 2 and ks[1]["toplam_sn"] == 406, ks[1]
        # DENEME ile SONUC AYRI: dama iki tur kostu, ikisi de 11/12. Turlari TOPLAMAK
        # (22/24) kampanyanin kendi raporuyla celisiyordu - ayni kosu icin iki farkli sayi.
        assert ks[1]["gizli"] == "11/12", ks[1]           # SON tur (dizge bicim de okunuyor)
        assert ks[1]["gizli_ilk"] == "11/12", ks[1]       # ILK deneme
        assert ks[1]["tur_basi_sn"] == 203.0, ks[1]
        # zorluk kampanyasi "zaman" anahtari kullanir - "?" gorunmemeli
        O.kaydet("z", {"zaman": "2026-08-25 14:11:02", "gorevler": {
            "a": {"turlar": [{"tur": 1, "sure_s": 10.0, "gizli": "4/12"},
                             {"tur": 2, "sure_s": 20.0, "gizli": "12/12"}]}}},
                 time.mktime(time.strptime("2026-08-25 14:11:02", "%Y-%m-%d %H:%M:%S")))
        z = O.kosular("z")[0]
        assert z["baslangic"].startswith("2026-08-25"), "zaman anahtari okunmadi: %s" % z
        assert z["gizli_ilk"] == "4/12" and z["gizli"] == "12/12", z

        # bos/bozuk arsiv dosyasi listeyi BOZMAZ
        with open(os.path.join(O.ARSIV, "k-bozuk.json"), "w", encoding="utf-8") as f:
            f.write("{yarim")
        assert len(O.kosular("k")) == 2, "bozuk dosya listeyi bozdu"
        assert O.kosular("olmayan_kampanya") == []
        print("kiyas dogru: ok (iki sema, siralama, bozuk dosya atlandi)")
        return True
    finally:
        O.ARSIV, O.ROOT = eski_arsiv, eski_kok


def kampanyalar_arsivliyor() -> bool:
    """Kampanyalar arsive YAZMALI - yoksa kural kagit uzerinde kalir."""
    for ad in ("code_kampanya", "zorluk_kampanya"):
        with open(os.path.join(ROOT, "tests", "%s.py" % ad), encoding="utf-8") as f:
            s = f.read()
        # ice aktarma satiri baska adlar da tasiyabilir (kampanya_cikis eklendi) - TAM
        # SATIR aramak testi ice aktarma bicimine bagliyor, davranisa degil.
        assert re.search(r"from core\.olcum_arsiv import .*\bkaydet\b", s), \
            "%s arsive yazmiyor" % ad
        assert 'kaydet("%s"' % ad in s, "%s yanlis adla arsivliyor" % ad
        # cikis kodu SONUCU yansitmali (bkz. cikis_kodu_sozlesmesi)
        assert re.search(r"from core\.olcum_arsiv import .*\bkampanya_cikis\b", s) \
            and "kampanya_cikis(" in s, "%s cikis kodunu kosulsuz donuyor" % ad
    print("kampanyalar arsivliyor: ok")
    return True


def cikis_kodu_sozlesmesi() -> bool:
    """Kampanya cikis kodu SONUCU yansitmali (denetim bulgusu #3).

    Kampanyalar KOSULSUZ 0 donuyordu: gizli kontroller 11/12 kalsa bile gozetimsiz gece
    raporu "GECTI" yaziyordu - basarisizlik BASARI gibi gorunuyordu. Uc degerli olmasi
    sart: "model gorevi cozemedi" bir OLCUM SONUCU, "harness patladi" bir ARIZA."""
    assert O.kampanya_cikis(12, 12) == O.CIKIS_TAMAM
    assert O.kampanya_cikis(11, 12) == O.CIKIS_EKSIK, "eksik kosu basari sayildi"
    assert O.kampanya_cikis(0, 12) == O.CIKIS_EKSIK
    # olculecek kontrol YOKSA bu basari degil ARIZADIR - kampanya bir sey kosmamis demektir
    assert O.kampanya_cikis(0, 0) == O.CIKIS_HATA, "bos kosu basari sayildi"
    assert O.kampanya_cikis(0, -1) == O.CIKIS_HATA
    # uc deger BIRBIRINDEN AYRI olmali (2'yi 1'e katlamak gece raporunu okunamaz yapar)
    assert len({O.CIKIS_TAMAM, O.CIKIS_EKSIK, O.CIKIS_HATA}) == 3

    # GERCEK kosu verisiyle: 2026-08-25 zorluk kampanyasi 50/51 kalmisti
    yol = os.path.join(ROOT, "tests", "zorluk_kampanya.son.json")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        g = t = 0
        for k in (d.get("gorevler") or {}).values():
            a, b = (str(k["turlar"][-1].get("gizli", "0/0")).split("/") + ["0"])[:2]
            g += int(a or 0); t += int(b or 0)
        if t:
            assert O.kampanya_cikis(g, t) == (O.CIKIS_TAMAM if g >= t else O.CIKIS_EKSIK)
    print("cikis kodu sozlesmesi: ok (tamam/eksik/ariza ayri)")
    return True


def main() -> int:
    ok = (arsiv_ezilmez() and kiyas_dogru() and kampanyalar_arsivliyor()
          and cikis_kodu_sozlesmesi())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""OLCUM ARSIVI testi (core/olcum_arsiv.py).

YASANDI: kampanyalar sonucu `tests/<ad>.son.json`'a yaziyordu ve her kosu oncekini
EZIYORDU. 2026-08-23 temel cizgisi (6 gorev, 8 tur, 2416 sn) 2026-08-25 kosusuyla
(883 sn) degistirildi; aradaki 2.39 katlik farkin sebebi olculemez oldu - kiyas noktasi
silinmisti. Olcum iddiasindaki bir projede kabul edilemez.

Cakilan sozlesme: ARSIV ASLA EZILMEZ.
"""
from __future__ import annotations
import json, os, shutil, sys, time

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
        assert ks[0]["gizli"] == "11/12", ks[0]           # 5+6 / 6+6
        assert ks[1]["tur"] == 2 and ks[1]["toplam_sn"] == 406, ks[1]
        assert ks[1]["gizli"] == "22/24", ks[1]           # dizge bicim de okunuyor
        assert ks[1]["tur_basi_sn"] == 203.0, ks[1]

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
        assert "from core.olcum_arsiv import kaydet" in s, "%s arsive yazmiyor" % ad
        assert 'kaydet("%s"' % ad in s, "%s yanlis adla arsivliyor" % ad
    print("kampanyalar arsivliyor: ok")
    return True


def main() -> int:
    ok = arsiv_ezilmez() and kiyas_dogru() and kampanyalar_arsivliyor()
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

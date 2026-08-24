"""TELEMETRI + HATA SINIFLANDIRMA testi (core/telemetri.py).

Bu modul yol haritasinin OLCUM tarafi: hangi hata ne siklikta cikiyor, is basina ne
kadar token yaniyor, hangi model gercek islerde ne yapiyor. Testler uc seyi cakar:

  1. Siniflandirici HARNESS'IN GERCEK METINLERINI tanir (hayali desenleri degil).
     Bicimler code_runner.py'den alindi - degisirse bu test kalir, dogrusu budur.
  2. "bilinmeyen" MESRU: zorlama siniflandirma yapilmaz, orani raporlanir.
  3. Sahte/gosterim isleri (kaynak="ornek") OLCUME GIRMEZ; kucuk orneklem SOYLENIR.
"""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.telemetri import is_telemetri, sinifla, siniflar, toplu  # noqa: E402

# (metin, beklenen sinif) - hepsi harness'in GERCEKTEN urettigi bicimler
GERCEK = [
    ("hesap.py(12): SyntaxError: invalid syntax",                  "sozdizimi"),
    ("HATA hesap.py satir 12: unexpected indent",                  "sozdizimi"),
    ("x.py:1:1: E999 SyntaxError",                                 "sozdizimi"),
    ("hesap.py:3:1: F821 Undefined name 'ortalam'",                "tanimsiz_ad"),
    ("t.py: NameError: name 'x' is not defined",                   "tanimsiz_ad"),
    ("hesap.py:1:1: F401 [*] os imported but unused",              "olu_kod"),
    ("a.py:2:5: F841 local variable 'y' assigned but never used",  "olu_kod"),
    ("auth.py: ModuleNotFoundError: No module named requests",     "bagimlilik"),
    ("b.py: ImportError: cannot import name 'X'",                  "bagimlilik"),
    ("DUSTU test_login - AssertionError: ACTIVE != EXPIRED",       "test_beklentisi"),
    ("x.py: TypeError: unsupported operand type(s)",               "tip"),
    ("y.py: AttributeError: 'NoneType' object has no attribute",   "tip"),
    ("z.py: ZeroDivisionError: division by zero",                  "calisma_zamani"),
    ("q.py: KeyError: 'ad'",                                       "calisma_zamani"),
    ("subprocess.TimeoutExpired: command timed out after 120s",    "zaman_asimi"),
    ("DURAGANLIK: ayni test hatalari 2 tur ust uste degismedi",    "duraganlik"),
    ("bir sey oldu ama ne oldugu belli degil",                     "bilinmeyen"),
    ("",                                                           "bilinmeyen"),
]


def _is_yaz(kok: str, jid: str, olaylar: list, kayit: dict) -> None:
    jd = os.path.join(kok, jid)
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False)
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in olaylar:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def siniflandirici() -> bool:
    """Her gercek bicim dogru sinifa dusmeli; emin olunmayan 'bilinmeyen' KALMALI."""
    for metin, beklenen in GERCEK:
        bulunan = sinifla(metin)
        assert bulunan == beklenen, "%r -> %s (beklenen %s)" % (metin[:60], bulunan, beklenen)

    # Cok satirli blok: BILGI satiri (test sayimi) istatistigi kirletmemeli
    blok = ("pytest testleri: 14/15\n"
            "DUSTU test_login_refresh - AssertionError: ACTIVE != EXPIRED [AYNI]")
    assert siniflar([blok]) == ["test_beklentisi"], siniflar([blok])
    # Hicbiri siniflanmiyorsa bilinmeyen KALIR (oran olcum)
    assert siniflar(["anlasilmaz bir sey"]) == ["bilinmeyen"]
    assert siniflar([]) == []
    print("siniflandirici: ok (%d gercek bicim, bilgi satiri eleniyor)" % len(GERCEK))
    return True


def is_kaydi() -> bool:
    """Tek isin olcum kaydi: ilk tur basarisi, onarim turlari, tur basina hata SINIFI."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "onarimli", [
        {"type": "write", "path": "a.py", "before": "", "after": "x = 1\n"},
        {"type": "onarim", "tur": 1,
         "mesaj": "a.py(1): SyntaxError: invalid syntax"},
        {"type": "onarim", "tur": 2,
         "mesaj": "pytest testleri: 3/4\nDUSTU test_a - AssertionError: 1 != 2"},
        {"type": "result", "ok": True, "errors": [], "rounds": 2, "wall": 90.0,
         "kullanim": {"prompt_tokens": 12000, "gen_tokens": 1500, "model_cagrisi": 6}},
    ], {"id": "onarimli", "durum": "bitti", "model": "m1", "kaynak": "web-panel"})
    r = is_telemetri(d, "onarimli")
    assert r["ilk_tur_gecti"] is False and r["gecti"] is True, r
    assert r["onarim_turu"] == 2, r
    assert [t["sinif"] for t in r["turlar"]] == ["sozdizimi", "test_beklentisi"], r["turlar"]
    assert r["istem_tok"] == 12000 and r["uretim_tok"] == 1500, r
    assert r["kaynak"] == "web-panel" and r["model"] == "m1", r

    _is_yaz(d, "ilk_turda", [
        {"type": "write", "path": "a.py", "before": "", "after": "x = 1\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "wall": 20.0},
    ], {"id": "ilk_turda", "durum": "bitti", "model": "m1"})
    assert is_telemetri(d, "ilk_turda")["ilk_tur_gecti"] is True

    _is_yaz(d, "kalan", [
        {"type": "result", "ok": False, "rounds": 1,
         "errors": ["t.py: ModuleNotFoundError: No module named yok"]},
    ], {"id": "kalan", "durum": "bitti", "model": "m1"})
    k = is_telemetri(d, "kalan")
    assert k["gecti"] is False and k["son_hata_siniflari"] == ["bagimlilik"], k
    print("is kaydi: ok (ilk tur, onarim turlari, tur basina sinif)")
    return True


def toplu_olcum() -> bool:
    """Toplu sayilar + ORNEK isleri eleme + kucuk orneklem uyarisi."""
    d = tempfile.mkdtemp()
    for i in range(4):                      # 4 gercek is: 3 ilk turda gecti, 1 duragan
        _is_yaz(d, "is%d" % i, [
            {"type": "write", "path": "a.py", "before": "", "after": "x=1\n"},
            {"type": "result", "ok": True, "errors": [], "rounds": 0, "wall": 10.0,
             "kullanim": {"prompt_tokens": 1000, "gen_tokens": 100}},
        ], {"id": "is%d" % i, "durum": "bitti", "model": "iyi", "kaynak": "web-panel"})
    _is_yaz(d, "is9", [
        {"type": "write", "path": "a.py", "before": "", "after": "x=1\n"},
        {"type": "onarim", "tur": 1, "mesaj": "a.py(1): SyntaxError: bad"},
        {"type": "onarim", "tur": 2, "mesaj": "a.py(1): SyntaxError: bad"},
        {"type": "duraganlik", "imza_sayisi": 1, "tur": 2},
        {"type": "result", "ok": False, "errors": ["a.py(1): SyntaxError: bad"], "rounds": 2,
         "wall": 50.0, "kullanim": {"prompt_tokens": 5000, "gen_tokens": 500}},
    ], {"id": "is9", "durum": "bitti", "model": "kotu", "kaynak": "mcp"})
    # gosterim isi: OLCUME GIRMEMELI
    _is_yaz(d, "isX", [
        {"type": "result", "ok": False, "errors": ["uydurma"], "rounds": 9, "wall": 999.0},
    ], {"id": "isX", "durum": "bitti", "model": "sahte", "kaynak": "ornek"})

    o = toplu(d)
    assert o["n"] == 5, o["n"]                       # ornek elendi
    assert o["ornek_atlandi"] == 1, o
    assert "sahte" not in o["modeller"], "ornek is model kiyasina karismis"
    assert o["ilk_tur_basari"] == 80.0, o["ilk_tur_basari"]
    assert o["onarim_sonrasi_basari"] == 80.0, o
    assert o["duraganlik"] == 20.0 and o["devir_onerisi"] == 20.0, o
    assert o["hata_siniflari"].get("sozdizimi") == 3, o["hata_siniflari"]
    assert o["modeller"]["iyi"]["basari_yuzde"] == 100.0
    assert o["modeller"]["kotu"]["basari_yuzde"] == 0.0
    assert o["ort_istem_tok"] == 1800, o["ort_istem_tok"]   # (1000*4 + 5000) / 5
    assert "uyari" in o, "kucuk orneklem uyarisi yok - 5 is uzerinden yuzde konusulur"

    # taksonomi uyarisi: siniflanamayan oran yuksekse SOYLENMELI
    d2 = tempfile.mkdtemp()
    _is_yaz(d2, "a", [
        {"type": "onarim", "tur": 1, "mesaj": "anlasilmaz sey"},
        {"type": "result", "ok": True, "errors": [], "rounds": 1},
    ], {"id": "a", "durum": "bitti", "model": "m"})
    o2 = toplu(d2)
    assert o2["bilinmeyen_orani"] == 100.0, o2
    assert "taksonomi_uyarisi" in o2, "siniflanamayan oran yuksekken uyari yok"

    assert toplu(os.path.join(d, "yok_boyle_klasor")).get("hata")
    print("toplu olcum: ok (ornek elendi, kucuk orneklem + taksonomi uyarisi var)")
    return True


def main() -> int:
    ok = siniflandirici() and is_kaydi() and toplu_olcum()
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

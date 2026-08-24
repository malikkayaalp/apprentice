"""INCELEME SOZLESMESI testi (core/inceleme.py).

Bu sozlesme runtime ile arayuz arasindaki KARARLI katman: bugun duz olay akisindan
uretiliyor, yarin dugum tabanli orkestratorden uretilecek - panel degismeyecek. Bu yuzden
testler ALANLARIN ANLAMINI cakar, uretim yolunu degil.

Uc kural denetlenir:
  1. Karar KAYITTAN okunur, burada HESAPLANMAZ (duraganligi runtime yazar).
  2. Beyan ile kanit ayridir; hesaplanamayan etiket (ornegin "risk") URETILMEZ.
  3. Geri alinabilirlik ISPATLANIR: `run_shell` calisma alanini olay gunlugune girmeden
     degistirebilir (code_runner.py:252 - dogrudan shell(), write olayi basmaz), o yuzden
     kabuk kosan iste geri alma MUMKUN DEGIL denir ve sebebi yazilir.
"""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:      # pencereli exe/pythonw: sys.stdout None olabilir
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.inceleme import SEMA, inceleme  # noqa: E402

# V0, V1'den SATIR SAYISIYLA da farkli olmali. Yoksa "ilk once -> son sonra" ile "son turun
# farki" ayni sayiyi verir ve test iki uygulamayi AYIRT EDEMEZ - test gecer ama hicbir sey
# olcmez (yasandi: gerileme sabotaji kacti, fixture zayifti).
V0 = "def f():\n    return 0\n    # eski\n    # satirlar\n"
V1 = "def f():\n    return 1\n"
V2 = "def f():\n    return 2\n\ndef g():\n    return 3\n"


def _is_yaz(kok: str, jid: str, olaylar: list, kayit: dict) -> None:
    jd = os.path.join(kok, jid)
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False)
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in olaylar:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        f.write("{bozuk json\n")          # cop satir akisi bozmamali


def net_fark() -> bool:
    """Dosya basina NET degisiklik: ilk yazimin ONCESI -> son yazimin SONRASI.

    Tur tur fark degil - kullanicinin sordugu soru 'bu is dosyayi ne yapti'. Ayni dosya
    onarim turlarinda birkac kez yazilir; ara turlarin toplami yaniltir."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "iki_tur", [
        {"type": "write", "path": "src/a.py", "before": V0, "after": V1},
        {"type": "write", "path": "src/a.py", "before": V1, "after": V2},
        {"type": "result", "ok": True, "errors": [], "rounds": 1},
    ], {"id": "iki_tur", "yazilabilir": ["src/"], "durum": "bitti"})
    f = inceleme(d, "iki_tur")["degisen_dosyalar"][0]
    # V0 -> V2 = (4, 3).  Son turun farki (V1 -> V2) olsaydi (4, 1) cikardi - AYIRT EDICI.
    assert (f["eklenen"], f["silinen"]) == (4, 3), f
    assert f["surum"] == 2 and f["yeni"] is False, f

    _is_yaz(d, "yeni", [{"type": "write", "path": "src/b.py", "before": "", "after": V2},
                        {"type": "result", "ok": True, "errors": [], "rounds": 0}],
            {"id": "yeni", "yazilabilir": ["src/"], "durum": "bitti"})
    g = inceleme(d, "yeni")["degisen_dosyalar"][0]
    assert (g["eklenen"], g["silinen"], g["yeni"]) == (5, 0, True), g
    print("net fark: ok (ilk once -> son sonra; yeni dosya isaretli)")
    return True


def geri_alma_ispati() -> bool:
    """run_shell kostuysa geri alma MUMKUN DEGIL - calismayan dugme koymayalim."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "kabuk", [
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "tool", "name": "run_shell", "detail": "python olustur.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "kabuk", "durum": "bitti"})
    g = inceleme(d, "kabuk")["geri_alinabilir"]
    assert g["mumkun"] is False, g
    assert "run_shell" in g["sebep"], g          # sebep GORUNUR olmali, sessizce gizlenmemeli

    _is_yaz(d, "temiz", [
        {"type": "system", "subtype": "tools_off", "tools": ["run_shell", "run_tests"]},
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "temiz", "durum": "bitti"})
    t = inceleme(d, "temiz")["geri_alinabilir"]
    assert t["mumkun"] is True and "run_shell" in t["sebep"], t   # kapali oldugu YAZILI

    _is_yaz(d, "bos", [{"type": "result", "ok": True, "errors": [], "rounds": 0}],
            {"id": "bos", "durum": "bitti"})
    assert inceleme(d, "bos")["geri_alinabilir"]["mumkun"] is False
    print("geri alma ispati: ok (kabuk kostuysa red, kapaliysa izin, yazim yoksa red)")
    return True


def devir_kanitla() -> bool:
    """Devir ONERISI runtime'in karari; burasi kanitini tasir, KENDI hesaplamaz."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "duragan", [
        {"type": "write", "path": "a.py", "before": V1, "after": V2},
        {"type": "onarim", "tur": 2},
        {"type": "duraganlik", "imza_sayisi": 1, "tur": 2},
        {"type": "result", "ok": False, "errors": ["test_login: Expected ACTIVE, got EXPIRED"],
         "ruff": ["F401 kullanilmayan import"], "rounds": 2, "duragan": True},
    ], {"id": "duragan", "durum": "bitti", "yazilabilir": ["src/"]})
    r = inceleme(d, "duragan")
    assert r["devir_onerisi"]["var"] is True
    assert r["devir_onerisi"]["sebep"] == "duraganlik", r["devir_onerisi"]
    assert r["devir_onerisi"]["kanit"], "kanitsiz devir onerisi = beyan"
    assert "EXPIRED" in r["devir_onerisi"]["son_hata"]
    assert r["onarim_turu"] == 2 and r["duraganlik"]["var"] is True

    # duraganlik olayi YOKSA burasi duraganlik URETMEZ (karar motoru degiliz)
    _is_yaz(d, "duragansiz", [
        {"type": "write", "path": "src/a.py", "before": V1, "after": V2},
        {"type": "onarim", "tur": 2},
        {"type": "result", "ok": True, "errors": [], "rounds": 2},
    ], {"id": "duragansiz", "durum": "bitti", "yazilabilir": ["src/"]})
    r2 = inceleme(d, "duragansiz")
    assert r2["duraganlik"]["var"] is False and r2["devir_onerisi"]["var"] is False, r2
    print("devir kaniti: ok (kanit kayittan gelir, uretilmez)")
    return True


def kapsam_ve_dogrulama() -> bool:
    """Yazma kapsami bir GUVENLIK yuzeyi: kapsam disina yazim dogrulama satiri olarak duser."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "tasma", [
        {"type": "write", "path": "src/a.py", "before": "", "after": V1},
        {"type": "write", "path": "gizli/b.py", "before": "", "after": V1},
        {"type": "result", "ok": True, "errors": [], "ruff": None, "rounds": 0},
    ], {"id": "tasma", "durum": "bitti", "yazilabilir": ["src/"]})
    r = inceleme(d, "tasma")
    disi = [x["yol"] for x in r["degisen_dosyalar"] if x["kapsam_disi"]]
    assert disi == ["gizli/b.py"], disi
    kap = [x for x in r["dogrulama"] if x["ad"] == "yazma kapsami"][0]
    assert kap["durum"] == "kaldi" and "1" in kap["kanit"], kap

    # kapsam SINIRSIZ ise "gecti" denmez - "yok" denir (olculmedi, iddia edilmez)
    _is_yaz(d, "sinirsiz", [{"type": "write", "path": "x.py", "before": "", "after": V1},
                            {"type": "result", "ok": True, "errors": [], "rounds": 0}],
            {"id": "sinirsiz", "durum": "bitti", "yazilabilir": []})
    r2 = inceleme(d, "sinirsiz")
    assert [x for x in r2["dogrulama"] if x["ad"] == "yazma kapsami"][0]["durum"] == "yok"
    assert r2["yazma_kapsami"]["sinirli"] is False

    # eski/bozuk kayit: ruff DIZGE gelirse harf harf gezilmemeli
    _is_yaz(d, "ruffdizge", [{"type": "write", "path": "x.py", "before": "", "after": V1},
                             {"type": "result", "ok": True, "errors": [], "ruff": "temiz",
                              "rounds": 0}], {"id": "ruffdizge", "durum": "bitti"})
    assert inceleme(d, "ruffdizge")["uyarilar"] == ["temiz"]
    print("kapsam + dogrulama: ok (tasma yakalandi, sinirsiz 'gecti' demiyor)")
    return True


def beyan_kanittan_ayri() -> bool:
    """Modelin kendi ozeti KANIT DEGILDIR: ayri alanda durur, dogrulamaya karismaz.
    Ayrica hesaplanamayan etiket (risk vb.) uretilmez."""
    d = tempfile.mkdtemp()
    _is_yaz(d, "beyan", [
        {"type": "assistant", "text": "Her sey mukemmel calisiyor, testler gecti."},
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "result", "ok": False, "errors": ["SyntaxError"], "rounds": 0},
    ], {"id": "beyan", "durum": "bitti"})
    r = inceleme(d, "beyan")
    assert "mukemmel" in r["beyan"], "modelin beyani tasinmali"
    derleme = [x for x in r["dogrulama"] if x["ad"] == "derleme"][0]
    assert derleme["durum"] == "kaldi", "beyan dogrulamayi EZMEMELI"
    ham = json.dumps(r, ensure_ascii=False).lower()
    assert "risk" not in ham, "hesaplanamayan risk etiketi uretilmis"
    assert r["sema"] == SEMA and isinstance(r["sema"], int)
    assert inceleme(d, "olmayan_is").get("hata"), "olmayan is hata vermeli"
    print("beyan/kanit ayrimi: ok (beyan dogrulamayi ezmiyor, risk etiketi yok)")
    return True


def uc_baglandi() -> bool:
    """Panel bu sozlesmeyi bir uctan sunmali (arayuz olay dosyasini dogrudan okumasin)."""
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        s = f.read()
    assert '"/api/inceleme"' in s, "panel /api/inceleme ucunu sunmuyor"
    assert "from core.inceleme import inceleme" in s, "panel sozlesmeyi kullanmiyor"
    print("uc baglandi: ok (/api/inceleme)")
    return True


def main() -> int:
    ok = (net_fark() and geri_alma_ispati() and devir_kanitla() and kapsam_ve_dogrulama()
          and beyan_kanittan_ayri() and uc_baglandi())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

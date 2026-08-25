"""AYARLAR / KESILME / KALICILIK testi - denetim bulgulari 4, 5, 10.

BULGU 4: `apprentice.config.template.json` bir `sampling` bolumu reklam ediyordu
(temperature, think, num_predict, max_steps, retries) ama HICBIRI okunmuyordu;
`code_runner` degerleri koda gomulu tutuyordu. `prompt.ek_talimat` de oyleydi. Sessizce
yok sayilan bir ayar, OLMAYAN bir ayardan KOTUDUR: kullanici degistirdigini sanir.

BULGU 5: `core/client.py` baglam kesilmesini tespit edip `LoopResult.truncated_steps`
uretiyordu ama `code_runner` bunu HIC OKUMUYORDU - hicbir rapora, hicbir panele
ulasmiyordu. Canli/XML yolunda ise tespit HIC YOKTU: ayni is, hangi kipte kostuguna gore
farkli guvence veriyordu.

BULGU 10: kuyruk yazma hatasi `except OSError: pass` ile yutuluyordu - panel "eklendi"
diyor, disk yazilmamis oluyordu. Bozuk kuyruk dosyasi da sessizce BOS kuyruga donuyor ve
ilk yazimda uzerine yazilarak veri kalici kayboluyordu.
"""
from __future__ import annotations
import json, os, stat, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "envs", "code"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.ayarlar import VARSAYILAN, ek_talimat, etkin  # noqa: E402
from core.kuyruk import Kuyruk  # noqa: E402


class Cfg:
    def __init__(self, d):
        self._d = d

    def get(self, k, varsayilan=None):
        if k in self._d:
            return self._d[k]
        p = self._d
        for parca in k.split("."):
            if not isinstance(p, dict) or parca not in p:
                return varsayilan
            p = p[parca]
        return p


def ayarlar_gercekten_okunuyor() -> bool:
    """Yapilandirma degerleri ETKIN degere ulasmali ve KAYNAGI gorunmeli."""
    d = etkin(Cfg({"sampling": {"temperature": 0.7, "num_predict": 900, "max_steps": 5}}))
    assert d["deger"]["temperature"] == 0.7, d
    assert d["deger"]["num_predict"] == 900 and d["deger"]["max_steps"] == 5, d
    assert d["kaynak"]["temperature"] == "yapilandirma", d["kaynak"]
    # verilmeyen alan varsayilanda kalir ve KAYNAGI oyle yazar
    assert d["deger"]["retries"] == VARSAYILAN["retries"], d
    assert d["kaynak"]["retries"] == "varsayilan", d["kaynak"]

    # GUVENLI VARSAYILANLAR (kullanici karari): ayar verilmezse bunlar gecerli
    bos = etkin(Cfg({}))
    assert bos["deger"]["temperature"] == 0.0 and bos["deger"]["think"] is False, bos
    assert not bos["uyarilar"], bos
    print("ayarlar gercekten okunuyor: ok (deger + kaynak)")
    return True


def riskli_deger_uyariyor() -> bool:
    """Riskli deger ENGELLENMEZ ama UYARILIR - makine kullanicinin, karar kullanicinin."""
    d = etkin(Cfg({"sampling": {"temperature": 0.9, "think": True}}))
    adlar = {u["ayar"] for u in d["uyarilar"]}
    assert {"temperature", "think"} <= adlar, d["uyarilar"]
    assert d["deger"]["temperature"] == 0.9 and d["deger"]["think"] is True, d
    for u in d["uyarilar"]:
        assert len(u["mesaj"]) > 20, u          # sebep yazili olmali, kuru uyari degil
    # olculmus gerekce mesajda gecmeli
    tm = [u["mesaj"] for u in d["uyarilar"] if u["ayar"] == "think"][0]
    assert "3900" in tm, tm

    # GECERSIZ/SINIR DISI deger: guvenli degere duser ve HATA olarak bildirilir
    b = etkin(Cfg({"sampling": {"temperature": "abc", "max_steps": 9999}}))
    assert b["deger"]["temperature"] == 0.0, b
    assert b["deger"]["max_steps"] <= 200, b
    assert len(b["hatalar"]) == 2, b["hatalar"]
    print("riskli deger uyariyor: ok (engellenmez, sebebiyle bildirilir)")
    return True


def olcum_profili_kilitli() -> bool:
    """Olcum profili yapilandirmayi YOK SAYAR - kiyas tek degiskenli kalsin."""
    eski = os.environ.get("APPRENTICE_OLCUM_PROFILI")
    os.environ["APPRENTICE_OLCUM_PROFILI"] = "1"
    try:
        d = etkin(Cfg({"sampling": {"temperature": 0.9, "think": True, "max_steps": 99}}))
        assert d["deger"] == VARSAYILAN, "olcum profili ayardan etkilendi: %s" % d["deger"]
        assert d["olcum_profili"] is True and not d["uyarilar"], d
        assert set(d["kaynak"].values()) == {"olcum-profili"}, d["kaynak"]
    finally:
        if eski is None:
            os.environ.pop("APPRENTICE_OLCUM_PROFILI", None)
        else:
            os.environ["APPRENTICE_OLCUM_PROFILI"] = eski
    print("olcum profili kilitli: ok")
    return True


def kosucu_ayari_gercek_istege_tasiyor() -> bool:
    """KAYNAK SOZLESMESI: code_runner sabit deger DEGIL, cozulmus ayari gonderir.

    Eski satirlar: `temperature=0.0, num_predict=6000, max_steps=12, retries=2, think=False`
    dogrudan cagrida yaziliydi."""
    with open(os.path.join(ROOT, "envs", "code", "code_runner.py"), encoding="utf-8") as f:
        k = f.read()
    for sabit in ("temperature=0.0", "num_predict=6000", "max_steps=12", "retries=2"):
        assert sabit not in k, "model cagrisinda hala SABIT deger var: %s" % sabit
    for alan in ("max_steps", "think", "temperature", "num_predict", "retries"):
        assert 'ORNEKLEME["%s"]' % alan in k, "%s ayardan beslenmiyor" % alan
    # CANLI yol da ayni ayarlari kullanmali - iki kip ayrilmasin
    canli = k[k.index("def canli_run("):k.index("def _tur_kos(") if "def _tur_kos(" in k else len(k)]
    assert 'ORNEKLEME["think"]' in canli and 'ORNEKLEME["temperature"]' in canli, \
        "canli yol hala sabit ayar kullaniyor"
    assert "EK_TALIMAT" in k and "prompt.ek_talimat" in open(
        os.path.join(ROOT, "core", "ayarlar.py"), encoding="utf-8").read(), \
        "ek_talimat okunmuyor"
    # ETKIN degerler RAPORA girmeli
    assert "ayarlar={" in k and '"olcum_profili"' in k, "etkin ayarlar rapora girmiyor"
    print("kosucu ayari gercek istege tasiyor: ok (iki yol da)")
    return True


def kesilme_gorunur() -> bool:
    """Baglam kesilmesi rapora tasinmali ve CANLI yolda da olculmeli."""
    with open(os.path.join(ROOT, "envs", "code", "code_runner.py"), encoding="utf-8") as f:
        k = f.read()
    assert "truncated_steps" in k, "kesilme sayimi hic okunmuyor"
    assert 'kesilme=' in k, "kesilme result olayina girmiyor"
    assert '"en_buyuk_istem"' in k, "tek istekteki en buyuk baglam ayri olculmuyor"
    canli = k[k.index("def canli_run("):]
    assert "detect_truncation" in canli, "CANLI yolda kesilme tespiti YOK"

    # detect_truncation gercekten calisiyor mu (parmak izi: num_ctx/2)
    from core import tokens as t
    assert t.detect_truncation(16386, 40000, 32768) is True, "gercek kesilme yakalanmadi"
    assert t.detect_truncation(4000, 4200, 32768) is False, "yanlis pozitif"
    print("kesilme gorunur: ok (rapora girer, canli yol da olcer)")
    return True


def kuyruk_yazma_hatasi_gizlenmez() -> bool:
    """Diske YAZILAMAZSA panel 'eklendi' DEMEZ (denetim bulgusu 10)."""
    ev = tempfile.mkdtemp()
    k = Kuyruk(ev, lambda i: {"is_id": "x"}, lambda j: False)
    assert k.ekle({"gorev": "bir"}).get("no") == 1

    # yazmayi PATLAT
    asil = k._yaz
    k._yaz = lambda: "kuyruk diske YAZILAMADI: disk dolu (simule)"
    r = k.ekle({"gorev": "iki"})
    assert r.get("hata"), "yazma basarisizken 'eklendi' dendi: %s" % r
    assert "YAZILAMADI" in r["hata"], r
    k._yaz = asil
    # BELLEK de bozulmamis olmali - basarisiz ekleme geri alinir
    assert len(k.liste()["ogeler"]) == 1, k.liste()["ogeler"]
    assert k.liste()["ogeler"][0]["baslik"] != "iki", k.liste()

    # duraklat/temizle de hatayi bildirir
    k._yaz = lambda: "yazilamadi"
    assert k.duraklat(True).get("hata"), "duraklat hatayi yuttu"
    assert k.temizle().get("hata"), "temizle hatayi yuttu"
    k._yaz = asil

    # GERCEK salt-okunur dosya (Windows'ta da calisir)
    ev2 = tempfile.mkdtemp()
    k2 = Kuyruk(ev2, lambda i: {"is_id": "x"}, lambda j: False)
    k2.ekle({"gorev": "a"})
    os.chmod(k2.yol, stat.S_IREAD)
    try:
        r2 = k2.ekle({"gorev": "b"})
        # bazi sistemlerde replace yine de basarili olabilir; basariliysa dosya GUNCEL olmali
        if r2.get("hata"):
            assert "YAZILAMADI" in r2["hata"], r2
        else:
            with open(k2.yol, encoding="utf-8") as f:
                assert len(json.load(f)["ogeler"]) == 2, "basarili dendi ama disk eski"
    finally:
        os.chmod(k2.yol, stat.S_IWRITE | stat.S_IREAD)
    print("kuyruk yazma hatasi gizlenmez: ok")
    return True


def bozuk_kuyruk_korunur() -> bool:
    """Bozuk kuyruk dosyasi SESSIZCE BOS kuyruga donmez; icerik KORUNUR."""
    ev = tempfile.mkdtemp()
    yol = os.path.join(ev, "kuyruk.json")
    with open(yol, "w", encoding="utf-8") as f:
        f.write('{"sema":1,"ogeler":[{"no":1,"durum":"bekliyor","baslik":"DEGERLI IS"')  # yarim

    k = Kuyruk(ev, lambda i: {"is_id": "x"}, lambda j: False)
    assert k.liste()["ogeler"] == [], "bozuk dosya kuyrugu cokertti"
    assert k.yukleme_hatasi and "OKUNAMADI" in k.yukleme_hatasi, k.yukleme_hatasi
    assert k.liste().get("kalicilik_hatasi"), "hata panele tasinmiyor"

    # BOZUK ICERIK KORUNMUS olmali - uzerine yazilip kaybolmamali
    yedekler = [a for a in os.listdir(ev) if ".bozuk-" in a]
    assert yedekler, "bozuk dosya korunmadi: %s" % os.listdir(ev)
    with open(os.path.join(ev, yedekler[0]), encoding="utf-8") as f:
        assert "DEGERLI IS" in f.read(), "korunan yedek bos"

    # ILK CALISTIRMA (dosya yok) hata DEGILDIR
    k2 = Kuyruk(tempfile.mkdtemp(), lambda i: {}, lambda j: False)
    assert not k2.yukleme_hatasi, k2.yukleme_hatasi
    assert k2.liste().get("kalicilik_hatasi") is None
    print("bozuk kuyruk korunur: ok (yedeklenir, bildirilir, ilk calistirma sessiz)")
    return True


def sablon_ile_kod_uyusuyor() -> bool:
    """Sablonda olup okunmayan ya da okunup sablonda gorunmeyen alan BIRAKMAYIZ."""
    with open(os.path.join(ROOT, "apprentice.config.template.json"), encoding="utf-8") as f:
        t = json.load(f)
    sablon = {k for k in (t.get("sampling") or {}) if not k.startswith("_")}
    assert sablon == set(VARSAYILAN), "sampling: sablon %s vs kod %s" % (sablon, set(VARSAYILAN))
    assert "ek_talimat" in (t.get("prompt") or {}), "prompt.ek_talimat sablonda yok"
    assert ek_talimat(Cfg({"prompt": {"ek_talimat": "  Turkce yaz.  "}})) == "Turkce yaz."
    assert ek_talimat(Cfg({})) == ""
    print("sablon ile kod uyusuyor: ok")
    return True


def main() -> int:
    denemeler = [ayarlar_gercekten_okunuyor, riskli_deger_uyariyor, olcum_profili_kilitli,
                 kosucu_ayari_gercek_istege_tasiyor, kesilme_gorunur,
                 kuyruk_yazma_hatasi_gizlenmez, bozuk_kuyruk_korunur,
                 sablon_ile_kod_uyusuyor]
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

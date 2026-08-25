"""SENARYO TESTLERI: bugun eklenenler, GERCEK DUNYA pisliginde.

Birim testleri temiz girdiyle calisir. Burasi tersini yapar: bozuk kayit, yarim yazilmis
satir, beklenmedik tip, unicode ad, devasa gunluk, ust uste kararlar, yaris benzeri
sirala. Kapsanan bugunku isler:

    core/inceleme.py   INCELEME sozlesmesi + karar kaydi + sahiplik
    core/geri_al.py    geri alma (git + gunluk yolu)
    core/telemetri.py  hata taksonomisi + toplu olcum

KURAL: her senaryo ya DOGRU cevabi verir ya da DURUST bir "bilmiyorum" doner. Patlamak,
sessizce yanlis sayi uretmek ve "olculmedi"yi "gecti" saymak kabul edilmez.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.geri_al import anlik, plan, uygula          # noqa: E402
from core.inceleme import inceleme, karar_oku, karar_yaz  # noqa: E402
from core.telemetri import toplu                       # noqa: E402

PZ = 0x08000000 if os.name == "nt" else 0


def _git(d, *a):
    return subprocess.run(["git", "-C", d] + list(a), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=PZ)


def _is(kok: str, jid: str, olaylar, kayit: dict) -> str:
    jd = os.path.join(kok, jid)
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False)
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in olaylar:
            f.write((e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)) + "\n")
    return jd


def bozuk_kayitlar() -> bool:
    """Gunluk bozuk/yarim/bos olabilir - sozlesme PATLAMAZ, elindekini doner."""
    d = tempfile.mkdtemp()
    senaryolar = {
        "bos": [],
        "yalniz_cop": ["{bozuk", "", "   ", "null", "[]", '{"type":}'],
        "yarim_satir": [{"type": "write", "path": "a.py", "before": "", "after": "x\n"},
                        '{"type": "result", "ok": tr'],           # yazarken kesilmis
        "ikili_cop": ["\x00\x01\x02 bozuk bayt", {"type": "exit", "code": 0}],
        "tip_karisik": [{"type": "write", "path": "a.py", "before": None, "after": None},
                        {"type": "result", "ok": "evet", "errors": "tek dizge",
                         "ruff": {"a": 1}, "rounds": "iki", "kullanim": "yok"}],
        "olay_degil": [{"foo": "bar"}, {"type": None}, {"type": 42}],
    }
    for ad, olaylar in senaryolar.items():
        _is(d, ad, olaylar, {"id": ad, "durum": "bitti"})
        r = inceleme(d, ad)
        assert isinstance(r, dict) and r.get("sema"), "%s: sozlesme donmedi" % ad
        assert isinstance(r.get("degisen_dosyalar"), list), ad
        assert isinstance(r.get("dogrulama"), list) and r["dogrulama"], ad
        for x in r["dogrulama"]:
            assert x["durum"] in ("gecti", "kaldi", "yok"), (ad, x)
        assert isinstance(r.get("devir_onerisi"), dict), ad
        assert isinstance(r.get("uyarilar"), list), ad
        # hesaplanamayan etiket URETILMEZ
        assert "risk" not in json.dumps(r, ensure_ascii=False).lower(), ad

    # job.json bozuk / yok
    jd = _is(d, "kayitsiz", [{"type": "result", "ok": True, "errors": [], "rounds": 0}],
             {"id": "kayitsiz"})
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        f.write("{yarim")
    r = inceleme(d, "kayitsiz")
    assert r.get("sema") and not r.get("hata"), "bozuk job.json sozlesmeyi durdurdu"
    assert inceleme(d, "hic_yok").get("hata"), "olmayan is hata vermeli"
    print("bozuk kayitlar: ok (%d senaryo, hicbiri patlamadi)" % (len(senaryolar) + 2))
    return True


def zor_dosya_adlari() -> bool:
    """Unicode, bosluk, uzun ad, ic ice klasor: net fark ve kapsam dogru calismali."""
    d = tempfile.mkdtemp()
    adlar = ["türkçe/çırak_dosyası.py", "bos luk/a b.py", "emoji_🙂.py",
             "derin/bir/iki/uc/dort/x.py", "UPPER/Mixed.PY", "nokta.li.ad.py",
             "a" * 80 + ".py"]
    olaylar = []
    for i, ad in enumerate(adlar):
        olaylar.append({"type": "write", "path": ad, "before": "" if i % 2 else "eski\n",
                        "after": "yeni %d\n" % i})
    olaylar.append({"type": "result", "ok": True, "errors": [], "rounds": 0})
    _is(d, "adlar", olaylar, {"id": "adlar", "durum": "bitti", "yazilabilir": ["türkçe/", "derin/"]})
    r = inceleme(d, "adlar")
    bulunan = {x["yol"] for x in r["degisen_dosyalar"]}
    assert len(bulunan) == len(adlar), "dosya kayboldu: %s" % (set(adlar) - bulunan)
    for x in r["degisen_dosyalar"]:
        assert x["eklenen"] >= 1, x
        assert isinstance(x["kapsam_disi"], bool), x
    disi = {x["yol"] for x in r["degisen_dosyalar"] if x["kapsam_disi"]}
    assert "türkçe/çırak_dosyası.py" not in disi, "unicode kapsam yolu taninmadi"
    assert "derin/bir/iki/uc/dort/x.py" not in disi, "ic ice klasor kapsam disi sayildi"
    assert "emoji_🙂.py" in disi and "bos luk/a b.py" in disi, disi
    print("zor dosya adlari: ok (%d ad: unicode, bosluk, emoji, derin, uzun)" % len(adlar))
    return True


def buyuk_gunluk() -> bool:
    """5000 olayli gunluk + 20 kez yazilan dosya: dogru ve MAKUL SUREDE."""
    d = tempfile.mkdtemp()
    olaylar = []
    for i in range(2000):
        olaylar.append({"type": "tool", "name": "read_file", "detail": "x%d.py" % i})
        olaylar.append({"type": "tool_result", "name": "read_file", "text": "..." * 40})
    icerik = "satir\n" * 200
    for tur in range(20):                       # AYNI dosya 20 kez yazildi
        olaylar.append({"type": "write", "path": "cok.py",
                        "before": icerik if tur else "",
                        "after": icerik + ("ek %d\n" % tur)})
        olaylar.append({"type": "onarim", "tur": tur + 1, "mesaj": "x.py(1): SyntaxError: bad"})
    olaylar.append({"type": "result", "ok": True, "errors": [], "rounds": 20})
    _is(d, "buyuk", olaylar, {"id": "buyuk", "durum": "bitti"})
    t0 = time.time()
    r = inceleme(d, "buyuk")
    sure = time.time() - t0
    assert sure < 10, "5000 olay %0.1f sn surdu - cok yavas" % sure
    f = r["degisen_dosyalar"][0]
    assert f["surum"] == 20, f
    # NET fark: ilk yazimin oncesi ("") -> son yazim. Ara turlar toplanmaz.
    assert f["yeni"] is True and f["eklenen"] == 201 and f["silinen"] == 0, f
    assert r["onarim_turu"] == 20, r["onarim_turu"]
    print("buyuk gunluk: ok (5000+ olay, 20 surum, %.1f sn)" % sure)
    return True


def geri_alma_zor_durumlar() -> bool:
    """Geri alma: ic ice klasor, silinen dosya, unicode ad, IKI KEZ uygulama."""
    if not shutil.which("git"):
        print("geri alma zor durumlar: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    os.makedirs(os.path.join(wd, "alt", "derin"), exist_ok=True)
    for ad, ic in (("kok.py", "kok eski\n"), ("alt/derin/x.py", "derin eski\n"),
                   ("silinecek.py", "bu silinecek\n"), ("türkçe.py", "unicode\n")):
        with open(os.path.join(wd, ad), "w", encoding="utf-8") as f:
            f.write(ic)
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)
    assert ag["yontem"] == "git" and ag["kirli"] == [], ag

    # cirak: degistir, yarat, SIL
    with open(os.path.join(wd, "kok.py"), "w", encoding="utf-8") as f:
        f.write("kok YENI\n")
    with open(os.path.join(wd, "alt", "derin", "yeni.py"), "w", encoding="utf-8") as f:
        f.write("yeni dosya\n")
    os.remove(os.path.join(wd, "silinecek.py"))

    d = tempfile.mkdtemp()
    _is(d, "is1", [{"type": "write", "path": "kok.py", "before": "kok eski\n", "after": "kok YENI\n"},
                   {"type": "result", "ok": True, "errors": [], "rounds": 0}],
        {"id": "is1", "durum": "bitti", "calisma_dizini": wd, "anlik": ag})
    p = plan(d, "is1")
    eylem = {e["yol"]: e["eylem"] for e in p["eylemler"]}
    assert eylem.get("kok.py") == "geri_yaz", p
    assert eylem.get("alt/derin/yeni.py") == "sil", "ic ice yeni dosya plana girmedi: %s" % p
    assert eylem.get("silinecek.py") == "geri_yaz", "SILINEN dosya geri getirilmiyor: %s" % p

    r = uygula(d, "is1", p)
    assert not r["basarisiz"], r
    with open(os.path.join(wd, "kok.py"), encoding="utf-8") as f:
        assert f.read() == "kok eski\n"
    assert not os.path.exists(os.path.join(wd, "alt", "derin", "yeni.py")), "yeni dosya silinmedi"
    assert os.path.isfile(os.path.join(wd, "silinecek.py")), "silinen dosya GERI GELMEDI"

    # IKINCI kez: yapacak sey kalmamali, patlamamali
    p2 = plan(d, "is1")
    assert p2["mumkun"] is False and not p2["eylemler"], p2
    r2 = uygula(d, "is1", p2)
    assert r2.get("hata") and not r2["yapildi"], r2
    print("geri alma zor durumlar: ok (ic ice, silinen dosya geri geldi, ikinci kez guvenli)")
    return True


def geri_alma_engelleri() -> bool:
    """Salt-okunur dosya ve kaybolan calisma dizini: patlamaz, DURUST rapor eder."""
    wd = tempfile.mkdtemp()
    hedef = os.path.join(wd, "kilitli.py")
    with open(hedef, "w", encoding="utf-8") as f:
        f.write("yeni\n")
    d = tempfile.mkdtemp()
    _is(d, "salt", [{"type": "write", "path": "kilitli.py", "before": "eski\n", "after": "yeni\n"},
                    {"type": "result", "ok": True, "errors": [], "rounds": 0}],
        {"id": "salt", "durum": "bitti", "calisma_dizini": wd, "anlik": {"yontem": "yok"}})
    os.chmod(hedef, 0o444)
    try:
        r = uygula(d, "salt")
        assert isinstance(r, dict), r
        # basarisiz olabilir (izin) ya da basarabilir (Windows sahibe izin verir) - IKISI DE
        # kabul; sart olan PATLAMAMASI ve sonucu DURUSTCE bildirmesi
        assert ("yapildi" in r and "basarisiz" in r) or r.get("hata"), r
    finally:
        os.chmod(hedef, 0o666)

    # calisma dizini plan ile uygulama ARASINDA silinirse
    wd2 = tempfile.mkdtemp()
    with open(os.path.join(wd2, "a.py"), "w", encoding="utf-8") as f:
        f.write("yeni\n")
    d2 = tempfile.mkdtemp()
    _is(d2, "kayip", [{"type": "write", "path": "a.py", "before": "eski\n", "after": "yeni\n"},
                      {"type": "result", "ok": True, "errors": [], "rounds": 0}],
        {"id": "kayip", "durum": "bitti", "calisma_dizini": wd2, "anlik": {"yontem": "yok"}})
    p = plan(d2, "kayip")
    assert p["mumkun"], p
    shutil.rmtree(wd2, ignore_errors=True)
    r = uygula(d2, "kayip", p)          # ELDEKI eski plan uygulaniyor
    assert isinstance(r, dict) and not r.get("yapildi"), "kayip dizinde is yapildigi iddia edildi: %s" % r
    print("geri alma engelleri: ok (salt-okunur ve kayip dizin durustce raporlandi)")
    return True


def karar_dizileri() -> bool:
    """Ust uste kararlar: gecmis birikir ama SINIRLI; her karar dogru okunur."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "is1"), exist_ok=True)
    dizi = ["kabul", "red", "kabul", "red", "kabul", "red", "kabul"]
    for i, k in enumerate(dizi):
        r = karar_yaz(d, "is1", k, {"geri_alinan": i} if k == "red" else {})
        assert r["durum"] == k, r
    son = karar_oku(d, "is1")
    assert son["durum"] == "kabul", son
    onceki = son.get("onceki") or []
    assert 1 <= len(onceki) <= 5, "gecmis sinirsiz buyuyor: %d" % len(onceki)
    assert onceki[-1]["durum"] == "red", onceki      # en yakin gecmis SONDA
    # dosya makul boyutta kalmali (gecmis birikimi dosyayi sisirmemeli)
    boyut = os.path.getsize(os.path.join(d, "is1", "inceleme.json"))
    assert boyut < 4000, "karar dosyasi sisti: %d bayt" % boyut
    print("karar dizileri: ok (%d karar, gecmis %d kayitla sinirli)" % (len(dizi), len(onceki)))
    return True


def telemetri_pislikte() -> bool:
    """Telemetri: karisik/bozuk kullanim alanlari, cok is, hepsi basarisiz."""
    d = tempfile.mkdtemp()
    for i in range(60):
        gecti = i % 3 != 0
        _is(d, "is%03d" % i, [
            {"type": "write", "path": "a.py", "before": "", "after": "x\n"},
            {"type": "onarim", "tur": 1, "mesaj": "a.py(1): SyntaxError: bad"} if not gecti else
            {"type": "tool", "name": "read_file"},
            {"type": "result", "ok": gecti, "errors": [] if gecti else ["a.py: NameError: x"],
             "rounds": 0 if gecti else 1,
             # kullanim alani bilerek KARISIK: dizge, None, eksik, dogru
             "kullanim": ({"prompt_tokens": 1000} if i % 4 == 0 else
                          ("cop" if i % 4 == 1 else (None if i % 4 == 2 else {}))),
             "wall": i},
        ], {"id": "is%03d" % i, "durum": "bitti", "model": "m%d" % (i % 3),
            "kaynak": "web-panel"})
    t0 = time.time()
    o = toplu(d, 200)
    sure = time.time() - t0
    assert sure < 20, "60 is %.1f sn surdu" % sure
    assert o["n"] == 60, o["n"]
    assert 60 <= o["ilk_tur_basari"] <= 70, o["ilk_tur_basari"]     # 40/60
    assert o["hata_siniflari"], "hic hata siniflanmadi"
    assert set(o["hata_siniflari"]) <= {"sozdizimi", "tanimsiz_ad", "bilinmeyen"}, o["hata_siniflari"]
    assert len(o["modeller"]) == 3, o["modeller"]
    assert isinstance(o["ort_istem_tok"], int), o
    assert "uyari" not in o, "60 is icin kucuk orneklem uyarisi cikmamali"
    print("telemetri pislikte: ok (60 is, karisik kullanim tipleri, %.1f sn)" % sure)
    return True


def kullanicinin_agents_dosyasi():
    """`kur.py --kural` KULLANICININ AGENTS.md'sini EZMEMELI (denetim bulgusu #4).

    AGENTS.md bize ait degil: ortak standart dosya (Codex/Copilot/Gemini okur) ve kullanicinin
    kendi proje kurallarini tutar. Onceki surum korlemesine uzerine yaziyordu - bir projeye
    baglanmak, o projenin butun ajan kurallarini SESSIZCE silmek demekti."""
    sys.path.insert(0, ROOT)
    import kur

    d = tempfile.mkdtemp()
    yol = os.path.join(d, "AGENTS.md")
    govde = "## Kural v1\n\nusta dogrular.\n"

    assert kur.agents_birlestir(yol, govde) == "yazildi"
    kur.agents_birlestir(yol, govde)                       # ikinci kosu YIGMAMALI
    with open(yol, encoding="utf-8") as f:
        assert f.read().count(kur.BASI) == 1, "blok yigildi"

    kullanici = "# Benim kurallarim\n\n- main dala push yok\n- testler Turkce\n"
    with open(yol, "w", encoding="utf-8") as f:
        f.write(kullanici)
    durum = kur.agents_birlestir(yol, govde)
    with open(yol, encoding="utf-8") as f:
        ic = f.read()
    assert "eklendi" in durum, durum
    assert kullanici.strip() in ic, "KULLANICININ KURALLARI SILINDI"
    assert "usta dogrular." in ic, "bizim kural yazilmadi"

    # govde degisince bizim blok guncellenir, kullanicinin metni YERINDE kalir
    assert kur.agents_birlestir(yol, "## Kural v2\n\nusta KOSARAK dogrular.\n") == "guncellendi"
    with open(yol, encoding="utf-8") as f:
        ic2 = f.read()
    assert kullanici.strip() in ic2, "guncellemede kullanicinin metni gitti"
    assert "usta dogrular." not in ic2 and "usta KOSARAK dogrular." in ic2, ic2
    assert ic2.count(kur.BASI) == 1, "guncellemede blok yigildi"
    shutil.rmtree(d, ignore_errors=True)
    print("kullanicinin AGENTS.md dosyasi: ok (ezilmiyor, yigilmiyor, guncelleniyor)")


def main() -> int:
    denemeler = [bozuk_kayitlar, zor_dosya_adlari, buyuk_gunluk, geri_alma_zor_durumlar,
                 geri_alma_engelleri, karar_dizileri, telemetri_pislikte,
                 kullanicinin_agents_dosyasi]
    kalan = 0
    for fn in denemeler:
        try:
            fn()
        except AssertionError as e:
            print("SENARYO KALDI - %s: %s" % (fn.__name__, str(e)[:500]))
            kalan += 1
        except Exception as e:  # noqa: BLE001
            print("SENARYO PATLADI - %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:400]))
            kalan += 1
    print("SONUC:", "GECTI" if not kalan else "KALDI (%d senaryo)" % kalan)
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())

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
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:      # pencereli exe/pythonw: sys.stdout None olabilir
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.inceleme import (SEMA, inceleme, kabul_yaz, karar_oku,  # noqa: E402
                           karar_yaz)
from core.telemetri import toplu  # noqa: E402

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
    """Geri alma ISPATLANIR, varsayilmaz. Karar core/geri_al.py'de; sozlesme onu tasir.

    Fixture'lar GERCEK calisma dizini kurar: plan diske bakar (dosya hala isin yazdigi
    halde mi?), sahte klasorle sinanamaz - sinanirsa test hicbir sey olcmez."""
    d = tempfile.mkdtemp()

    def calisma_alani(**dosyalar) -> str:
        wd = tempfile.mkdtemp()
        for ad, ic in dosyalar.items():
            with open(os.path.join(wd, ad), "w", encoding="utf-8") as f:
                f.write(ic)
        return wd

    # 1) KABUK KOSTU + git yok -> MUMKUN DEGIL, sebep GORUNUR (sessizce gizlenmez)
    wd = calisma_alani(**{"a.py": V1})
    _is_yaz(d, "kabuk", [
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "tool", "name": "run_shell", "detail": "python olustur.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "kabuk", "durum": "bitti", "calisma_dizini": wd})
    g = inceleme(d, "kabuk")["geri_alinabilir"]
    assert g["mumkun"] is False, g
    assert "run_shell" in g["sebep"], g

    # 2) KABUK KOSMADI -> olay gunlugu yeter
    wd2 = calisma_alani(**{"a.py": V1})
    _is_yaz(d, "temiz", [
        {"type": "system", "subtype": "tools_off", "tools": ["run_shell", "run_tests"]},
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "temiz", "durum": "bitti", "calisma_dizini": wd2})
    t = inceleme(d, "temiz")["geri_alinabilir"]
    assert t["mumkun"] is True and t["yontem"] == "gunluk", t
    assert t["eylem_sayisi"] == 1, t

    # 3) YAZIM YOK -> geri alinacak sey yok
    wd3 = calisma_alani()
    _is_yaz(d, "bos", [{"type": "result", "ok": True, "errors": [], "rounds": 0}],
            {"id": "bos", "durum": "bitti", "calisma_dizini": wd3})
    assert inceleme(d, "bos")["geri_alinabilir"]["mumkun"] is False

    # 4) IS BITTIKTEN SONRA baskasi degistirmis -> DOKUNULMAZ
    wd4 = calisma_alani(**{"a.py": "BASKASI ELLE DEGISTIRDI\n"})
    _is_yaz(d, "sonradan", [
        {"type": "write", "path": "a.py", "before": V1, "after": V2},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "sonradan", "durum": "bitti", "calisma_dizini": wd4})
    s4 = inceleme(d, "sonradan")["geri_alinabilir"]
    assert s4["mumkun"] is False and s4["atlanan"], s4
    assert "sonra" in s4["atlanan"][0]["sebep"], s4

    # 5) CALISMA DIZINI YOK -> uydurma yapilmaz
    _is_yaz(d, "dizinsiz", [
        {"type": "write", "path": "a.py", "before": "", "after": V1},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"id": "dizinsiz", "durum": "bitti", "calisma_dizini": os.path.join(d, "yok")})
    assert inceleme(d, "dizinsiz")["geri_alinabilir"]["mumkun"] is False
    print("geri alma ispati: ok (kabuk->red, gunluk->izin, sonradan degisen->dokunma)")
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


def karar_kaydi() -> bool:
    """Inceleyenin karari AYRI dosyada durur (tek yazar kurali): events.jsonl'in sahibi
    isi kosan surectir, karar ise inceleyenin sozudur.

    Bu BIRIM testi: HTTP ucu ayrica denetliyor ama gecersiz girdi korumasi burada da
    olmali - iki katman birden bozulmasin diye (savunma derinligi)."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "is1"), exist_ok=True)
    assert karar_oku(d, "is1") == {}, "karar yokken bos sozluk donmeli"

    k = karar_yaz(d, "is1", "kabul", {"not": "olur"})
    assert k["durum"] == "kabul" and k["sema"] == SEMA and k["not"] == "olur", k
    assert karar_oku(d, "is1")["durum"] == "kabul"
    assert os.path.exists(os.path.join(d, "is1", "inceleme.json")), "ayri dosyaya yazilmadi"

    # fikir degistirmek serbest ama GECMIS SILINMEZ
    k2 = karar_yaz(d, "is1", "red", {"geri_alinan": 3})
    assert k2["durum"] == "red" and k2["geri_alinan"] == 3, k2
    assert k2["onceki"] and k2["onceki"][-1]["durum"] == "kabul", k2

    # GECMISE geri_alinan da tasinmali: "daha once reddedilmisti" yetmez, KAC DOSYANIN
    # geri alindigi arayuzde gorunmeli - yoksa kod geri alinmis bir is "kabul edildi"
    # diye gorunur ve kullanici kodun durdugunu sanir (yasandi).
    k3 = karar_yaz(d, "is1", "kabul")
    assert k3["onceki"][-1]["durum"] == "red", k3
    assert k3["onceki"][-1].get("geri_alinan") == 3, "gecmiste kac dosya geri alindigi kayboldu"

    # GECERSIZ girdi: bu katman da reddetmeli
    for kotu in ("sacma", "", None, "KABUL"):
        assert karar_yaz(d, "is1", kotu).get("hata"), "gecersiz karar kabul edildi: %r" % kotu
    assert karar_oku(d, "is1")["durum"] == "kabul", "gecersiz karar mevcut karari bozdu"
    assert karar_oku(d, "is1")["onceki"], "gecersiz karar gecmisi de bozdu"
    assert karar_yaz(d, "olmayan_is", "kabul").get("hata")

    # bozuk dosya: patlamaz, bos doner
    with open(os.path.join(d, "is1", "inceleme.json"), "w", encoding="utf-8") as f:
        f.write("{bozuk")
    assert karar_oku(d, "is1") == {}
    print("karar kaydi: ok (ayri dosya, gecmis korunuyor, gecersiz girdi reddediliyor)")
    return True


def surec_canliligi() -> bool:
    """Sahip surec canli mi? Denetim CREATE_NO_WINDOW ALTINDA da dogru calismali.

    YASANDI: ilk surum os.kill(pid, 0) kullaniyordu. Bu projede her alt surec
    CREATE_NO_WINDOW (0x08000000) ile baslatilir - MS-DOS penceresi acilmasin diye. O
    bayrakla baslatilmis bir Python surecinde os.kill(pid, 0) Windows'ta
    "OSError [WinError 87] The parameter is incorrect" veriyor, KENDI pid'i icin bile.
    Panel sunucusu tam o bayrakla kosuyor: canlilik denetimi uretimde HER ISI OKSUZ
    gosterirdi. Test dogrudan kosunca geciyordu, kosucu altinda kaliyordu - fark bayrakti.

    Bu yuzden test denetimi ALT SURECTE, O BAYRAKLA kosar. Ayni surecte kosturmak
    hicbir sey olcmez."""
    kod = (
        "import os, subprocess, sys, time\n"
        "sys.path.insert(0, r'%s')\n" % ROOT +
        "from core.inceleme import _surec_canli\n"
        "kurban = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],\n"
        "                          creationflags=0x08000000)\n"
        "time.sleep(0.8)\n"
        "sonuc = {'kendi': _surec_canli(os.getpid()), 'kurban': _surec_canli(kurban.pid)}\n"
        "kurban.kill(); kurban.wait(); time.sleep(0.5)\n"
        "sonuc['oldurulen'] = _surec_canli(kurban.pid)\n"
        "sonuc['olmayan'] = _surec_canli(999999)\n"
        "sonuc['bozuk'] = _surec_canli('abc')\n"
        "sonuc['sifir'] = _surec_canli(0)\n"
        "try:\n"
        "    os.kill(os.getpid(), 0); sonuc['os_kill'] = 'ok'\n"
        "except Exception as e: sonuc['os_kill'] = type(e).__name__\n"
        "import json; open(r'%s', 'w').write(json.dumps(sonuc))\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cikti = f.name
    try:
        r = subprocess.run([sys.executable, "-c", kod % cikti], cwd=ROOT, timeout=90,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        with open(cikti, encoding="utf-8") as f:
            s = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise AssertionError("alt surec kosmadi: %s / %s" % (e, (r.stderr or b"")[:200])) from None
    finally:
        try:
            os.unlink(cikti)
        except OSError:
            pass

    assert s["kendi"] is True, "kendi sureci OLU sayildi: %s" % s
    assert s["kurban"] is True, "yasayan surec olu sayildi: %s" % s
    assert s["oldurulen"] is False, "oldurulmus surec CANLI sayildi: %s" % s
    assert s["olmayan"] is False, "olmayan pid canli sayildi: %s" % s
    # bozuk girdi: "bilinmiyor" denir, "olu" DENMEZ
    assert s["bozuk"] is None and s["sifir"] is None, "gecersiz pid icin hukum verildi: %s" % s
    print("surec canliligi: ok (CREATE_NO_WINDOW altinda dogru; os.kill orada %s veriyor)"
          % s["os_kill"])
    return True


def kabul_denetimi() -> bool:
    """Kabul kriterleri DENETLENDI mi, TUTTU mu? Ucu de ayri sey.

    YASANDI (gece kusatmasi): `kabul_kriterleri` yalnizca TASINIYORDU - iseme giriyor, is
    kaydina yaziliyor, hicbir yerde denetlenmiyordu. Derleme/ruff gecince sozlesme "gecti"
    diyordu. `dama` gorevi kriteri iki turda da tutturamadi (11/12), telemetri "ilk tur
    basari %100, hic hata yok" dedi: BASARISIZ ise BASARILI deniyordu.

    Kural: denetlenmemis kriter "gecti" SAYILMAZ; "yok" denir ve sebebi yazilir."""
    d = tempfile.mkdtemp()

    def kur(jid, kriterler, ok=True):
        jd = os.path.join(d, jid)
        os.makedirs(jd, exist_ok=True)
        with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
            json.dump({"id": jid, "durum": "bitti", "kabul_kriterleri": kriterler}, f,
                      ensure_ascii=False)
        with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "result", "ok": ok, "errors": [], "rounds": 0}) + "\n")

    def satir(jid):
        s = [x for x in inceleme(d, jid)["dogrulama"] if x["ad"] == "kabul kriterleri"]
        return s[0] if s else None

    # 1) KRITER VAR, DENETLENMEDI -> "gecti" DENMEZ
    kur("denetsiz", ["bos listede cokmesin", "harf notu dondursun"])
    s1 = satir("denetsiz")
    assert s1 and s1["durum"] == "yok", s1
    assert "DOGRULANMADI" in s1["kanit"] and "2 kriter" in s1["kanit"], s1

    # 2) DENETLENDI ve TUTMADI -> kaldi, kac kontrolun dustugu KANITTA
    kur("tutmadi", ["a", "b"])
    kabul_yaz(d, "tutmadi", 11, 12, ["coklu atlama zorunlu degil"], "kampanya")
    s2 = satir("tutmadi")
    assert s2["durum"] == "kaldi" and "11/12" in s2["kanit"], s2
    assert "coklu atlama" in s2["kanit"], "dusen kontrolun adi kanitta yok: %s" % s2

    # 3) DENETLENDI ve TUTTU
    kabul_yaz(d, "tutmadi", 12, 12, [], "kampanya")
    assert satir("tutmadi")["durum"] == "gecti", satir("tutmadi")

    # 4) KRITER YOK -> satir HIC eklenmez (denetlenecek sey yok)
    kur("kritersiz", [])
    assert satir("kritersiz") is None, "kritersiz iste kabul satiri uretildi"

    # 5) GECERSIZ sayim reddedilir, mevcut kayit BOZULMAZ
    for kotu in ((13, 12), (-1, 5), ("a", "b")):
        assert kabul_yaz(d, "tutmadi", kotu[0], kotu[1]).get("hata"), kotu
    assert satir("tutmadi")["durum"] == "gecti", "gecersiz sayim mevcut denetimi bozdu"
    assert kabul_yaz(d, "olmayan_is", 1, 1).get("hata")

    # 6) KABUL kaydi OLAY GUNLUGUNE yazilmaz (tek yazar kurali)
    with open(os.path.join(d, "tutmadi", "events.jsonl"), encoding="utf-8") as f:
        assert "kabul" not in f.read(), "kabul denetimi events.jsonl'e yazilmis"
    assert os.path.exists(os.path.join(d, "tutmadi", "kabul.json"))

    # 7) TELEMETRI dogrulayici basarisini kabul basarisiyla KARISTIRMAZ
    o = toplu(d, 50)
    assert o["kabul_gecti"] == 1 and o["kabul_denetlenmedi"] == 1, o
    assert o["kritersiz_is"] == 1, o
    assert "kabul_uyarisi" in o, "denetlenmemis kriter varken uyari yok"
    assert "yalniz DOGRULAYICIYI" in o["kabul_uyarisi"], o["kabul_uyarisi"]
    print("kabul denetimi: ok (denetlenmemis kriter 'gecti' sayilmiyor, telemetri ayiriyor)")
    return True


def zaman_cizgisi() -> bool:
    """SURE NEREYE GITTI (yol haritasi 11): olaylardan zaman dilimleri.

    Cakilan sozlesme:
      1. Uc tur dilim ayrilir: model uretimi / arac kosumu / dogrulama.
      2. Dilimler TOPLAMI isin suresini asmaz - cakisan dilim uretmeyiz.
      3. ESKI KAYITTA ZAMAN YOKSA UYDURULMAZ: var=False doner, panel bolumu cizmez.
         Eksik olcumu tahminle doldurmak, olcumun kendisini bozar."""
    d = tempfile.mkdtemp()
    jd = os.path.join(d, "is1"); os.makedirs(jd)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "is1", "ortam": "code", "calisma_dizini": d}, f)
    T = 1000.0
    olaylar = [{"type": "system", "t": T},
               {"type": "tool", "name": "read_file", "t": T + 12},
               {"type": "tool_result", "name": "read_file", "t": T + 12.4},
               {"type": "tool", "name": "write_file", "t": T + 40},
               {"type": "tool_result", "name": "write_file", "t": T + 40.6},
               {"type": "write", "path": "a.py", "before": "", "after": "x=1", "t": T + 40.6},
               # `assistant` = modelin NIHAI cevabi bitti. Dogrulamanin BASLANGIC SINIRI
               # budur; olmadan "son aractan sonrasi dogrulama" varsayimi modelin cevap
               # uretme suresini de dogrulama sayardi (denetim bulgusu 9).
               {"type": "assistant", "text": "bitti", "t": T + 40.6},
               {"type": "result", "ok": True, "errors": [], "wall": 55, "t": T + 55}]

    def yaz(ol):
        with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
            for e in ol:
                f.write(json.dumps(e) + "\n")

    yaz(olaylar)
    z = inceleme(d, "is1")["zaman_cizgisi"]
    assert z["var"] and z["toplam"] == 55.0, z
    oz = z["ozet"]
    assert oz["uretim"] == 39.6 and oz["dogrulama"] == 14.4, oz
    assert abs(oz["arac"] - 1.0) < 0.01, oz
    # dilimler cakismamali: toplamlari isin suresini ASMAZ
    assert sum(x["sure"] for x in z["dilimler"]) <= z["toplam"] + 0.01, z["dilimler"]
    tipler = [x["tip"] for x in z["dilimler"]]
    assert tipler == ["uretim", "arac", "uretim", "arac", "dogrulama"], tipler
    assert abs(z["uretim_orani"] - 0.72) < 0.01, z["uretim_orani"]

    # YARIM KALAN ARAC (cokme/zaman asimi): kayip zaman yutulmaz, isaretlenir
    yaz(olaylar[:4] + [{"type": "exit", "code": 1, "t": T + 60}])
    z2 = inceleme(d, "is1")["zaman_cizgisi"]
    assert any("yarim" in x["ad"] for x in z2["dilimler"]), z2["dilimler"]

    # ARACSIZ IS: surenin TAMAMI uretimdir - yapay dogrulama suresi URETILMEZ.
    # (Olculdu: eski surum 60 sn uretimi 60 sn "dogrulama" gosteriyordu.)
    yaz([{"type": "system", "t": T},
         {"type": "assistant", "text": "uzun cevap", "t": T + 60},
         {"type": "result", "ok": True, "errors": [], "t": T + 60}])
    za = inceleme(d, "is1")["zaman_cizgisi"]
    assert za["ozet"]["dogrulama"] == 0.0, "aracsiz iste yapay dogrulama suresi: %s" % za["ozet"]
    assert za["ozet"]["uretim"] == 60.0, za["ozet"]

    # ASSISTANT YOKSA sinir BILINMEZ: "dogrulama" diye etiketlemek yerine acikca bilinmiyor
    yaz([{"type": "system", "t": T},
         {"type": "tool", "name": "w", "t": T + 5},
         {"type": "tool_result", "name": "w", "t": T + 6},
         {"type": "result", "ok": True, "errors": [], "t": T + 30}])
    zb = inceleme(d, "is1")["zaman_cizgisi"]
    assert zb["ozet"]["dogrulama"] == 0.0, zb["ozet"]
    assert zb["ozet"]["bilinmiyor"] == 24.0, "siniflandirilamayan sure gizlendi: %s" % zb["ozet"]
    assert any(x["tip"] == "bilinmiyor" for x in zb["dilimler"]), zb["dilimler"]

    # GOSTERIM SINIRI acikca bildirilmeli (ekrandaki dilimleri toplamak toplami vermez)
    cok = [{"type": "system", "t": T}]
    for i in range(60):
        cok.append({"type": "tool", "name": "a%d" % i, "t": T + i * 2 + 1})
        cok.append({"type": "tool_result", "name": "a%d" % i, "t": T + i * 2 + 1.9})
    cok.append({"type": "assistant", "text": "x", "t": T + 130})
    cok.append({"type": "result", "ok": True, "errors": [], "t": T + 140})
    yaz(cok)
    zc = inceleme(d, "is1")["zaman_cizgisi"]
    assert zc["kirpildi"] is True and zc["dilim_sayisi"] > len(zc["dilimler"]), zc["dilim_sayisi"]
    assert sum(x["sure"] for x in zc["dilimler"]) < sum(zc["ozet"].values()) + 0.01,         "kirpma bildirilmis ama ozet dilimlerle ayni - kirpma anlamsiz"

    # ESKI KAYIT: zaman damgasi yok -> UYDURMA YOK
    yaz([{k: v for k, v in e.items() if k != "t"} for e in olaylar])
    z3 = inceleme(d, "is1")["zaman_cizgisi"]
    assert z3["var"] is False and "zaman damgasi yok" in z3["sebep"], z3
    assert "dilimler" not in z3 or not z3.get("dilimler"), z3
    print("zaman cizgisi: ok (uc tur dilim, cakisma yok, eski kayitta uydurma yok)")
    return True


def main() -> int:
    ok = (net_fark() and geri_alma_ispati() and devir_kanitla() and kapsam_ve_dogrulama()
          and beyan_kanittan_ayri() and uc_baglandi() and karar_kaydi() and surec_canliligi() and kabul_denetimi() and zaman_cizgisi())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

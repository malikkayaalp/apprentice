"""GERI ALMA testi (core/geri_al.py).

Asil soru: `run_shell` boslugu gercekten kapaniyor mu? `write` olaylari before/after tasir
ama run_shell calisma alanini olay gunlugune HIC girmeden degistirebilir. Git ise
degisikligi KIMIN yaptigina bakmaz - bu yuzden birincil yontem git, gunluk yedektir.

Testler dort guvenlik kuralini cakar:
  1. Kullanicinin KENDI degisikligine dokunulmaz (is baslarken zaten kirli olan dosya).
  2. Is bittikten SONRA degismis dosyaya dokunulmaz (baskasi duzenlemis olabilir).
  3. Calisma alani disina cikan yol islenmez.
  4. Once PLAN, sonra uygulama: plan() hicbir seyi degistirmez.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.geri_al import anlik, plan, uygula, zemin  # noqa: E402
from core.geri_al import _kirli as _kirli_disaridan  # noqa: E402

PZ = 0x08000000 if os.name == "nt" else 0


def _git(d, *a):
    return subprocess.run(["git", "-C", d] + list(a), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=PZ)


def _is(ev: str, workdir: str, olaylar: list, ag: dict) -> str:
    jd = os.path.join(ev, "is1")
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "is1", "calisma_dizini": workdir, "anlik": ag}, f)
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in olaylar:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return ev


def _yaz(kok, ad, ic):
    with open(os.path.join(kok, ad), "w", encoding="utf-8") as f:
        f.write(ic)


def _oku(kok, ad):
    with open(os.path.join(kok, ad), encoding="utf-8") as f:
        return f.read()


def git_yolu() -> bool:
    """GIT: run_shell'in urettigi, GUNLUKTE HIC GORUNMEYEN dosya da geri alinmali.
    Kullanicinin is baslamadan once yaptigi degisiklige DOKUNULMAMALI."""
    if not shutil.which("git"):
        print("geri alma (git): git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "a.py", "eski a\n")
    _yaz(wd, "kullanici.py", "v1\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    _yaz(wd, "kullanici.py", "KULLANICI DEGISIKLIGI\n")     # is BASLAMADAN once: bizim degil

    ag = anlik(wd)
    assert ag["yontem"] == "git" and ag["kirli"] == ["kullanici.py"], ag

    _yaz(wd, "a.py", "yeni a\n")                    # cirak yazdi (gunlukte var)
    _yaz(wd, "kabuk_urunu.py", "kabuk yazdi\n")     # run_shell yazdi (GUNLUKTE YOK)
    # SIRA URETIMDEKI GIBI: dosyalar once yazilir, olay gunlugu EN SON kapanir. Bitis ani
    # events.jsonl mtime'indan okunuyor; fikstur ters sirayla kurulursa dosyalar "is
    # bittikten sonra degismis" gorunur.
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "eski a\n", "after": "yeni a\n"},
        {"type": "tool", "name": "run_shell", "detail": "python uret.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], ag)

    p = plan(ev, "is1")
    assert p["yontem"] == "git" and p["mumkun"], p
    yollar = {e["yol"]: e["eylem"] for e in p["eylemler"]}
    assert yollar.get("a.py") == "geri_yaz", p
    assert yollar.get("kabuk_urunu.py") == "sil", "run_shell urunu plana girmedi - BOSLUK ACIK"
    assert "kullanici.py" not in yollar, "KULLANICININ DOSYASI plana girdi"
    assert any(a["yol"] == "kullanici.py" for a in p["atlanan"]), p["atlanan"]
    # KURAL 4: plan hicbir seyi degistirmemis olmali
    assert _oku(wd, "a.py") == "yeni a\n" and os.path.exists(os.path.join(wd, "kabuk_urunu.py"))

    r = uygula(ev, "is1", p)
    assert len(r["yapildi"]) == 2 and not r["basarisiz"], r
    assert _oku(wd, "a.py") == "eski a\n", "geri yazilmadi"
    assert not os.path.exists(os.path.join(wd, "kabuk_urunu.py")), "kabuk urunu silinmedi"
    assert "KULLANICI DEGISIKLIGI" in _oku(wd, "kullanici.py"), "KULLANICININ EMEGI SILINDI"
    print("geri alma (git): ok (run_shell boslugu kapali, kullanicinin isi korundu)")
    return True


def kullanici_emegi_git() -> bool:
    """GIT yolunda da: is bittikten SONRA degisen dosyaya DOKUNULMAZ (denetim bulgusu #2).

    Git yolu "kim degistirdiginden bagimsiz" calisiyordu; bu, cirak bittikten SONRA
    kullanicinin yaptigi duzenlemeyi de kapsiyordu. Somut zarar:
      - cirak a.py yazar -> kullanici elle duzeltir -> GERI AL -> `git checkout` kullanicinin
        emegini SESSIZCE siler.
      - kullanici is bittikten sonra YENI dosya olusturur -> git'e '??' gorunur -> SILINIR.
    Gunluk yolunda bu kural bastan beri vardi, git yolunda YOKTU. Bu test farki kilitler."""
    if not shutil.which("git"):
        print("kullanici emegi (git): git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "cirak.py", "eski\n"); _yaz(wd, "ikinci.py", "eski2\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)

    _yaz(wd, "cirak.py", "def f():\n    return 1\n")     # cirak iki dosyayi da yazdi
    _yaz(wd, "ikinci.py", "x = 1\n")
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "cirak.py", "before": "eski\n", "after": "def f():\n    return 1\n"},
        {"type": "write", "path": "ikinci.py", "before": "eski2\n", "after": "x = 1\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], ag)

    # --- IS BITTI. Simdi KULLANICI devrede ---
    time.sleep(2.5)                       # mtime bitisten SONRA olsun (SLACK payi 2 sn)
    _yaz(wd, "cirak.py", "def f():\n    return 42   # kullanici duzeltti\n")
    _yaz(wd, "ELDE_YAZILAN.py", "# kullanicinin kendi yeni dosyasi\n")

    p = plan(ev, "is1")
    yollar = {e["yol"] for e in p["eylemler"]}
    atl = {a["yol"]: a["sebep"] for a in p["atlanan"]}
    assert p["yontem"] == "git", p
    assert "cirak.py" not in yollar, "kullanicinin duzenledigi dosya geri alma planinda!"
    assert "ELDE_YAZILAN.py" not in yollar, "kullanicinin YENI dosyasi SILINECEKTI!"
    assert "cirak.py" in atl and "sonra" in atl["cirak.py"], atl
    assert "ELDE_YAZILAN.py" in atl, atl
    # dokunulmamis dosya HALA geri alinabilmeli - koruma isi tumden durdurmamali
    assert "ikinci.py" in yollar, "dokunulmamis dosya da geri alinamadi: %s" % p

    r = uygula(ev, "is1", p)
    assert _oku(wd, "cirak.py") == "def f():\n    return 42   # kullanici duzeltti\n", \
        "KULLANICININ EMEGI SILINDI"
    assert os.path.exists(os.path.join(wd, "ELDE_YAZILAN.py")), "kullanicinin YENI dosyasi SILINDI"
    assert _oku(wd, "ikinci.py") == "eski2\n", r     # dokunulmayan dosya gercekten geri alindi
    print("kullanici emegi (git): ok (duzenlenen + yeni dosya atlandi, digeri geri alindi)")
    return True


def bayat_plan() -> bool:
    """Plan gosterildikten SONRA dosya degisirse UYGULA yine de dokunmaz (yaris korumasi).

    Panel plani gosterir, kullanici onay ekranindayken dosyayi duzenler, sonra GERI AL'a
    basar. Yikici adimin hemen oncesinde yeniden bakilmazsa emek gider."""
    if not shutil.which("git"):
        print("bayat plan: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "yaris.py", "eski\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)
    _yaz(wd, "yaris.py", "yeni = 1\n")
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "yaris.py", "before": "eski\n", "after": "yeni = 1\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], ag)
    p = plan(ev, "is1")
    assert {e["yol"] for e in p["eylemler"]} == {"yaris.py"}, p     # plan cikarken temizdi

    time.sleep(2.5)      # kullanici onay ekranindayken dosyayi duzenledi
    _yaz(wd, "yaris.py", "yeni = 1\nkullanici = 'buraya dokunma'\n")

    r = uygula(ev, "is1", p)      # BAYAT plan uygulaniyor
    assert not r.get("yapildi"), "bayat plan korumasiz uygulandi -> %s" % r
    assert any(a["yol"] == "yaris.py" for a in r.get("atlanan") or []), r
    assert _oku(wd, "yaris.py") == "yeni = 1\nkullanici = 'buraya dokunma'\n", \
        "plan-sonrasi duzenleme SILINDI"
    print("bayat plan: ok (plan gosterildikten sonraki duzenleme korundu)")
    return True


def gunluk_yolu() -> bool:
    """GIT YOK: kabuk kosmadiysa olay gunlugu yeter; kostuysa REDDEDILIR."""
    wd = tempfile.mkdtemp()
    _yaz(wd, "a.py", "yeni\n"); _yaz(wd, "b.py", "sifirdan\n")
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "eski\n", "after": "yeni\n"},
        {"type": "write", "path": "b.py", "before": "", "after": "sifirdan\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"yontem": "yok"})
    p = plan(ev, "is1")
    assert p["yontem"] == "gunluk" and p["mumkun"], p
    uygula(ev, "is1", p)
    assert _oku(wd, "a.py") == "eski\n", "eski icerik geri yazilmadi"
    assert not os.path.exists(os.path.join(wd, "b.py")), "isin yarattigi dosya silinmedi"

    # kabuk kostu + git yok -> RED, ve dosyaya DOKUNULMAZ
    wd2 = tempfile.mkdtemp(); _yaz(wd2, "a.py", "yeni\n")
    ev2 = _is(tempfile.mkdtemp(), wd2, [
        {"type": "write", "path": "a.py", "before": "eski\n", "after": "yeni\n"},
        {"type": "tool", "name": "run_shell", "detail": "python x.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"yontem": "yok"})
    p2 = plan(ev2, "is1")
    assert p2["mumkun"] is False and "run_shell" in p2["sebep"], p2
    r2 = uygula(ev2, "is1", p2)
    assert r2.get("hata") and _oku(wd2, "a.py") == "yeni\n", "reddedildigi halde dokundu"
    print("geri alma (gunluk): ok (kabuk yoksa izin, varsa red ve dokunmuyor)")
    return True


def guvenlik() -> bool:
    """Sonradan degisen dosya ATLANIR; calisma alani disi ISLENMEZ."""
    wd = tempfile.mkdtemp()
    _yaz(wd, "a.py", "BASKASI ELLE DEGISTIRDI\n")
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "eski\n", "after": "yeni\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], {"yontem": "yok"})
    p = plan(ev, "is1")
    assert p["mumkun"] is False and p["atlanan"], p
    assert "sonra" in p["atlanan"][0]["sebep"], p["atlanan"]
    assert _oku(wd, "a.py") == "BASKASI ELLE DEGISTIRDI\n"

    wd2 = tempfile.mkdtemp()
    for kotu in ("../disari.py", "/mutlak.py", "C:/Windows/x.py"):
        ev2 = _is(tempfile.mkdtemp(), wd2, [
            {"type": "write", "path": kotu, "before": "", "after": "x\n"},
            {"type": "result", "ok": True, "errors": [], "rounds": 0},
        ], {"yontem": "yok"})
        p2 = plan(ev2, "is1")
        assert not p2["eylemler"], "%r plana girdi" % kotu
        assert p2["atlanan"] and p2["atlanan"][0]["sebep"] == "calisma alani disinda", p2

    # anlik goruntu: git olmayan klasorde "yok" der, patlamaz
    assert anlik(tempfile.mkdtemp())["yontem"] == "yok"
    assert anlik(os.path.join(wd2, "olmayan"))["yontem"] == "yok"
    print("guvenlik: ok (sonradan degisen atlandi, kacis yollari islenmedi)")
    return True


def zemin_bilgisi() -> bool:
    """Cirak HANGI ZEMINE yazacak: dal + worktree temiz mi. Git deposu degilse
    {"git": False} doner - bos/uydurma bilgi gosterilmez."""
    if not shutil.which("git"):
        print("zemin: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    assert zemin(wd) == {"git": False}, "git olmayan klasore dal uyduruldu"
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t")
    _git(wd, "config", "user.name", "t"); _git(wd, "checkout", "-q", "-b", "ozellik/giris")
    _yaz(wd, "a.py", "x\n"); _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    z = zemin(wd)
    assert z["git"] is True and z["dal"] == "ozellik/giris", z
    assert z["temiz"] is True and z["kirli_sayisi"] == 0, z
    _yaz(wd, "a.py", "degisti\n")
    z2 = zemin(wd)
    assert z2["temiz"] is False and z2["kirli_sayisi"] == 1, z2
    # anlik goruntu de dali kaydeder (is HANGI zemine yazildi)
    assert anlik(wd)["dal"] == "ozellik/giris"
    assert zemin(os.path.join(wd, "olmayan")) == {"git": False}
    print("zemin bilgisi: ok (dal + worktree durumu, git yoksa uydurmuyor)")
    return True


def zemin_degisirse_durur() -> bool:
    """IS SIRASINDA commit/checkout olduysa geri alma DURUR (denetim bulgusu 2).

    Kayitli baslangic HEAD'i bugune kadar HIC OKUNMUYORDU: anlik() kaydediyor, uygula() ise
    duz `git checkout -- <yol>` cagiriyordu - yani INDEKSTEN/GUNCEL HEAD'den geri yaziyordu.
    Is sirasinda commit olduysa YANLIS icerik yaziliyordu."""
    if not shutil.which("git"):
        print("zemin degisirse durur: git yok, atlandi")
        return True

    # --- HEAD degisirse ---
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "a.py", "v1\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)
    _yaz(wd, "a.py", "cirak yazdi\n")
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "v1\n", "after": "cirak yazdi\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "t": time.time()}], ag)
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "kullanici commit")   # HEAD ILERLEDI

    p = plan(ev, "is1")
    assert not p["mumkun"], "HEAD degismisken geri alma mumkun gorundu"
    assert "HEAD" in p["sebep"] and "DURDURULDU" in p["sebep"], p["sebep"]
    # BAYAT plan da uygulanmamali - uygula() zemini yeniden denetler
    r = uygula(ev, "is1", {"mumkun": True, "eylemler": [
        {"yol": "a.py", "eylem": "geri_yaz", "kaynak": "git"}]})
    assert r.get("hata"), "HEAD degismisken bayat plan uygulandi: %s" % r
    assert _oku(wd, "a.py") == "cirak yazdi\n", "HEAD degismisken dosyaya DOKUNULDU"

    # --- DAL degisirse ---
    wd2 = tempfile.mkdtemp()
    _git(wd2, "init", "-q"); _git(wd2, "config", "user.email", "t@t"); _git(wd2, "config", "user.name", "t")
    _yaz(wd2, "b.py", "v1\n")
    _git(wd2, "add", "-A"); _git(wd2, "commit", "-qm", "ilk")
    ag2 = anlik(wd2)
    _yaz(wd2, "b.py", "cirak\n")
    ev2 = _is(tempfile.mkdtemp(), wd2, [
        {"type": "write", "path": "b.py", "before": "v1\n", "after": "cirak\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "t": time.time()}], ag2)
    _git(wd2, "checkout", "-q", "-b", "baska-dal")
    p2 = plan(ev2, "is1")
    assert not p2["mumkun"] and "dal" in p2["sebep"], p2["sebep"]
    print("zemin degisirse durur: ok (HEAD ve dal degisimi ayri ayri durdurdu)")
    return True


def baslangic_icerigi_geri_yazilir() -> bool:
    """Geri yazma IS BASLANGICINDAKI icerigi kullanir - indeksi ya da guncel HEAD'i DEGIL.

    `git checkout -- <yol>` once INDEKSE bakar: is sirasinda bir sey sahnelendiyse (cirak
    ya da kabuk `git add` calistirdiysa) geri alma o BOZUK kaynagi yaziyordu. Ustelik
    dosyayi ayrica sahneliyordu - kullanicinin stage durumunu degistirmek geri almanin
    isi degil. `git show <baslangic_head>:<yol>` ikisini de cozer."""
    if not shutil.which("git"):
        print("baslangic icerigi: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "a.py", "BASLANGIC\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)

    _yaz(wd, "a.py", "cirak yazdi\n")
    _git(wd, "add", "a.py")            # INDEKS artik cirak'in icerigini tutuyor
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "BASLANGIC\n", "after": "cirak yazdi\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "t": time.time()}], ag)
    p = plan(ev, "is1")
    assert p["mumkun"], p
    r = uygula(ev, "is1", p)
    assert not r["basarisiz"], r
    assert _oku(wd, "a.py") == "BASLANGIC\n", \
        "baslangic icerigi degil indeks/HEAD yazildi: %r" % _oku(wd, "a.py")
    print("baslangic icerigi geri yazilir: ok (indeks kaynak DEGIL)")
    return True


def kullanici_is_sirasinda_duzenlerse() -> bool:
    """IS SURERKEN kullanicinin degistirdigi/olusturdugu dosya KORUNUR.

    Kabuk KOSMADIYSA cirak dosyayi ancak write_file ile degistirebilir - izi gunlukte olur.
    Iz yoksa o degisiklik KULLANICININDIR. Kabuk KOSTUYSA ayirt edilemez; o zaman plana
    girer ama BELIRSIZ isaretiyle - kullanici onaylamadan once gorsun."""
    if not shutil.which("git"):
        print("kullanici is sirasinda: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "cirak.py", "v1\n"); _yaz(wd, "benim.py", "benim v1\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")
    ag = anlik(wd)

    _yaz(wd, "cirak.py", "cirak yazdi\n")                   # gunlukte VAR
    _yaz(wd, "benim.py", "IS SURERKEN BEN DUZENLEDIM\n")    # gunlukte YOK -> kullanici
    _yaz(wd, "YENI_NOTUM.md", "is surerken actim\n")        # gunlukte YOK -> kullanici
    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "cirak.py", "before": "v1\n", "after": "cirak yazdi\n"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "t": time.time()}], ag)

    p = plan(ev, "is1")
    yollar = {e["yol"] for e in p["eylemler"]}
    atl = {a["yol"]: a["sebep"] for a in p["atlanan"]}
    assert "cirak.py" in yollar, "cirak'in yazdigi dosya geri alinmiyor: %s" % p
    assert "benim.py" not in yollar, "KULLANICININ is sirasindaki duzenlemesi geri alinacakti"
    assert "YENI_NOTUM.md" not in yollar, "KULLANICININ yeni dosyasi silinecekti"
    assert "kabuk" in atl.get("benim.py", ""), atl      # sebep: cirak yazmamis, kabuk kosmamis
    uygula(ev, "is1", p)
    assert "BEN DUZENLEDIM" in _oku(wd, "benim.py"), "kullanicinin emegi silindi"
    assert os.path.exists(os.path.join(wd, "YENI_NOTUM.md")), "kullanicinin yeni dosyasi silindi"
    assert _oku(wd, "cirak.py") == "v1\n", "cirak'in dosyasi geri alinmadi"

    # KABUK KOSTUYSA: plana girer ama BELIRSIZ isaretiyle (run_shell boslugu kapali kalsin)
    wd2 = tempfile.mkdtemp()
    _git(wd2, "init", "-q"); _git(wd2, "config", "user.email", "t@t"); _git(wd2, "config", "user.name", "t")
    _yaz(wd2, "x.py", "v1\n"); _git(wd2, "add", "-A"); _git(wd2, "commit", "-qm", "ilk")
    ag2 = anlik(wd2)
    _yaz(wd2, "kabuk_urunu.txt", "kabuk yazdi\n")
    ev2 = _is(tempfile.mkdtemp(), wd2, [
        {"type": "tool", "name": "run_shell", "detail": "python uret.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0, "t": time.time()}], ag2)
    p2 = plan(ev2, "is1")
    e2 = [e for e in p2["eylemler"] if e["yol"] == "kabuk_urunu.txt"]
    assert e2, "kabuk urunu plana girmedi - run_shell boslugu geri acildi"
    assert e2[0].get("belirsiz"), "kabuk kosarken belirsizlik isaretlenmemis: %s" % e2[0]
    print("kullanici is sirasinda duzenlerse: ok (korundu; kabuk varsa belirsiz isaretli)")
    return True


def zor_yollar() -> bool:
    """Bosluk, Unicode ve yeniden adlandirma iceren yollar DOGRU ayristirilir.

    Eski ayristirma satir[3:].strip().strip(chr(34)) idi. git ozel karakterli yolu TIRNAKLAR
    ve C-kacisi uygular; yeniden adlandirmayi 'eski -> yeni' bicimde yazar. Sonuc, bas
    tirnakli bozuk bir yoldu ve hicbir dosyayla eslesmedigi icin geri alma SESSIZCE
    iskaliyordu. Artik `--porcelain -z` (NUL ayracli, kacissiz) kullaniliyor."""
    if not shutil.which("git"):
        print("zor yollar: git yok, atlandi")
        return True
    wd = tempfile.mkdtemp()
    _git(wd, "init", "-q"); _git(wd, "config", "user.email", "t@t"); _git(wd, "config", "user.name", "t")
    _yaz(wd, "eski_ad.py", "tasinacak\n")
    _git(wd, "add", "-A"); _git(wd, "commit", "-qm", "ilk")

    bosluklu = "benim dosyam.py"
    unicodelu = "ozel_ismi_s_g_u_ışğü.py"
    _yaz(wd, bosluklu, "bosluk\n")
    _yaz(wd, unicodelu, "unicode\n")
    _git(wd, "mv", "eski_ad.py", "yeni_ad.py")

    kirli = _kirli_disaridan(wd)
    assert bosluklu in kirli, "bosluklu yol okunamadi: %s" % sorted(kirli)
    assert unicodelu in kirli, "unicode yol okunamadi: %s" % sorted(kirli)
    assert "yeni_ad.py" in kirli, "yeniden adlandirmanin HEDEFI okunamadi: %s" % sorted(kirli)
    for y in kirli:
        assert not y.startswith(chr(34)), "bozuk yol (bas tirnak): %r" % y
        assert " -> " not in y, "yeniden adlandirma ayristirilmamis: %r" % y
    print("zor yollar: ok (bosluk, unicode, yeniden adlandirma)")
    return True


def main() -> int:
    ok = (git_yolu() and kullanici_emegi_git() and bayat_plan() and gunluk_yolu()
          and guvenlik() and zemin_bilgisi() and zemin_degisirse_durur()
          and baslangic_icerigi_geri_yazilir() and kullanici_is_sirasinda_duzenlerse()
          and zor_yollar())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

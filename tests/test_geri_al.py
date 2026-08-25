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
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.geri_al import anlik, plan, uygula  # noqa: E402

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

    ev = _is(tempfile.mkdtemp(), wd, [
        {"type": "write", "path": "a.py", "before": "eski a\n", "after": "yeni a\n"},
        {"type": "tool", "name": "run_shell", "detail": "python uret.py"},
        {"type": "result", "ok": True, "errors": [], "rounds": 0},
    ], ag)
    _yaz(wd, "a.py", "yeni a\n")                    # cirak yazdi (gunlukte var)
    _yaz(wd, "kabuk_urunu.py", "kabuk yazdi\n")     # run_shell yazdi (GUNLUKTE YOK)

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


def main() -> int:
    ok = git_yolu() and gunluk_yolu() and guvenlik()
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

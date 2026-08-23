"""Apprentice kurulum: tek betik, adim adim, bagimliliksiz.

    python kur.py                 # kontrol et, eksikleri tamamla (model indirme dahil), IDE'leri ayarla
    python kur.py --kontrol       # yalnizca durumu goster, hicbir sey degistirme
    python kur.py --ide cursor,vscode   # yalnizca bu IDE'leri ayarla (cursor, vscode, windsurf, claude-desktop)
    python kur.py --olc           # + ilk calistirma num_batch olcumu (2-3 dk, GPU'ya ozel)
    python kur.py --kural <proje_klasoru>   # denetci kural dosyasini o projeye yaz (Cursor .mdc + genel .md)

Windows'ta ayni betik Apprentice-Setup.exe olarak paketlenir (PyInstaller); Python yoksa resmi
gomulu Python'u (embeddable, ~11 MB) depoya indirir ve sunucu onunla calisir.

Adimlar:
  1  Python 3.10+ (yoksa gomulu Python indirilir - yalniz Windows)
  2  Ollama kurulu mu, calisiyor mu (degilse baslatmayi dener)
  3  Model var mi, yoksa indir (ilerleme yuzdesiyle)
  4  IDE'ler: kurulu olan her IDE'nin MCP ayarina "apprentice" girdisi (diger girdilere dokunmaz)
     Claude Code: depodaki .mcp.json zaten yeterli
  5  Oz-test: sunucuyla el sikisma + fake ortamda bir tur (model gerekmez)
  6  (istege bagli) num_batch olcumu -> apprentice.config.json
"""
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys, time, urllib.request, urllib.error

# exe (PyInstaller --onefile) icinden: __file__ gecici klasoru gosterir; depo = exe'nin yanindaki klasor.
ROOT = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
sys.path.insert(0, ROOT)
if not os.path.isdir(os.path.join(ROOT, "server")):
    print("Bu dosya Apprentice deposunun KOKUNDE calistirilmali (server/ klasorunun yaninda). Su an: %s" % ROOT)
    sys.exit(1)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from core import config  # noqa: E402

OK, HATA, UYARI, BILGI = "[ok]  ", "[X]   ", "[!]   ", "      "
DEGISTIR = True


def adim(n, baslik):
    print("\n%d) %s" % (n, baslik))


def ollama_url() -> str:
    return (config.get("ollama.url") or "http://localhost:11434").rstrip("/")


def ollama_tags():
    with urllib.request.urlopen(ollama_url() + "/api/tags", timeout=3) as r:
        return [m.get("name") for m in json.load(r).get("models", [])]


# ------------------------------------------------------------------ 1 python
DONMUS = getattr(sys, "frozen", False)          # PyInstaller exe icinden mi calisiyoruz
GOMULU_SURUM = "3.12.8"
GOMULU_DIR = os.path.join(ROOT, "runtime", "python")


def sistem_python() -> str:
    """Sunucuyu calistiracak Python: gomulu varsa o, yoksa PATH'teki 3.10+."""
    g = os.path.join(GOMULU_DIR, "python.exe")
    if os.path.isfile(g):
        return g
    if not DONMUS and sys.version_info >= (3, 10):
        return sys.executable
    for ad in ("python3", "python", "py"):
        exe = shutil.which(ad)
        if not exe:
            continue
        try:
            out = subprocess.run([exe, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if tuple(int(x) for x in out.split(".")) >= (3, 10):
                return exe
        except Exception:
            continue
    return ""


def gomulu_python_indir() -> bool:
    """Resmi Windows embeddable Python'u runtime/python altina acar. pip yok, gerekmiyor (stdlib)."""
    if os.name != "nt":
        return False
    import zipfile, io
    url = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (GOMULU_SURUM, GOMULU_SURUM)
    print(BILGI + "Gomulu Python indiriliyor: %s" % url)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            veri = r.read()
        os.makedirs(GOMULU_DIR, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(veri)).extractall(GOMULU_DIR)
        # ._pth dosyasi: depo kokunu de yola ekle ki 'core', 'mcpbridge' bulunsun
        for ad in os.listdir(GOMULU_DIR):
            if ad.endswith("._pth"):
                with open(os.path.join(GOMULU_DIR, ad), "a", encoding="utf-8") as f:
                    f.write("\n..\\..\n")
        ok = subprocess.run([os.path.join(GOMULU_DIR, "python.exe"), "-c", "import json, urllib.request; print('ok')"],
                            capture_output=True, text=True, timeout=30).stdout.strip() == "ok"
        print((OK if ok else HATA) + "Gomulu Python %s: %s" % (GOMULU_SURUM, GOMULU_DIR))
        return ok
    except Exception as e:
        print(HATA + "gomulu Python indirilemedi: %s" % str(e)[:200])
        return False


def kontrol_python() -> bool:
    exe = sistem_python()
    if exe:
        try:
            v = subprocess.run([exe, "-c", "import sys;print(sys.version.split()[0])"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            v = "?"
        print(OK + "Python %s  (%s)" % (v, exe))
        return True
    print(UYARI + "Python 3.10+ bulunamadi.")
    if not DEGISTIR:
        return False
    if gomulu_python_indir():
        return True
    print(HATA + "Python kur: https://www.python.org/downloads/  (kurunca tekrar calistir)")
    return False


# ------------------------------------------------------------------ 2 ollama
def kontrol_ollama() -> bool:
    exe = shutil.which("ollama")
    if not exe:
        print(HATA + "Ollama kurulu degil. Indir: https://ollama.com/download  (kurunca bu betigi tekrar calistir)")
        return False
    print(OK + "Ollama kurulu: %s" % exe)
    try:
        ollama_tags()
        print(OK + "Ollama calisiyor (%s)" % ollama_url())
        return True
    except Exception:
        pass
    if not DEGISTIR:
        print(HATA + "Ollama calismiyor (%s)." % ollama_url())
        return False
    print(BILGI + "Ollama calismiyor, baslatiliyor...")
    try:
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([exe, "serve"], **kw)
    except Exception as e:
        print(HATA + "baslatilamadi: %s" % e)
        return False
    for _ in range(20):
        time.sleep(1)
        try:
            ollama_tags()
            print(OK + "Ollama basladi")
            return True
        except Exception:
            continue
    print(HATA + "Ollama 20 sn icinde cevap vermedi. Elle baslat: ollama serve")
    return False


# ------------------------------------------------------------------ 3 model
def kontrol_model() -> bool:
    model = config.env_or(["APPRENTICE_MODEL", "UNITY_CODE_MODEL"], "ollama.model")
    try:
        adlar = ollama_tags()
    except Exception:
        print(HATA + "Ollama'ya ulasilamadi, model kontrol edilemedi")
        return False
    if model in adlar:
        print(OK + "Model yuklu: %s" % model)
        return True
    print(UYARI + "Model yok: %s" % model)
    if not DEGISTIR:
        return False
    print(BILGI + "Indiriliyor (~20 GB, baglantiya gore 10-60 dk)...")
    req = urllib.request.Request(ollama_url() + "/api/pull",
                                 json.dumps({"name": model, "stream": True}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            son = ""
            for line in r:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("error"):
                    print("\n" + HATA + d["error"])
                    return False
                durum = d.get("status", "")
                t, c = d.get("total"), d.get("completed")
                if t and c is not None:
                    birim, bol = ("GB", 1e9) if t >= 1e9 else ("MB", 1e6)
                    msg = "%s  %5.1f%%  (%.1f / %.1f %s)" % (durum, 100.0 * c / t, c / bol, t / bol, birim)
                else:
                    msg = durum
                if msg != son:
                    sys.stdout.write("\r" + BILGI + msg.ljust(70))
                    sys.stdout.flush()
                    son = msg
        print()
    except Exception as e:
        print("\n" + HATA + "indirme hatasi: %s" % str(e)[:200])
        return False
    try:
        if model in ollama_tags():
            print(OK + "Model indirildi: %s" % model)
            return True
    except Exception:
        pass
    print(HATA + "indirme bitti ama model listede yok; 'ollama pull %s' ile elle dene" % model)
    return False


# ------------------------------------------------------------------ 4 IDE'ler
def _ev() -> str:
    return os.path.expanduser("~")


def _appdata() -> str:
    return os.environ.get("APPDATA") or os.path.join(_ev(), "AppData", "Roaming")


def ide_listesi() -> dict:
    """ad -> (ayar dosyasi, ust anahtar, 'kurulu mu' klasoru). Her IDE'nin MCP dosya semasi farkli:
    Cursor/Windsurf/Claude Desktop 'mcpServers', VS Code 'servers'."""
    if sys.platform == "darwin":
        vscode = os.path.join(_ev(), "Library", "Application Support", "Code", "User", "mcp.json")
        claude_d = os.path.join(_ev(), "Library", "Application Support", "Claude", "claude_desktop_config.json")
    elif os.name == "nt":
        vscode = os.path.join(_appdata(), "Code", "User", "mcp.json")
        claude_d = os.path.join(_appdata(), "Claude", "claude_desktop_config.json")
    else:
        vscode = os.path.join(_ev(), ".config", "Code", "User", "mcp.json")
        claude_d = os.path.join(_ev(), ".config", "Claude", "claude_desktop_config.json")
    return {
        "cursor":         (os.path.join(_ev(), ".cursor", "mcp.json"), "mcpServers", os.path.join(_ev(), ".cursor")),
        "vscode":         (vscode, "servers", os.path.dirname(vscode)),
        "windsurf":       (os.path.join(_ev(), ".codeium", "windsurf", "mcp_config.json"), "mcpServers",
                           os.path.join(_ev(), ".codeium", "windsurf")),
        "claude-desktop": (claude_d, "mcpServers", os.path.dirname(claude_d)),
    }


def sunucu_girdisi() -> dict:
    py = sistem_python() or "python"
    sunucu = os.path.join(ROOT, "server", "apprentice_server.py").replace("\\", "/")
    return {"command": py.replace("\\", "/"), "args": [sunucu], "env": {"PYTHONIOENCODING": "utf-8"}}


def ide_ayarla(ad: str, yol: str, anahtar: str, kurulu_dir: str) -> bool:
    istenen = sunucu_girdisi()
    if ad == "vscode":
        istenen = {"type": "stdio", **istenen}
    cfg = {}
    if os.path.exists(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(UYARI + "%s ayar dosyasi okunamadi (%s): %s" % (ad, yol, e))
            return False
    mevcut = (cfg.get(anahtar) or {}).get("apprentice")
    if mevcut and mevcut.get("args") == istenen["args"] and mevcut.get("command") == istenen["command"]:
        print(OK + "%s: apprentice kayitli (%s)" % (ad, yol))
        return True
    if not DEGISTIR:
        print(UYARI + "%s: apprentice kayitli degil ya da yolu farkli (%s)" % (ad, yol))
        return False
    cfg.setdefault(anahtar, {})["apprentice"] = istenen
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(OK + "%s: yazildi -> %s  (IDE aciksa MCP listesini yenile)" % (ad, yol))
    return True


def mcp_json_guncelle():
    """Claude Code icin depodaki .mcp.json: 'python' PATH'te yoksa (gomulu Python) gercek yolu yaz."""
    p = os.path.join(ROOT, ".mcp.json")
    py = sistem_python()
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        g = cfg.setdefault("mcpServers", {}).setdefault("apprentice", {})
        if py and (shutil.which("python") is None or py.startswith(GOMULU_DIR)):
            if DEGISTIR and g.get("command") != py.replace("\\", "/"):
                g["command"] = py.replace("\\", "/")
                with open(p, "w", encoding="utf-8", newline=chr(10)) as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                print(OK + "Claude Code: .mcp.json komutu gomulu Python'a cevrildi")
                return
        print(OK + "Claude Code: depodaki .mcp.json ile otomatik (bu klasorde 'claude' ac)")
    except Exception as e:
        print(UYARI + ".mcp.json guncellenemedi: %s" % e)


def kontrol_ideler(secim: str = "") -> bool:
    ideler = ide_listesi()
    istenenler = [x.strip() for x in secim.split(",") if x.strip()] if secim else []
    bulundu, hepsi_ok = 0, True
    for ad, (yol, anahtar, kurulu_dir) in ideler.items():
        kurulu = os.path.isdir(kurulu_dir)
        if istenenler and ad not in istenenler:
            continue
        if not kurulu and not istenenler:
            continue                      # kurulu olmayan IDE'ye dokunma
        if ad == "claude-desktop" and not istenenler:
            continue                      # IDE degil; yalnizca --ide ile
        bulundu += 1
        hepsi_ok = ide_ayarla(ad, yol, anahtar, kurulu_dir) and hepsi_ok
    if not bulundu:
        print(UYARI + "Kurulu IDE bulunamadi (cursor / vscode / windsurf / claude-desktop). "
                      "--ide <ad> ile zorla ya da Claude Code kullan.")
    return hepsi_ok


# ------------------------------------------------------------------ 5 oz-test
def oz_test() -> bool:
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        from test_server import Client
    except Exception as e:
        print(HATA + "test istemcisi yuklenemedi: %s" % e)
        return False
    home = os.path.join(ROOT, ".apprentice_test_home")
    import test_server as _ts
    _ts.sys.executable = sistem_python() or sys.executable   # exe icinden: sunucuyu gercek Python'la ac
    c = Client({"APPRENTICE_HOME": home})
    try:
        c.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                              "clientInfo": {"name": "kur", "version": "0"}})
        c.notify("notifications/initialized")
        araclar = [t["name"] for t in c.call("tools/list")["tools"]]
        rep = c.tool("worker_run", {"gorev": "kurulum duman testi", "ortam": "fake",
                                    "kabul_kriterleri": ["x"]}, timeout=60)["structuredContent"]
        ok = rep.get("derleme_durumu") == "derlendi"
        print((OK if ok else HATA) + "Sunucu el sikisti, araclar: %s, fake tur: %s" % (araclar, rep.get("derleme_durumu")))
        return ok
    except Exception as e:
        print(HATA + "oz-test basarisiz: %s" % str(e)[:300])
        return False
    finally:
        c.close()


# ------------------------------------------------------------------ kural
KURAL = """---
description: Apprentice - yerel isci modeli denetle (worker_run)
alwaysApply: true
---
Bu projede kod yazma isi apprentice.worker_run aracina verilir; sen DENETCISIN.
- Kodu kendin yazma. Gorevi ve KABUL KRITERLERINI sen yaz: somut, olculebilir, ornek girdi -> beklenen cikti.
- ortam "code". calisma_dizini yazma (workspace koku); gerekirse gorele alt klasor ver.
- Uzun surebilecek islerde bekle=false ver, worker_status(is_id) ile sor.
- Donen 'ozet' beyandir, kanit degil. 'olcumler' (run_tests ciktisi) ve 'yazilan_dosyalar[].icerik' uzerinden
  kendin dogrula; kose durumlarini dusun; tutmayan varsa ayni 'oturum' ile SOMUT geri bildirim ver
  (hangi girdi, ne bekleniyor, ne geldi). Genel "testler tutmuyor" deme.
- En fazla 4 tur. Bitince: tur sayisi, sure, her kriter nasil dogrulandi.
"""


def kural_yaz(proje: str) -> bool:
    """Cursor: .cursor/rules/apprentice.mdc (otomatik uygulanir). Diger IDE'ler icin ayni metin
    APPRENTICE.md olarak proje kokune; kullanici sohbete '@APPRENTICE.md' der ya da
    Copilot icin .github/copilot-instructions.md'ye ekler."""
    d = os.path.join(proje, ".cursor", "rules")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "apprentice.mdc")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(KURAL)
    print(OK + "Cursor kurali yazildi: %s" % p)
    govde = KURAL.split("---")[-1].strip() + "\n"
    p2 = os.path.join(proje, "APPRENTICE.md")
    with open(p2, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Apprentice denetci kurali\n\n" + govde)
    print(OK + "Genel kural yazildi: %s  (VS Code/Copilot: .github/copilot-instructions.md'ye ekle)" % p2)
    return True


# ------------------------------------------------------------------ main
def main() -> int:
    global DEGISTIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--kontrol", action="store_true", help="hicbir sey degistirme")
    ap.add_argument("--olc", action="store_true", help="num_batch olcumu yap ve yaz")
    ap.add_argument("--kural", metavar="PROJE", help="denetci kural dosyasini bu projeye yaz")
    ap.add_argument("--ide", default="", help="virgulle: cursor,vscode,windsurf,claude-desktop (bos = kurulu olanlar)")
    a = ap.parse_args()
    DEGISTIR = not a.kontrol

    if a.kural:
        return 0 if kural_yaz(a.kural) else 1

    print("Apprentice kurulum  (%s, %s)" % (platform.system(), ROOT))
    sonuc = []
    adim(1, "Python");        sonuc.append(kontrol_python())
    adim(2, "Ollama");        sonuc.append(kontrol_ollama())
    adim(3, "Model");         sonuc.append(kontrol_model() if sonuc[-1] else False)
    adim(4, "IDE'ler")
    sonuc.append(kontrol_ideler(a.ide))
    mcp_json_guncelle()
    adim(5, "Oz-test");       sonuc.append(oz_test())
    if a.olc and all(sonuc[:3]):
        adim(6, "num_batch olcumu (2-3 dk)")
        r = subprocess.run([sistem_python() or sys.executable, os.path.join(ROOT, "core", "olcum.py"), "--yaz"])
        sonuc.append(r.returncode == 0)

    print()
    if all(sonuc):
        print("HAZIR. IDE'ni ac, MCP listesinde 'apprentice' yesil olsun (gerekirse yenile).")
        print("Proje icin kural dosyasi: python kur.py --kural <proje_klasoru>  (denetci rolu otomatik uygulanir)")
        return 0
    print("EKSIK ADIM VAR - yukaridaki [X] satirlarini tamamlayip tekrar calistir.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

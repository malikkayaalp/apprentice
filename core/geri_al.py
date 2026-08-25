"""GERI ALMA (rollback): isin calisma alaninda yaptigi degisikligi geri cevirme.

NEDEN GIT ONCE: `write` olaylari before/after tasir ama `run_shell` calisma alanini olay
gunlugune HIC girmeden degistirebilir (code_runner.py:252 dogrudan shell() cagirir, write
olayi basmaz). Yani gunluk tek basina butun mutasyonlari kapsamaz. Git ise degisikligi KIMIN
yaptigina bakmaz - dosya sistemine bakar. Bu yuzden birincil yontem git, gunluk yedektir.

UC YONTEM, DUSEN SIRAYLA:
  git     - calisma alani git deposu. Is BASLARKEN HEAD + kirli dosya listesi kaydedilir;
            geri alirken "simdi kirli ama BASLARKEN kirli DEGILDI" olan dosyalar isin
            eseridir. run_shell ile yapilmis degisiklik de buraya dusr - bosluk kapanir.
  gunluk  - git yok ama kabuk araci da kosmamis. write olaylarinin before'u guvenilirdir.
  yok     - git yok VE kabuk kosmus. Geri alma MUMKUN DEGIL denir, sebebi yazilir.
            Calismayan dugme koymaktansa dugmeyi hic koymamak.

GUVENLIK KURALLARI (hepsi kodda zorunlu):
  1. Kullanicinin KENDI degisikligine dokunulmaz. Is baslarken zaten kirli olan dosya
     atlanir - o kullanicinin isi, cirağın degil.
  2. Is bittikten SONRA degismis dosya atlanir. Icerik isin yazdigindan farkliysa araya
     baska biri girmistir; geri almak onun emegini siler.
  3. Calisma alani disina cikan hicbir yol islenmez.
  4. Once PLAN, sonra uygulama. plan() hicbir sey degistirmez; ne yapilacagini soyler.
  5. `git reset --hard` / `git clean` KULLANILMAZ - genis silme yapan komutlar bu projede
     run_shell'de de yasak. Yalniz DOSYA BAZINDA geri yazma/silme yapilir.
"""
from __future__ import annotations
import json, os, subprocess

PENCERESIZ = 0x08000000 if os.name == "nt" else 0     # MS-DOS penceresi acilmasin (yasandi)


def _git(workdir: str, *arg, timeout: int = 30):
    try:
        return subprocess.run(["git", "-C", workdir] + list(arg), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=PENCERESIZ)
    except Exception:
        return None


def git_deposu_mu(workdir: str) -> bool:
    r = _git(workdir, "rev-parse", "--git-dir")
    return bool(r and r.returncode == 0)


def _kirli(workdir: str) -> dict:
    """git status --porcelain -> {yol: durum}. Yollar '/' ile normallenir."""
    r = _git(workdir, "status", "--porcelain", "--untracked-files=all")
    out: dict = {}
    if not r or r.returncode != 0:
        return out
    for satir in (r.stdout or "").splitlines():
        if len(satir) < 4:
            continue
        durum, yol = satir[:2], satir[3:].strip().strip('"')
        if " -> " in yol:                       # yeniden adlandirma: hedefi al
            yol = yol.split(" -> ", 1)[1]
        out[yol.replace("\\", "/")] = durum
    return out


def anlik(workdir: str) -> dict:
    """IS BASLARKEN cekilen anlik goruntu. job.json'a yazilir; geri alma buna dayanir.
    Ucuzdur: git komutu iki tane, dosya kopyalanmaz."""
    if not workdir or not os.path.isdir(workdir):
        return {"yontem": "yok", "sebep": "calisma dizini yok"}
    if not git_deposu_mu(workdir):
        return {"yontem": "yok", "sebep": "calisma alani git deposu degil"}
    r = _git(workdir, "rev-parse", "HEAD")
    dl = _git(workdir, "rev-parse", "--abbrev-ref", "HEAD")
    return {"yontem": "git",
            "head": (r.stdout or "").strip() if r and r.returncode == 0 else "",
            # DAL da kaydedilir: isin hangi ZEMINE yazildigini soyler. "Su an hangi
            # daldayiz"dan degerlidir - kod o dala yazilmistir, sonra dal degisebilir.
            "dal": (dl.stdout or "").strip() if dl and dl.returncode == 0 else "",
            "kirli": sorted(_kirli(workdir))}     # BASLARKEN zaten kirli olanlar: dokunulmaz


def zemin(workdir: str) -> dict:
    """Calisma alaninin SU ANKI git zemini: hangi dal, worktree temiz mi.
    Ise baslamadan once gorunur olmali - cirak bu zemine yazacak."""
    if not workdir or not os.path.isdir(workdir) or not git_deposu_mu(workdir):
        return {"git": False}
    dl = _git(workdir, "rev-parse", "--abbrev-ref", "HEAD")
    kirli = _kirli(workdir)
    return {"git": True,
            "dal": (dl.stdout or "").strip() if dl and dl.returncode == 0 else "",
            "kirli_sayisi": len(kirli),
            "temiz": not kirli}


def _guvenli(workdir: str, yol: str) -> str | None:
    """Calisma alani icinde mi? Disari cikan yolu ISLEMEYIZ (mutlak yol, .., surucu)."""
    y = (yol or "").replace("\\", "/").strip()
    if not y or ".." in y.split("/") or y.startswith("/") or os.path.splitdrive(y)[0]:
        return None
    tam = os.path.realpath(os.path.join(workdir, y))
    kok = os.path.realpath(workdir)
    return tam if tam == kok or tam.startswith(kok + os.sep) else None


def _olaylar(jobs_dir: str, jid: str) -> list:
    out = []
    try:
        with open(os.path.join(jobs_dir, jid, "events.jsonl"), encoding="utf-8",
                  errors="replace") as f:
            for satir in f:
                try:
                    e = json.loads(satir)
                    if isinstance(e, dict):   # 'null'/'42'/'[]' de gecerli
                        out.append(e)          # JSON'dur - olay DEGILDIR
                except Exception:
                    continue
    except OSError:
        pass
    return out


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def plan(jobs_dir: str, jid: str) -> dict:
    """Geri alma PLANI. HICBIR SEY DEGISTIRMEZ - ne yapilacagini soyler.

    Doner: {mumkun, yontem, sebep, eylemler[], atlanan[]}
      eylem: {"yol", "eylem": "geri_yaz"|"sil", "kaynak": "git"|"gunluk"}
      atlanan: {"yol", "sebep"} - kullanicinin kendi degisikligi, sonradan degismis dosya vb.
    """
    try:
        with open(os.path.join(jobs_dir, jid, "job.json"), encoding="utf-8") as f:
            kayit = json.load(f)
    except Exception:
        return {"mumkun": False, "yontem": "yok", "sebep": "is bulunamadi",
                "eylemler": [], "atlanan": []}
    workdir = kayit.get("calisma_dizini") or ""
    ag = kayit.get("anlik") or {}
    olaylar = _olaylar(jobs_dir, jid)
    kabuk = sorted({e.get("name") for e in olaylar
                    if e.get("type") == "tool" and e.get("name") in ("run_shell", "run_tests")})
    yazimlar: dict = {}
    for e in olaylar:
        if e.get("type") == "write":
            y = (e.get("path") or "").replace("\\", "/")
            d = yazimlar.setdefault(y, {"ilk_once": e.get("before") or ""})
            d["son_sonra"] = e.get("after") or ""

    if not workdir or not os.path.isdir(workdir):
        return {"mumkun": False, "yontem": "yok", "sebep": "calisma dizini bulunamadi",
                "eylemler": [], "atlanan": []}

    eylemler, atlanan = [], []

    # --- 1. YONTEM: GIT (kim degistirdiginden bagimsiz - run_shell boslugunu kapatir) ---
    if ag.get("yontem") == "git" and git_deposu_mu(workdir):
        basta_kirli = set(ag.get("kirli") or [])
        for yol, durum in sorted(_kirli(workdir).items()):
            tam = _guvenli(workdir, yol)
            if tam is None:
                atlanan.append({"yol": yol, "sebep": "calisma alani disinda"})
                continue
            if yol in basta_kirli:
                # KURAL 1: is baslamadan da kirliydi -> kullanicinin kendi isi
                atlanan.append({"yol": yol, "sebep": "iş başlamadan da değişikti (senin işin)"})
                continue
            if durum.strip() == "??":
                eylemler.append({"yol": yol, "eylem": "sil", "kaynak": "git"})
            else:
                eylemler.append({"yol": yol, "eylem": "geri_yaz", "kaynak": "git"})
        return {"mumkun": bool(eylemler), "yontem": "git",
                "sebep": ("git anlik goruntusu var: kabuk komutuyla yapilan degisiklik de "
                          "kapsanir" if eylemler else "geri alinacak degisiklik yok"),
                "eylemler": eylemler, "atlanan": atlanan}

    # --- 2. YONTEM: OLAY GUNLUGU (yalniz kabuk kosmadiysa guvenilir) ---
    if kabuk:
        return {"mumkun": False, "yontem": "yok",
                "sebep": ("kabuk komutu calisti (%s) ve calisma alani git deposu degil - "
                          "dosya degisiklikleri olay gunlugunde olmayabilir, geri alma "
                          "eski hali GARANTI EDEMEZ" % ", ".join(kabuk)),
                "eylemler": [], "atlanan": []}
    if not yazimlar:
        return {"mumkun": False, "yontem": "yok", "sebep": "geri alinacak yazim yok",
                "eylemler": [], "atlanan": []}
    for yol, d in sorted(yazimlar.items()):
        tam = _guvenli(workdir, yol)
        if tam is None:
            atlanan.append({"yol": yol, "sebep": "calisma alani disinda"})
            continue
        simdi = _oku(tam)
        if simdi is None:
            atlanan.append({"yol": yol, "sebep": "dosya artik yok"})
            continue
        # KURAL 2: is bittikten SONRA degismisse dokunma - baskasinin emegini silmeyelim
        if simdi != d.get("son_sonra", ""):
            atlanan.append({"yol": yol, "sebep": "iş bittikten sonra değişmiş (başkası düzenlemiş)"})
            continue
        eylemler.append({"yol": yol, "eylem": "sil" if not d["ilk_once"] else "geri_yaz",
                         "kaynak": "gunluk"})
    return {"mumkun": bool(eylemler), "yontem": "gunluk",
            "sebep": ("butun degisiklikler write olaylarinda kayitli; kabuk araci kosmadi"
                      if eylemler else "geri alinacak degisiklik kalmadi"),
            "eylemler": eylemler, "atlanan": atlanan}


def uygula(jobs_dir: str, jid: str, p: dict | None = None) -> dict:
    """Plani UYGULA. Plan verilmezse yeniden hesaplanir (yaris riskini azaltmak icin
    cagiran taraf plani gostermis olmali)."""
    p = p or plan(jobs_dir, jid)
    if not p.get("mumkun"):
        return {"hata": p.get("sebep") or "geri alinamaz", "yapildi": [], "basarisiz": []}
    try:
        with open(os.path.join(jobs_dir, jid, "job.json"), encoding="utf-8") as f:
            workdir = json.load(f).get("calisma_dizini") or ""
    except Exception:
        return {"hata": "is bulunamadi", "yapildi": [], "basarisiz": []}

    yazimlar: dict = {}
    for e in _olaylar(jobs_dir, jid):
        if e.get("type") == "write":
            y = (e.get("path") or "").replace("\\", "/")
            yazimlar.setdefault(y, {"ilk_once": e.get("before") or ""})

    yapildi, basarisiz = [], []
    for ey in p.get("eylemler") or []:
        yol, tam = ey["yol"], _guvenli(workdir, ey["yol"])
        if tam is None:
            basarisiz.append({"yol": yol, "sebep": "calisma alani disinda"})
            continue
        try:
            if ey["kaynak"] == "git":
                if ey["eylem"] == "sil":
                    os.remove(tam)
                else:
                    # DOSYA BAZINDA geri yazma; `git reset --hard`/`git clean` KULLANILMAZ
                    r = _git(workdir, "checkout", "--", yol)
                    if not r or r.returncode != 0:
                        basarisiz.append({"yol": yol,
                                          "sebep": (r.stderr if r else "git calismadi")[:120]})
                        continue
            else:
                if ey["eylem"] == "sil":
                    os.remove(tam)
                else:
                    with open(tam, "w", encoding="utf-8", newline="") as f:
                        f.write(yazimlar.get(yol, {}).get("ilk_once", ""))
            yapildi.append(ey)
        except OSError as e:  # noqa: BLE001
            basarisiz.append({"yol": yol, "sebep": str(e)[:120]})
    return {"yapildi": yapildi, "basarisiz": basarisiz, "atlanan": p.get("atlanan") or [],
            "yontem": p.get("yontem")}

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


def _gitb(workdir: str, *arg, timeout: int = 30):
    """_git'in BAYT donen surumu. `--porcelain -z` ciktisi NUL ayracli ve KACISSIZDIR;
    metne cevirip satirlara bolmek o guvenceyi bozar."""
    try:
        return subprocess.run(["git", "-C", workdir] + list(arg), capture_output=True,
                              timeout=timeout, creationflags=PENCERESIZ)
    except Exception:
        return None


def _kirli(workdir: str) -> dict:
    """git status -> {yol: durum}. Yollar '/' ile normallenir.

    `-z` KULLANILIR, cunku duz `--porcelain` cikisi:
      - bosluk/ozel karakter iceren yolu TIRNAKLAR ve C-kacisi uygular ("src/\\303\\266.py"),
      - yeniden adlandirmayi `"eski" -> "yeni"` diye yazar.
    Eski ayristirma `satir[3:].strip().strip('"')` yapiyordu: tirnakli Unicode yolu
    cozemiyor, yeniden adlandirmada ise `"yeni.py` gibi BAS TIRNAKLI bozuk yol uretiyordu -
    o yol hicbir dosyayla eslesmedigi icin geri alma sessizce ISKALIYORDU.
    `-z` ciktisi NUL ayracli, tirnaksiz, kacissizdir; yeniden adlandirmada iki kayit
    ard arda gelir: once YENI ad, sonra ESKI ad."""
    r = _gitb(workdir, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    out: dict = {}
    if not r or r.returncode != 0:
        return out
    # Windows'ta yol baytlari sistem kod sayfasi olabilir; surrogateescape ile kayipsiz tut.
    parcalar = (r.stdout or b"").split(b"\x00")
    i = 0
    while i < len(parcalar):
        kayit = parcalar[i]
        i += 1
        if len(kayit) < 4:
            continue
        durum = kayit[:2].decode("ascii", "replace")
        yol = kayit[3:].decode("utf-8", "surrogateescape")
        if durum[0] in ("R", "C"):
            # yeniden adlandirma/kopyalama: SONRAKI kayit ESKI addir, onu atla.
            # Hedef (yeni ad) bizi ilgilendirir - degisiklik orada.
            i += 1
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


def _bitis(jobs_dir: str, jid: str, olaylar: list | None = None) -> float:
    """Isin GERCEK bitis ani. 0 = bilinmiyor.

    ONCE OLAYIN ZAMAN DAMGASI: `exit` (yoksa `result`) olayinin `t` alani. Bu, iscinin
    gercekten durdugu andir.

    NEDEN MTIME DEGIL: ilk surum events.jsonl'in mtime'ini kullaniyordu. Ama panel, is
    bittikten SONRA dosyaya `usta_rapor` olayi ekliyor (panel.py:_usta_rapor_tamamla) -
    mtime o anda ILERI kayiyor. Sonuc: kullanicinin isin bitisi ile usta raporu arasinda
    yaptigi duzenleme "is SIRASINDA olmus" sayilip GERI ALINABILIYORDU. Yani koruma tam da
    korumasi gereken pencerede delikti.

    Olayda damga yoksa (eski kayit) mtime'a duseriz - o zaman da SLACK payi vardir."""
    for e in reversed(olaylar or _olaylar(jobs_dir, jid)):
        if e.get("type") in ("exit", "result") and isinstance(e.get("t"), (int, float)):
            return float(e["t"])
    try:
        return os.path.getmtime(os.path.join(jobs_dir, jid, "events.jsonl"))
    except OSError:
        return 0.0


SLACK = 2.0    # dosya sistemi mtime cozunurlugu + isin son saniyesindeki yazimlar icin pay


def _sonradan_degismis(tam: str, bitis: float, beklenen: str | None) -> str:
    """Dosya IS BITTIKTEN SONRA degismis mi? Doner: sebep ('' = is guvenli).

    NEDEN VAR: git yolu "kim degistirdiginden bagimsiz" calisiyordu ve bu, KULLANICININ
    is bittikten sonra yaptigi duzenlemeyi de kapsiyordu. Somut zarar: cirak a.py yazar,
    kullanici elle duzeltir, GERI AL'a basar -> `git checkout -- a.py` kullanicinin emegini
    SESSIZCE siler. Daha kotusu: is bittikten sonra olusturulan YEPYENI dosya git'e '??'
    gorunur ve `os.remove` ile silinirdi. Gunluk yolunda bu kural vardi, git yolunda YOKTU.

    IKI OLCUT: (1) icerik - dosyanin write olayi varsa isci'nin BIRAKTIGI icerikle
    karsilastirilir; (2) zaman - write olayi yoksa (kabuk yazmis ya da sonradan olusmus)
    mtime bitis anina bakilir. Supheliyse DOKUNMA: yanlis atlama sadece is birakir,
    yanlis silme veri kaybettirir."""
    if beklenen is not None:
        return "" if _oku(tam) == beklenen else "iş bittikten sonra değişmiş (başkası düzenlemiş)"
    if not bitis:
        return ""
    try:
        m = os.path.getmtime(tam)
    except OSError:
        return ""
    if m > bitis + SLACK:
        return "iş bittikten sonra oluşmuş/değişmiş (mtime iş bitişinden sonra)"
    return ""


def _oku(yol: str) -> str | None:
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _zemin_degisti(workdir: str, ag: dict) -> str:
    """Is baslarken kaydedilen git zemini hala ayni mi? Doner: sebep ('' = ayni).

    Kayitli `head` bugune kadar HIC OKUNMUYORDU: `anlik()` kaydediyordu ama `uygula()`
    duz `git checkout -- <yol>` cagiriyordu - yani INDEKSTEN/GUNCEL HEAD'den geri yaziyordu.
    Is sirasinda commit/checkout olduysa geri alma YANLIS icerigi yaziyordu."""
    bas_head = str(ag.get("head") or "")
    if not bas_head:
        return ""                       # eski kayit: denetleyemeyiz, susariz (uydurma yok)
    r = _git(workdir, "rev-parse", "HEAD")
    simdi = (r.stdout or "").strip() if r and r.returncode == 0 else ""
    if simdi and simdi != bas_head:
        return ("is baslarken HEAD %s idi, simdi %s - is sirasinda commit/checkout yapilmis. "
                "Dosyalari baska bir agacin uzerine geri yazmak tutarsiz sonuc verir; "
                "geri alma DURDURULDU." % (bas_head[:10], simdi[:10]))
    bas_dal = str(ag.get("dal") or "")
    if bas_dal:
        d = _git(workdir, "rev-parse", "--abbrev-ref", "HEAD")
        simdi_dal = (d.stdout or "").strip() if d and d.returncode == 0 else ""
        if simdi_dal and simdi_dal != bas_dal:
            return ("is '%s' dalina yazildi, simdi '%s' dalindasin - geri alma DURDURULDU."
                    % (bas_dal, simdi_dal))
    return ""


# NOT (denenip BIRAKILDI): dosyayi `git show <head>:<yol>` ile okuyup ham bayt yazmak.
# Amac indekse dokunmamakti. AMA `git show` BLOB'u verir - satir sonu/temizleme suzgeclerini
# (autocrlf, .gitattributes text=auto, smudge) UYGULAMAZ. Sonuc: LF yazilir, git CRLF bekler,
# geri yazilan dosya HALA "degismis" gorunur ve ikinci geri alma ayni dosyayi tekrar yakalar.
# Bunu mevcut senaryo testi yakaladi (`geri_alma_zor_durumlar`, "ikinci kez guvenli" adimi).
# Dogrusu git'in KENDI checkout'u - ama GUNCEL HEAD'den degil, KAYITLI baslangic HEAD'inden:
#     git checkout <baslangic_head> -- <yol>
# Bu hem suzgecleri uygular hem de dogru surumu yazar. Indeksi de o surume ceker; zaten
# yalnizca "is baslarken temiz olan" dosyalara dokundugumuz icin indeksin baslangic hali
# tam olarak odur.


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
        # ZEMIN DENETIMI: is BASLARKEN kaydedilen HEAD/dal hala gecerli mi?
        # Degistiyse (commit, checkout, pull, rebase) dosyalari geri yazmak, dosyalari
        # BASKA bir agacin uzerine koymak demektir - tutarsiz bir calisma agaci uretir.
        # Yanlis icerik yazmaktansa DURUP SEBEBINI SOYLERIZ.
        zemin_hata = _zemin_degisti(workdir, ag)
        if zemin_hata:
            return {"mumkun": False, "yontem": "yok", "sebep": zemin_hata,
                    "eylemler": [], "atlanan": []}
        basta_kirli = set(ag.get("kirli") or [])
        bitis = _bitis(jobs_dir, jid, olaylar)
        for yol, durum in sorted(_kirli(workdir).items()):
            tam = _guvenli(workdir, yol)
            if tam is None:
                atlanan.append({"yol": yol, "sebep": "calisma alani disinda"})
                continue
            if yol in basta_kirli:
                # KURAL 1: is baslamadan da kirliydi -> kullanicinin kendi isi
                atlanan.append({"yol": yol, "sebep": "iş başlamadan da değişikti (senin işin)"})
                continue
            # KURAL 2: is bittikten SONRA degismisse dokunma. Gunluk yolunda bu kural
            # bastan beri vardi, git yolunda YOKTU - kullanicinin sonradan yaptigi
            # duzenleme `git checkout` ile sessizce siliniyordu.
            sebep = _sonradan_degismis(tam, bitis, yazimlar.get(yol, {}).get("son_sonra"))
            if sebep:
                atlanan.append({"yol": yol, "sebep": sebep})
                continue
            # KURAL 3: IS SIRASINDA degismis ama CIRAK YAZMAMIS dosya.
            # Kabuk KOSMADIYSA cirak dosyayi ancak write_file ile degistirebilir - yani
            # olay gunlugunde izi olur. Iz yoksa o degisiklik KULLANICININDIR ve is
            # devam ederken yapilmistir; geri almak onun emegini siler.
            # Kabuk KOSTUYSA ayirt edemeyiz (run_shell gunluge girmez): o zaman plana
            # alinir ama "belirsiz" isaretiyle - kullanici ONAYLAMADAN once gorsun.
            if yol not in yazimlar:
                if not kabuk:
                    atlanan.append({"yol": yol,
                                    "sebep": "iş sırasında değişmiş ama çırak yazmamış "
                                             "(kabuk koşmadı — bu senin düzenlemen)"})
                    continue
                belirsiz = True
            else:
                belirsiz = False
            ey = {"yol": yol, "kaynak": "git",
                  "eylem": "sil" if durum.strip() == "??" else "geri_yaz"}
            if belirsiz:
                ey["belirsiz"] = ("çırağın yazma kaydı yok; kabuk (%s) koştuğu için "
                                  "onun eseri olabilir" % ", ".join(kabuk))
            eylemler.append(ey)
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
            d = yazimlar.setdefault(y, {"ilk_once": e.get("before") or ""})
            d["son_sonra"] = e.get("after") or ""

    olaylar_u = _olaylar(jobs_dir, jid)
    bitis = _bitis(jobs_dir, jid, olaylar_u)
    # Kayitli baslangic HEAD'i: geri yazma bunun uzerinden yapilir.
    bas_head = ""
    try:
        with open(os.path.join(jobs_dir, jid, "job.json"), encoding="utf-8") as f:
            ag_u = json.load(f).get("anlik") or {}
        bas_head = str(ag_u.get("head") or "")
        if ag_u.get("yontem") == "git":
            z = _zemin_degisti(workdir, ag_u)
            if z:      # PLAN ile UYGULA arasinda dal/HEAD degismis olabilir - yine bakariz
                return {"hata": z, "yapildi": [], "basarisiz": [], "atlanan": []}
    except Exception:  # noqa: BLE001
        pass
    yapildi, basarisiz, atlanan = [], [], list(p.get("atlanan") or [])
    for ey in p.get("eylemler") or []:
        yol, tam = ey["yol"], _guvenli(workdir, ey["yol"])
        if tam is None:
            basarisiz.append({"yol": yol, "sebep": "calisma alani disinda"})
            continue
        # SON KONTROL: plan gosterildikten SONRA dosya degismis olabilir (kullanici
        # onay ekranindayken duzenlemis olabilir). Yikici adimin hemen oncesinde
        # yeniden bakariz - plan ne kadar taze olursa olsun, yazan biz oldugumuz icin
        # sorumluluk burada.
        sebep = _sonradan_degismis(tam, bitis, yazimlar.get(yol, {}).get("son_sonra"))
        if sebep:
            atlanan.append({"yol": yol, "sebep": sebep + " - geri alma sirasinda atlandi"})
            continue
        try:
            if ey["kaynak"] == "git":
                if ey["eylem"] == "sil":
                    os.remove(tam)
                else:
                    # IS BASLARKENKI icerik geri yazilir - GUNCEL HEAD/indeks DEGIL.
                    # Eski surum `git checkout -- <yol>` cagiriyordu: (a) indeksten okur,
                    # yani is sirasinda sahnelenmis bir degisiklik varsa ONU yazardi;
                    # (b) is sirasinda commit olduysa YANLIS surumu yazardi; (c) dosyayi
                    # ayrica SAHNELERDI. `git show <baslangic_head>:<yol>` uculunu de cozer.
                    if not bas_head:
                        basarisiz.append({"yol": yol, "sebep": "is baslangic HEAD'i kayitli degil "
                                                               "(eski kayit) - geri yazilmadi"})
                        continue
                    r = _git(workdir, "checkout", bas_head, "--", yol)
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
    return {"yapildi": yapildi, "basarisiz": basarisiz, "atlanan": atlanan,
            "yontem": p.get("yontem")}

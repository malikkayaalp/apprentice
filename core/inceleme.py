"""INCELEME SOZLESMESI (ReviewSummary): runtime -> arayuz arasindaki KARARLI projeksiyon.

Neden ayri bir katman: panel bugun duz olay akisini (events.jsonl) okuyor. Yarin dugum
tabanli orkestratore gecersek olay semasi degisir ve olay semasina gore yazilmis her ekran
yeniden yazilir. Bu modul arada durur:

    olaylar / bugunku akis / yarinki DAG
                  |
            inceleme()  <-- SOZLESME (sema surumlu)
                  |
                panel

Kurallar:
  1. Burasi KARAR VERMEZ, karari KAYITTAN OKUR. Duraganligi runtime hesaplar
     (code_runner: hata imzalari iki tur ayni ise duragan=True + "duraganlik" olayi);
     burasi yalnizca o karari ve KANITINI tasir. Arayuz de hesaplamaz - yoksa UI ikinci
     bir karar motoruna doner.
  2. BEYAN ile KANIT ayrilir. Modelin kendi ozeti (`ozet`) beyandir; derleme/ruff/test
     dogrulayicidan gelir. Hesaplanamayan hicbir etiket (ornegin "risk: ORTA") URETILMEZ.
  3. Geri alinabilirlik ISPATLANIR, varsayilmaz. `write` olayi before/after tasir ama
     `run_shell` calisma alanini gunluge HIC girmeden degistirebilir (code_runner:252 -
     dogrudan shell(), write olayi basmaz; silme yasagi da alt dizge kara listesi). Bu
     yuzden kabuk komutu kosmus bir iste geri alma MUMKUN DEGIL denir ve sebebi yazilir.
"""
from __future__ import annotations
import difflib, json, os, time

SEMA = 1                      # sozlesme surumu: alan eklenirse artmaz, alan ANLAMI degisirse artar
KABUK_ARACLARI = ("run_shell", "run_tests")


def _olaylar(jobs_dir: str, jid: str) -> list:
    yol = os.path.join(jobs_dir, jid, "events.jsonl")
    out = []
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            for satir in f:
                try:
                    e = json.loads(satir)
                    if isinstance(e, dict):   # 'null'/'42'/'[]' de gecerli
                        out.append(e)          # JSON'dur - olay DEGILDIR
                except Exception:
                    continue          # cop satir akisi bozmasin
    except OSError:
        return []
    return out


def _is_kaydi(jobs_dir: str, jid: str) -> dict:
    try:
        with open(os.path.join(jobs_dir, jid, "job.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _net_fark(ilk_once: str, son_sonra: str) -> tuple:
    """Isin TAMAMINDA net degisiklik: ilk yazimin oncesi -> son yazimin sonrasi.
    Tur tur fark degil; kullanicinin sordugu 'bu is dosyayi ne yapti' sorusu budur."""
    e, y = (ilk_once or "").splitlines(), (son_sonra or "").splitlines()
    ekle = sil = 0
    for etiket, i1, i2, j1, j2 in difflib.SequenceMatcher(None, e, y, autojunk=False).get_opcodes():
        if etiket != "equal":
            sil += i2 - i1
            ekle += j2 - j1
    return ekle, sil


def _surec_canli(pid) -> bool | None:
    """PID hala yasiyor mu? None = bilinmiyor.

    NEDEN os.kill DEGIL: bu projede her alt surec CREATE_NO_WINDOW (0x08000000) ile
    baslatilir - MS-DOS penceresi acilmasin diye (kazanilmis bir duzeltme). O bayrakla
    baslatilmis bir Python surecinde os.kill(pid, 0) Windows'ta

        OSError [WinError 87] The parameter is incorrect

    veriyor - KENDI pid'i icin bile. Panel sunucusu tam o bayrakla kosuyor, yani
    os.kill'e dayanan canlilik denetimi uretimde HER ISI OKSUZ gosterirdi. Gece
    kusatmasinin batarya asamasi bunu daha kosu baslamadan yakaladi (test dogrudan
    kosunca geciyor, koşucu altinda kaliyordu - fark tam bu bayrakti).

    Windows'ta ctypes ile OpenProcess + GetExitCodeProcess kullanilir: ek paket yok,
    surec baslatilmaz, bayraktan etkilenmez.
    KENAR DURUM: 259 ile cikmis bir surec STILL_ACTIVE ile ayni gorunur - nadir ve
    zararsiz (en fazla "olu sahip canli sanilir", tersi degil)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True          # baskasinin sureci ama VAR
        except OSError:
            return None
    try:
        import ctypes
        from ctypes import wintypes
        SORGU = 0x1000                       # PROCESS_QUERY_LIMITED_INFORMATION
        HALA_CALISIYOR = 259                 # STILL_ACTIVE
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(SORGU, False, pid)
        if not h:
            return False                     # acilamiyorsa surec yok (ya da erisim yok)
        try:
            kod = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(kod)):
                return None
            return kod.value == HALA_CALISIYOR
        finally:
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return None                          # bilinmiyor - "olu" DEMEYIZ


def _sozluk(x) -> dict:
    """Sozluk bekledigimiz alan bozuk kayitta dizge/liste olabilir - bos sozluge cevir."""
    return x if isinstance(x, dict) else {}


def _sahiplik(is_kaydi: dict) -> dict:
    """TEK YAZAR KURALI: is kaydina yalniz SAHIBI yazar; baskasi okur.

    Sahip surec olduyse is OKSUZ kalir - kimse son halkayi yazmayacak demektir. Bunu
    gizlemek yerine SOYLERIZ; panel eksik olani uydurmaz (yasandi: panel, sahibi olmadigi
    MCP islerine "ustaya rapor gitti" olayi ekliyordu - usta hic bakmamis olabilir)."""
    sahip = dict(is_kaydi.get("sahip") or {})
    if not sahip:                      # eski kayit: kaynak alani ayni seyi soyler
        # MCP yolu "kaynak" damgalamaz -> BOS olan MCP'dir. "web-panel" paneldir.
        # Baska bir deger (ornegin "ornek") ne biri ne otekidir: "?" denir, uydurulmaz.
        kaynak = is_kaydi.get("kaynak") or ""
        sahip = {"rol": "panel" if kaynak == "web-panel" else ("mcp" if not kaynak else "?"),
                 "pid": None}
    pid = sahip.get("pid")
    sahip["canli"] = _surec_canli(pid) if pid else None   # None = bilinmiyor
    return sahip


def _kapsam(is_kaydi: dict) -> dict:
    """Cirak nereye yazabilir? Bos liste = calisma alaninin tamami (olculdu: liste
    verildiginde -%94 token; bu yuzden bos liste 'sinirsiz' demek ve GORUNUR olmali)."""
    liste = [str(y) for y in (is_kaydi.get("yazilabilir") or [])]
    return {"liste": liste, "sinirli": bool(liste),
            "aciklama": ("yalniz bu yollar" if liste else "calisma alaninin tamami")}


def _kapsam_disi(yol: str, kapsam: dict) -> bool:
    if not kapsam["sinirli"]:
        return False
    y = (yol or "").replace("\\", "/").lstrip("./")
    for izin in kapsam["liste"]:
        i = str(izin).replace("\\", "/").rstrip("/*").lstrip("./")
        if not i or y == i or y.startswith(i + "/"):
            return False
    return True


KABUL_DOSYASI = "kabul.json"       # kabul kriterlerini DENETLEYENIN dosyasi


def kabul_oku(jobs_dir: str, jid: str) -> dict:
    """Kabul kriterlerinin denetim sonucu (varsa).

    KIM YAZAR: kriterleri denetleyen taraf - kampanya harness'i, usta, ya da ileride bir
    dogrulayici. Isi KOSAN surec DEGIL, o yuzden events.jsonl'e degil AYRI dosyaya yazilir
    (tek yazar kurali). inceleme.json karar icin ne ise, kabul.json denetim icin odur.

    NEDEN GEREKLI: `kabul_kriterleri` bugun yalnizca TASINIYOR - iseme giriyor, is kaydina
    yaziliyor, hicbir yerde denetlenmiyor. Derleme/ruff/test gecince sozlesme "gecti" diyor
    ama kriterin tutup tutmadigini kimse bilmiyor. Olculdu (gece kusatmasi): `dama` gorevi
    kabul kriterini iki turda da tutturamadi (11/12), telemetri "ilk tur basari %100, hic
    hata yok" dedi. Yani sistem BASARISIZ bir ise BASARILI diyordu."""
    try:
        with open(os.path.join(jobs_dir, jid, KABUL_DOSYASI), encoding="utf-8") as f:
            k = json.load(f)
        return k if isinstance(k, dict) else {}
    except Exception:
        return {}


def kabul_yaz(jobs_dir: str, jid: str, gecen: int, toplam: int,
              basarisiz: list | None = None, kaynak: str = "") -> dict:
    """Kabul denetimi sonucunu kaydet. Denetleyen taraf cagirir."""
    jd = os.path.join(jobs_dir, jid)
    if not os.path.isdir(jd):
        return {"hata": "is bulunamadi"}
    try:
        gecen, toplam = int(gecen), int(toplam)
    except (TypeError, ValueError):
        return {"hata": "gecen/toplam sayi olmali"}
    if toplam < 0 or gecen < 0 or gecen > toplam:
        return {"hata": "gecersiz sayim: %s/%s" % (gecen, toplam)}
    kayit = {"sema": SEMA, "gecen": gecen, "toplam": toplam,
             "basarisiz": [str(x)[:200] for x in (basarisiz or [])][:20],
             "kaynak": kaynak or "?", "t": time.time()}
    try:
        with open(os.path.join(jd, KABUL_DOSYASI), "w", encoding="utf-8", newline="\n") as f:
            json.dump(kayit, f, ensure_ascii=False, indent=1)
    except OSError as e:
        return {"hata": str(e)[:150]}
    return kayit


def _kabul_satiri(jobs_dir: str, jid: str, kriterler: list) -> dict | None:
    """DOGRULAMA listesine eklenecek "kabul kriterleri" satiri.

    Uc hal, ucu de DURUST:
      denetlendi + tuttu   -> gecti
      denetlendi + tutmadi -> kaldi  (kac kriterin dustugu kanitta)
      HIC denetlenmedi     -> yok    ("N kriter verildi, DOGRULANMADI")
    Kriter verilmemisse satir HIC EKLENMEZ - denetlenecek bir sey yok."""
    if not kriterler:
        return None
    k = kabul_oku(jobs_dir, jid)
    if not k or not isinstance(k.get("toplam"), int):
        return {"ad": "kabul kriterleri", "durum": "yok",
                "kanit": "%d kriter verildi, DOGRULANMADI" % len(kriterler)}
    gecen, toplam = int(k.get("gecen") or 0), int(k["toplam"])
    tuttu = toplam > 0 and gecen >= toplam
    kanit = "%d/%d kontrol" % (gecen, toplam)
    if not tuttu and k.get("basarisiz"):
        kanit += " · " + str(k["basarisiz"][0])[:80]
    return {"ad": "kabul kriterleri", "durum": "gecti" if tuttu else "kaldi", "kanit": kanit}


KARAR_DOSYASI = "inceleme.json"     # INCELEYENIN dosyasi (events.jsonl KOSUCUNUN)


def karar_oku(jobs_dir: str, jid: str) -> dict:
    """Inceleyenin karari: kabul / red / (bos). TEK YAZAR KURALI geregi olay gunlugune
    DEGIL, ayri bir dosyaya yazilir - events.jsonl'in sahibi isi kosan surectir, karar ise
    inceleyenin sozudur. Ikisini ayni dosyaya karistirmak sahipligi bozar."""
    try:
        with open(os.path.join(jobs_dir, jid, KARAR_DOSYASI), encoding="utf-8") as f:
            k = json.load(f)
        return k if isinstance(k, dict) else {}
    except Exception:
        return {}


def karar_yaz(jobs_dir: str, jid: str, durum: str, ayrinti: dict | None = None) -> dict:
    """Karari kaydet. durum: "kabul" | "red". Var olan karari EZER (kullanici fikir
    degistirebilir) ama gecmisi 'onceki' altinda tutar - kayit silinmez."""
    if durum not in ("kabul", "red"):
        return {"hata": "gecersiz karar: %r" % durum}
    jd = os.path.join(jobs_dir, jid)
    if not os.path.isdir(jd):
        return {"hata": "is bulunamadi"}
    eski = karar_oku(jobs_dir, jid)
    kayit = {"sema": SEMA, "durum": durum, "t": time.time()}
    kayit.update(ayrinti or {})
    if eski.get("durum"):
        # GECMISE geri_alinan da tasinir: "daha once reddedilmisti" yetmez, KAC DOSYANIN
        # geri alindigi arayuzde gorunmeli - yoksa kod geri alinmis bir is "kabul edildi"
        # diye gorunur ve kullanici kodun durdugunu sanir.
        gecmis = {"durum": eski["durum"], "t": eski.get("t")}
        if eski.get("geri_alinan"):
            gecmis["geri_alinan"] = eski["geri_alinan"]
        kayit["onceki"] = [x for x in (eski.get("onceki") or [])][-4:] + [gecmis]
    try:
        with open(os.path.join(jd, KARAR_DOSYASI), "w", encoding="utf-8", newline="\n") as f:
            json.dump(kayit, f, ensure_ascii=False, indent=1)
    except OSError as e:
        return {"hata": str(e)[:150]}
    return kayit


def _zaman_cizgisi(olaylar: list) -> dict:
    """Sure NEREYE gitti? Olaylardan zaman dilimleri uretir (yol haritasi 11).

    NEDEN PROJEKSIYONDA: panel olay semasini BILMEZ. Zaman cizgisini panelde hesaplasaydik
    'tool' ile 'tool_result' eslesmesini arayuze ogretmis olurduk - sema degisince panel
    kirilirdi. Burada uretiliyor, panel yalnizca ciziyor.

    UC TUR DILIM, ucu de gozlemlenen sey:
      uretim    - model token uretiyordu (arac cagrilari ARASINDAKI bosluk)
      arac      - bir arac kosuyordu (tool -> tool_result arasi)
      dogrulama - son aractan sonuca kadar (derleme + test)
    ESKI KAYITLARDA ZAMAN YOK: o zaman {"var": False} doner ve panel bolumu gostermez.
    Uydurma yapmayiz - eksik olcumu tahminle doldurmak olcumu bozar."""
    damgali = [e for e in olaylar if isinstance(e.get("t"), (int, float))]
    if len(damgali) < 2:
        return {"var": False, "sebep": "olaylarda zaman damgasi yok (eski kayit)"}
    t0 = damgali[0]["t"]
    dilimler, ozet = [], {"uretim": 0.0, "arac": 0.0, "dogrulama": 0.0}
    acik = None          # bekleyen tool olayi
    onceki_son = t0      # bir onceki dilimin bittigi an

    def ekle(ad, tip, bas, bit):
        sure = round(max(0.0, bit - bas), 2)
        if sure < 0.05:                     # gorunmeyecek kadar kisa dilim gurultudur
            return
        dilimler.append({"ad": ad, "tip": tip, "bas": round(bas - t0, 2), "sure": sure})
        ozet[tip] = round(ozet[tip] + sure, 2)

    for e in damgali:
        tip, t = e.get("type"), e["t"]
        if tip == "tool":
            ekle("model üretiyor", "uretim", onceki_son, t)
            acik = (str(e.get("name") or "arac"), t)
        elif tip == "tool_result":
            if acik:
                ekle(acik[0], "arac", acik[1], t)
                acik = None
            onceki_son = t
        elif tip in ("result", "exit"):
            if acik:                        # arac yarim kaldi (cokme/zaman asimi)
                ekle(acik[0] + " (yarim)", "arac", acik[1], t)
                acik = None
            ekle("doğrulama", "dogrulama", onceki_son, t)
            onceki_son = t
        elif tip == "write":
            onceki_son = max(onceki_son, t)
    toplam = round(damgali[-1]["t"] - t0, 2)
    return {"var": bool(dilimler), "toplam": toplam, "dilimler": dilimler[:40],
            "ozet": ozet,
            # ANLAMLI ORAN: zamanin ne kadari MODEL uretiminde gecti. Bu sayi hizlandirma
            # calismasinin nereye bakmasi gerektigini soyler (model mi, arac mi, dogrulama mi).
            "uretim_orani": round(ozet["uretim"] / toplam, 3) if toplam else 0}


def inceleme(jobs_dir: str, jid: str) -> dict:
    """Bir isin INCELEME OZETI. Yalniz diskteki kayittan uretilir, model cagrilmaz."""
    olaylar = _olaylar(jobs_dir, jid)
    if not olaylar and not os.path.isdir(os.path.join(jobs_dir, jid)):
        return {"sema": SEMA, "hata": "is bulunamadi"}
    kayit = _is_kaydi(jobs_dir, jid)
    kapsam = _kapsam(kayit)
    sahiplik = _sahiplik(kayit)

    dosyalar: dict = {}          # yol -> {ilk_once, son_sonra, surum}
    sonuc: dict = {}
    duraganlik = None
    onarim_turu = 0
    kabuk_kosan = []
    beyan = ""
    cikis = None

    for e in olaylar:
        t = e.get("type")
        if t == "write":
            yol = (e.get("path") or "").replace("\\", "/")
            d = dosyalar.setdefault(yol, {"ilk_once": e.get("before") or "", "surum": 0})
            d["son_sonra"] = e.get("after") or ""
            d["surum"] += 1
        elif t == "tool" and e.get("name") in KABUK_ARACLARI:
            kabuk_kosan.append(e.get("name"))
        elif t == "onarim":
            onarim_turu = max(onarim_turu, int(e.get("tur") or 0))
        elif t == "duraganlik":
            duraganlik = {"var": True, "imza_sayisi": e.get("imza_sayisi"), "tur": e.get("tur")}
        elif t == "assistant":
            beyan = e.get("text") or beyan
        elif t == "result":
            sonuc = e
        elif t == "exit":
            cikis = e.get("code")

    # --- degisen dosyalar: net fark + kapsam ihlali ---
    degisen = []
    for yol, d in dosyalar.items():
        ekle, sil = _net_fark(d["ilk_once"], d.get("son_sonra", ""))
        degisen.append({"yol": yol, "eklenen": ekle, "silinen": sil, "surum": d["surum"],
                        "yeni": not d["ilk_once"], "kapsam_disi": _kapsam_disi(yol, kapsam)})
    degisen.sort(key=lambda x: (-(x["eklenen"] + x["silinen"]), x["yol"]))

    # --- DOGRULAMA: her satir bir KANIT; yoksa "yok" denir, "gecti" denmez ---
    ruff = sonuc.get("ruff")
    if isinstance(ruff, str):        # eski/bozuk kayit: dizge harf harf gezilmesin
        ruff = [ruff]
    ruff = list(ruff or [])
    hatalar = list(sonuc.get("errors") or [])
    dogrulama = []
    if sonuc:
        dogrulama.append({"ad": "derleme",
                          "durum": "gecti" if sonuc.get("ok") else "kaldi",
                          "kanit": ("%d hata" % len(hatalar)) if hatalar else "hata yok"})
        dogrulama.append({"ad": "ruff",
                          "durum": "kaldi" if ruff else "gecti",
                          "kanit": ("%d uyari" % len(ruff)) if ruff else "uyari yok"})
    else:
        dogrulama.append({"ad": "derleme", "durum": "yok", "kanit": "is bitmedi"})
    ks = _kabul_satiri(jobs_dir, jid, kayit.get("kabul_kriterleri") or [])
    if ks:
        dogrulama.append(ks)
    kd = [d for d in degisen if d["kapsam_disi"]]
    dogrulama.append({"ad": "yazma kapsami",
                      "durum": "kaldi" if kd else ("gecti" if kapsam["sinirli"] else "yok"),
                      "kanit": ("%d dosya kapsam disi" % len(kd)) if kd else
                               ("kapsam icinde" if kapsam["sinirli"] else "kapsam sinirlanmamis")})

    # --- DEVIR ONERISI: runtime "usta gerekli" dedi mi? (devretmedi - ONERDI) ---
    kanit = []
    if duraganlik:
        kanit.append("ayni hata imzasi 2 tur ust uste (imza: %s)" % duraganlik.get("imza_sayisi"))
        kanit.append("onarim turunda ilerleme yok")
    if sonuc and not sonuc.get("ok") and hatalar:
        kanit.append("is bittiginde %d dogrulama hatasi kaldi" % len(hatalar))
    for alan, metin in (("butce_uyarisi", "butce uyarisi"), ("hafiza_uyarisi", "HAFIZA.md siniri"),
                        ("durum_uyarisi", "STATE.md siniri")):
        if sonuc.get(alan):
            kanit.append("%s: %s" % (metin, str(sonuc[alan])[:120]))
    devir = {"var": bool(duraganlik) or bool(sonuc and not sonuc.get("ok") and hatalar),
             "sebep": "duraganlik" if duraganlik else ("dogrulama_gecmedi" if kanit else ""),
             "kanit": kanit,
             "son_hata": (hatalar[0][:400] if hatalar else "")}

    # --- GERI ALINABILIRLIK: ispat, varsayim degil ---
    # Karar artik core/geri_al.py'de: calisma alani git deposuysa degisikligi KIM yaparsa
    # yapsin (run_shell dahil) geri alinabilir; degilse yalniz kabuk kosmadiysa olay
    # gunluguyle; ikisi de yoksa MUMKUN DEGIL denir ve sebebi yazilir.
    try:
        from core.geri_al import plan as _geri_plan
        gp = _geri_plan(jobs_dir, jid)
        geri = {"mumkun": bool(gp.get("mumkun")), "sebep": gp.get("sebep") or "",
                "yontem": gp.get("yontem") or "yok",
                "eylem_sayisi": len(gp.get("eylemler") or []),
                "atlanan": gp.get("atlanan") or []}
    except Exception as e:  # noqa: BLE001
        geri = {"mumkun": False, "sebep": "geri alma plani cikarilamadi: %s" % str(e)[:80],
                "yontem": "yok", "eylem_sayisi": 0, "atlanan": []}

    durum = kayit.get("durum") or ("bitti" if sonuc else "calisiyor")
    if cikis not in (None, 0) and durum != "bitti":
        durum = "hata"

    return {
        "sema": SEMA,
        "is_id": jid,
        "durum": durum,
        "ortam": kayit.get("ortam") or "",     # code | fake (fake = duman testi, olcume girmez)
        "kaynak": kayit.get("kaynak") or "",   # web-panel | mcp | ornek (olcum bunu eler)
        "baslik": kayit.get("baslik") or "",
        "gorev": kayit.get("gorev") or "",
        "model": kayit.get("model") or "",
        "calisma_dizini": kayit.get("calisma_dizini") or "",
        "yazma_kapsami": kapsam,
        # ZEMIN: is HANGI git zeminine yazildi. Anlik goruntuden gelir (is baslarken
        # cekilmisti), "su an hangi daldayiz"dan degerli - dal sonradan degismis olabilir.
        "zemin": {"git": (kayit.get("anlik") or {}).get("yontem") == "git",
                  "dal": (kayit.get("anlik") or {}).get("dal") or "",
                  "basta_kirli": len((kayit.get("anlik") or {}).get("kirli") or [])},
        "sahiplik": sahiplik,
        "degisen_dosyalar": degisen,
        "dogrulama": dogrulama,
        "onarim_turu": onarim_turu,
        "duraganlik": duraganlik or {"var": False},
        "devir_onerisi": devir,
        "uyarilar": [str(u) for u in ruff[:8]],
        "kullanim": _sozluk(sonuc.get("kullanim")) or _sozluk(kayit.get("kullanim")),
        "sure": sonuc.get("wall") or kayit.get("sure") or 0,
        "beyan": beyan[:600],            # modelin kendi ozeti - KANIT DEGIL, ayri alanda durur
        # BAGLAM KESILMESI ve ETKIN AYARLAR (denetim bulgulari 5 ve 4). Ikisi de runtime'da
        # URETILIYOR ama hicbir yere ULASMIYORDU. Panel olay semasini bilmedigi icin
        # projeksiyona konuyor - arayuz yalnizca ciziyor.
        "kesilme": _sozluk(sonuc.get("kesilme")) or None,
        "ayarlar": _sozluk(sonuc.get("ayarlar")) or None,
        "zaman_cizgisi": _zaman_cizgisi(olaylar),
        "geri_alinabilir": geri,
        "karar": karar_oku(jobs_dir, jid),
        "kabul": kabul_oku(jobs_dir, jid),
        "kabul_kriterleri": list(kayit.get("kabul_kriterleri") or []),
        # OTURUM: ayni gorevin ard arda denemelerini birbirine baglar. Duraganligi
        # DENEMELER ARASI gormek icin gerekli - tek is icine bakmak yetmez.
        "oturum": kayit.get("oturum") or "",
    }

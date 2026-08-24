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
import difflib, json, os

SEMA = 1                      # sozlesme surumu: alan eklenirse artmaz, alan ANLAMI degisirse artar
KABUK_ARACLARI = ("run_shell", "run_tests")


def _olaylar(jobs_dir: str, jid: str) -> list:
    yol = os.path.join(jobs_dir, jid, "events.jsonl")
    out = []
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            for satir in f:
                try:
                    out.append(json.loads(satir))
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


def inceleme(jobs_dir: str, jid: str) -> dict:
    """Bir isin INCELEME OZETI. Yalniz diskteki kayittan uretilir, model cagrilmaz."""
    olaylar = _olaylar(jobs_dir, jid)
    if not olaylar and not os.path.isdir(os.path.join(jobs_dir, jid)):
        return {"sema": SEMA, "hata": "is bulunamadi"}
    kayit = _is_kaydi(jobs_dir, jid)
    kapsam = _kapsam(kayit)

    dosyalar: dict = {}          # yol -> {ilk_once, son_sonra, surum}
    sonuc: dict = {}
    duraganlik = None
    onarim_turu = 0
    kabuk_kosan = []
    kapali_araclar = []
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
        elif t == "system" and e.get("subtype") == "tools_off":
            ham = e.get("tools")
            kapali_araclar = ham if isinstance(ham, list) else [str(ham)]
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
    if kabuk_kosan:
        geri = {"mumkun": False,
                "sebep": "kabuk komutu calisti (%s) - dosya degisiklikleri olay gunlugunde "
                         "olmayabilir, geri alma calisma alanini eski haline dondurmeyi "
                         "GARANTI EDEMEZ" % ", ".join(sorted(set(kabuk_kosan)))}
    elif not dosyalar:
        geri = {"mumkun": False, "sebep": "geri alinacak yazim yok"}
    else:
        geri = {"mumkun": True,
                "sebep": "butun degisiklikler write olaylarinda (before/after) kayitli%s"
                         % ("; kabuk araclari kapaliydi: " + ", ".join(kapali_araclar)
                            if kapali_araclar else "")}

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
        "degisen_dosyalar": degisen,
        "dogrulama": dogrulama,
        "onarim_turu": onarim_turu,
        "duraganlik": duraganlik or {"var": False},
        "devir_onerisi": devir,
        "uyarilar": [str(u) for u in ruff[:8]],
        "kullanim": sonuc.get("kullanim") or kayit.get("kullanim") or {},
        "sure": sonuc.get("wall") or kayit.get("sure") or 0,
        "beyan": beyan[:600],            # modelin kendi ozeti - KANIT DEGIL, ayri alanda durur
        "geri_alinabilir": geri,
    }

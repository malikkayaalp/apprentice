"""POLITIKA: gozetimsiz kosuda "bu isten sonra ne olacak" sorusunu KOD cevaplar.

NEDEN: kuyruk tek basina tehlikelidir. Gece 12 is siraladin, ikincisi kaldi, kuyruk devam
etti ve kalan 10 is BOZUK BIR TEMEL uzerine calisti. Asil risk "bir is kaldi" degil,
"bir is kaldi ve kimse durmadi"dir.

KARARI MODEL VERMEZ. Bu projenin kurucu olcumu: isci ham olcumu kendi yorumlayip
duzeltmeye kalkinca YAKINSAMADI. Ayni sebeple "is iyi mi" sorusuna da model degil,
DOGRULAYICININ ciktisi cevap verir. Burasi o ciktiyi okuyan deterministik bir kural
katmanidir - regex bile degil, alan karsilastirmasi.

VARSAYILAN MUHAFAZAKAR: `otomatik_kabul` KAPALI. Otomatik kabul, denetciyi devreden
cikarmak demektir; bu projenin butun mimarisi "usta KOSARAK dogrular" uzerine kurulu.
Acmak isteyen acar, ama varsayilan olarak KABUL kararini insan verir.

UC SINYAL, UCU DE DOGRULAYICIDAN (modelin beyanindan DEGIL):
  1. dogrulama satirlarinda "kaldi" var mi (derleme/test/kabul/yazma kapsami)
  2. yazma kapsami disina dosya yazilmis mi (disiplin ihlali - olculdu: dama gorevinde
     11 dosya yazildi, 10'u istenmemisti)
  3. DURAGANLIK: ayni imza denemeler arasi tekrarliyor mu (olculdu: 2600 -> 6050 token
     yandi, sonuc AYNI). Duraganlik varsa devam etmek para yakmaktir.
"""
from __future__ import annotations

SEMA = 1

VARSAYILAN = {
    "hata_olunca": "dur",          # dur | devam
    "duraganlikta": "dur",         # dur | devam
    "kapsam_disinda": "dur",       # dur | devam
    "ust_uste_hata_siniri": 2,     # bu kadar is UST USTE kalirsa dur (0 = kapali)
    "otomatik_kabul": False,       # hepsi gectiyse KABUL isaretle (varsayilan KAPALI)
    "otomatik_reddet": False,      # kalirsa REDDET isaretle (varsayilan KAPALI)
    # KANIT YOKSA DURURUZ (denetim bulgusu 3). "Basarisiz degil" ile "basarili" AYNI SEY
    # DEGILDIR; denetlenmemis bir isin ustune yeni is yigmak, gozetimsiz kosuda bozuk
    # temel uzerine insa etmektir.
    "dogrulanmayinca": "dur",      # dur | devam  (kabul kriteri denetlenmemis vb.)
    "bilinmeyince": "dur",         # dur | devam  (is kaydi eksik/bozuk)
}


def ayar_yukle(config=None) -> dict:
    """apprentice.config.json -> 'politika' bolumu; eksik anahtarlar varsayilandan gelir."""
    a = dict(VARSAYILAN)
    try:
        if config is None:
            from core import config as config_mod
            config = config_mod
        d = config.get("politika") or {}
        if isinstance(d, dict):
            for k, v in d.items():
                if k in a and not str(k).startswith("_"):
                    a[k] = v
    except Exception:      # noqa: BLE001 - ayar okunamazsa varsayilan gecerli
        pass
    a["ust_uste_hata_siniri"] = max(0, int(a.get("ust_uste_hata_siniri") or 0))
    return a


def degerlendir(ozet: dict) -> dict:
    """ReviewSummary'yi oku, SAF karar ver. Doner: {sonuc, sebepler, kalan_kontroller}.

    sonuc DORT DEGERLI:
      "temiz"        - POZITIF kanit var: en az bir dogrulama GECTI, hicbiri kalmadi.
      "kaldi"        - acik basarisizlik (dogrulama kaldi / kapsam ihlali / duraganlik).
      "dogrulanmadi" - ne gecti ne kaldi: OLCULMEDI. Kabul kriteri verilip denetlenmemis
                       olabilir ya da hic dogrulama kaydi yoktur. BASARI DEGILDIR.
      "bilinmiyor"   - is hala kosuyor ya da ozet hic uretilemedi (kayit eksik/bozuk).
    "dogrulanmadi" ile "temiz" arasindaki fark bu maddenin CEKIRDEGI: "basarisiz degil"
    ile "basarili" ayni sey DEGILDIR.
    """
    if not isinstance(ozet, dict) or not ozet.get("is_id"):
        return {"sonuc": "bilinmiyor", "sebepler": ["inceleme ozeti yok"],
                "kalan_kontroller": []}
    if str(ozet.get("durum") or "").lower() in ("kosuyor", "calisiyor", "basladi"):
        return {"sonuc": "bilinmiyor", "sebepler": ["is hala kosuyor"],
                "kalan_kontroller": []}

    sebepler, kalanlar, denetlenmeyen, gecenler = [], [], [], []
    for d in ozet.get("dogrulama") or []:
        if not isinstance(d, dict):
            continue
        durum, ad = str(d.get("durum")), str(d.get("ad") or "?")
        if durum == "kaldi":
            kalanlar.append(ad)
            sebepler.append("%s: %s" % (ad, str(d.get("kanit") or "")[:120]))
        elif durum == "gecti":
            gecenler.append(ad)
        else:
            # "yok" = OLCULMEDI. Bu bir BASARI DEGILDIR (denetim bulgusu 3): kabul
            # kriterleri verilip hic denetlenmediyse `_kabul_satiri` "yok" yazar ve eski
            # politika yalnizca "kaldi"ya baktigi icin isi TEMIZ sayiyordu. Telemetride
            # duzelttigimiz "%100 dogrulayici / gercek %81,6" yalani politika kapisindan
            # geri giriyordu.
            denetlenmeyen.append("%s (%s)" % (ad, str(d.get("kanit") or "olculmedi")[:80]))

    disi = [d.get("yol") for d in (ozet.get("degisen_dosyalar") or [])
            if isinstance(d, dict) and d.get("kapsam_disi")]
    if disi:
        sebepler.append("yazma kapsami disina %d dosya: %s"
                        % (len(disi), ", ".join(str(x) for x in disi[:4])))

    dur = ozet.get("duraganlik") or {}
    duragan = bool(isinstance(dur, dict) and dur.get("var"))
    if duragan:
        sebepler.append("duraganlik: ayni imza denemeler arasi tekrarliyor (%s)"
                        % str(dur.get("imza") or dur.get("sebep") or "")[:120])

    # SIRA ONEMLI: once acik BASARISIZLIK, sonra EKSIK KANIT, en son temiz.
    # "temiz" POZITIF KANIT ISTER: en az bir dogrulama GECMIS olmali. Kanit yoksa
    # "dogrulanmadi" deriz - "kaldi" degildir ama BASARI da degildir.
    if kalanlar or disi or duragan:
        sonuc = "kaldi"
    elif denetlenmeyen:
        sonuc = "dogrulanmadi"
        sebepler.append("denetlenmemis kontrol: " + "; ".join(denetlenmeyen[:3]))
    elif not gecenler:
        sonuc = "dogrulanmadi"
        sebepler.append("hicbir dogrulama kaydi yok - basari iddia edilemez")
    else:
        sonuc = "temiz"
    return {"sonuc": sonuc, "sebepler": sebepler, "kalan_kontroller": kalanlar,
            "denetlenmeyen": denetlenmeyen, "gecen_kontroller": gecenler,
            "kapsam_disi": [str(x) for x in disi], "duraganlik": duragan}


def karar(degerlendirme: dict, ayar: dict, ust_uste: int = 0) -> dict:
    """Degerlendirmeden EYLEM uret. Doner: {eylem, isaret, sebep}.

    eylem: "devam" | "dur"      (kuyruga verilir)
    isaret: "" | "kabul" | "red"      (inceleme.json'a yazilacak karar; "" = insana birak)
    """
    a = dict(VARSAYILAN); a.update(ayar or {})
    d = degerlendirme or {}
    sonuc = d.get("sonuc")

    if sonuc == "bilinmiyor":
        # UYDURMA YOK - ve DEVAM DA YOK. Ozet cikmadiysa (kayit eksik/bozuk, is hala
        # kosuyor gorunuyor) is TAMAMLANMIS SAYILMAZ. Eski surum burada "devam" diyordu:
        # bozuk bir is kaydi kuyrugun sonraki isi baslatmasina sessizce izin veriyordu.
        return {"eylem": "dur" if a.get("bilinmeyince") == "dur" else "devam",
                "isaret": "",
                "sebep": "durum BILINMIYOR (is kaydi eksik/bozuk olabilir): "
                         + "; ".join(d.get("sebepler") or ["-"])[:160]}

    if sonuc == "dogrulanmadi":
        # KANIT YOK. Ne "kaldi" diyebiliriz ne "gecti". Otomatik kabul ASLA olmaz -
        # dogrulanmamis isi basari saymak, bu projenin butun olcum durustlugunu bozar.
        return {"eylem": "dur" if a.get("dogrulanmayinca") == "dur" else "devam",
                "isaret": "",
                "sebep": "DOGRULANMADI: " + "; ".join(d.get("sebepler") or ["-"])[:180]}

    if sonuc == "temiz":
        # POZITIF KANIT var (en az bir "gecti", hic "kaldi"/"yok" yok).
        return {"eylem": "devam",
                "isaret": "kabul" if a.get("otomatik_kabul") else "",
                "sebep": "butun dogrulamalar gecti (%d kontrol)"
                         % len(d.get("gecen_kontroller") or [])}

    # --- kaldi ---
    eylem = "devam"
    if d.get("duraganlik") and a.get("duraganlikta") == "dur":
        eylem = "dur"
    elif d.get("kapsam_disi") and a.get("kapsam_disinda") == "dur":
        eylem = "dur"
    elif a.get("hata_olunca") == "dur":
        eylem = "dur"
    sinir = a.get("ust_uste_hata_siniri") or 0
    if sinir and ust_uste >= sinir:
        eylem = "dur"
    return {"eylem": eylem,
            "isaret": "red" if a.get("otomatik_reddet") else "",
            "sebep": "; ".join(d.get("sebepler") or ["dogrulama kaldi"])[:200]}


class Politika:
    """Kuyruga takilan sarmalayici: ozet okur, karar verir, gerekiyorsa KARARI YAZAR.

    Kuyruk bunu `politika(oge, kuyruk) -> "devam"|"dur"` olarak cagirir. Yazma isi burada
    yapilir cunku kuyruk kararlardan haberdar olmamali - tek sorumluluk."""

    def __init__(self, jobs_dir: str, ayar: dict | None = None, ozet_al=None, karar_yaz=None):
        self.jobs_dir = jobs_dir
        self.ayar = dict(VARSAYILAN)
        self.ayar.update(ayar or {})
        self.ust_uste = 0
        self.gecmis: list = []
        # SON KARARIN SEBEBI: kuyruk bunu okuyup kullanicinin gorecegi yere yazar.
        # Olmadan panelde yalnizca "politika kuyrugu durdurdu" gorunuyordu - kullanici
        # NEDEN durdugunu bilemiyordu (denetim bulgusu 3).
        self.son_sebep = ""
        self._ozet_al = ozet_al
        self._karar_yaz = karar_yaz

    def _ozet(self, jid: str) -> dict:
        if self._ozet_al:
            return self._ozet_al(jid) or {}
        from core.inceleme import inceleme
        return inceleme(self.jobs_dir, jid) or {}

    def _yaz(self, jid: str, isaret: str, sebep: str) -> None:
        try:
            if self._karar_yaz:
                self._karar_yaz(jid, isaret, sebep)
            else:
                from core.inceleme import karar_yaz
                karar_yaz(self.jobs_dir, jid, isaret,
                          {"kim": "politika", "not": sebep[:300], "otomatik": True})
        except Exception:      # noqa: BLE001 - karar yazilamazsa kuyruk yine de dogru davransin
            pass

    def __call__(self, oge: dict, kuyruk=None) -> str:
        jid = str((oge or {}).get("is_id") or "")
        if not jid:
            # is HIC baslamadiysa (kuyruk 'hata' isaretledi) bu da ust uste hata sayilir
            self.ust_uste += 1
            k = ("dur" if (self.ayar.get("hata_olunca") == "dur"
                           or (self.ayar.get("ust_uste_hata_siniri") or 0)
                           and self.ust_uste >= self.ayar["ust_uste_hata_siniri"]) else "devam")
            self.son_sebep = "is HIC baslatilamadi: %s" % (oge or {}).get("sebep", "-")
            self.gecmis.append({"is_id": "", "sonuc": "baslatilamadi", "eylem": k,
                                "sebep": self.son_sebep})
            return k
        d = degerlendir(self._ozet(jid))
        k = karar(d, self.ayar,
                  self.ust_uste + (0 if d.get("sonuc") == "temiz" else 1))
        if d.get("sonuc") in ("kaldi", "dogrulanmadi", "bilinmiyor"):
            self.ust_uste += 1          # "temiz olmayan" her sonuc ust uste sayilir
        elif d.get("sonuc") == "temiz":
            self.ust_uste = 0
        self.son_sebep = k.get("sebep") or ""
        if k.get("isaret"):
            self._yaz(jid, k["isaret"], k.get("sebep") or "")
        self.gecmis.append({"is_id": jid, "sonuc": d.get("sonuc"), "eylem": k["eylem"],
                            "sebep": k.get("sebep", ""), "isaret": k.get("isaret", "")})
        return k["eylem"]

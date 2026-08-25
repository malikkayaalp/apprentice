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

    sonuc: "temiz" | "kaldi" | "bilinmiyor"
    "bilinmiyor" MESRU bir sonuctur: is hala kosuyorsa ya da ozet uretilemediyse uydurmayiz.
    """
    if not isinstance(ozet, dict) or not ozet.get("is_id"):
        return {"sonuc": "bilinmiyor", "sebepler": ["inceleme ozeti yok"],
                "kalan_kontroller": []}
    if str(ozet.get("durum") or "").lower() in ("kosuyor", "calisiyor", "basladi"):
        return {"sonuc": "bilinmiyor", "sebepler": ["is hala kosuyor"],
                "kalan_kontroller": []}

    sebepler, kalanlar = [], []
    for d in ozet.get("dogrulama") or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("durum")) == "kaldi":
            kalanlar.append(str(d.get("ad") or "?"))
            sebepler.append("%s: %s" % (d.get("ad") or "?", str(d.get("kanit") or "")[:120]))

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

    return {"sonuc": "kaldi" if (kalanlar or disi or duragan) else "temiz",
            "sebepler": sebepler, "kalan_kontroller": kalanlar,
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
        # UYDURMA YOK: ozet cikmadiysa ne kabul ederiz ne reddederiz, kuyrugu da durdurmayiz.
        return {"eylem": "devam", "isaret": "",
                "sebep": "; ".join(d.get("sebepler") or ["durum bilinmiyor"])[:200]}

    if sonuc == "temiz":
        return {"eylem": "devam",
                "isaret": "kabul" if a.get("otomatik_kabul") else "",
                "sebep": "butun dogrulamalar gecti"}

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
            self.gecmis.append({"is_id": "", "sonuc": "baslatilamadi", "eylem": k})
            return k
        d = degerlendir(self._ozet(jid))
        k = karar(d, self.ayar, self.ust_uste + (1 if d.get("sonuc") == "kaldi" else 0))
        if d.get("sonuc") == "kaldi":
            self.ust_uste += 1
        elif d.get("sonuc") == "temiz":
            self.ust_uste = 0
        if k.get("isaret"):
            self._yaz(jid, k["isaret"], k.get("sebep") or "")
        self.gecmis.append({"is_id": jid, "sonuc": d.get("sonuc"), "eylem": k["eylem"],
                            "sebep": k.get("sebep", ""), "isaret": k.get("isaret", "")})
        return k["eylem"]

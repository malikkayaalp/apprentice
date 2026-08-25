"""GIZLILIK: uzak ustaya NE gidiyor - tek karar yeri.

NEDEN VAR: rapor, cirak'in yazdigi her dosyanin TAM ICERIGINI tasiyordu ve bu rapor
`worker_run`/`worker_status` ile IDE'deki uzak modele gidiyordu. Belgeler ise "kod
makineden cikmaz, denetciye yalnizca ozetler ve olcumler gider" diyordu. Iddia YANLISTI.

KABUL EDILEN GERCEK: fark (diff) da KAYNAK KODDUR. Tam dosya yerine fark gondermek
"kod disari cikmiyor" iddiasini DOGRU YAPMAZ - yalnizca cikan miktari kucultur. Bu yuzden
burada iki sey birden yapilir:
  1. Gonderilen miktar sinirlanir (varsayilan: yalnizca FARK, tam icerik KAPALI)
  2. Ne gonderildigi RAPORDA yazar (`gizlilik` alani) - kullanici tahmin etmesin

Belge tarafi ayri is degil, AYNI isin parcasi: davranisi degistirip belgeyi eski birakmak
ya da belgeyi duzeltip davranisi birakmak, ikisi de yarim cozumdur.

TAM ICERIK: varsayilan KAPALI. Acmak icin apprentice.config.json:
    "gizlilik": {"tam_icerik": true}
Acikca acilir, sessizce acilmaz.

MASKELEME BIR GARANTI DEGIL: desen tabanlidir; bilinen anahtar bicimlerini yakalar,
"her sirri bulur" demez. Sirri olan dosyayi hic gondermemek her zaman daha guvenlidir.
Yakalanan her sey RAPORDA sayilir - sessiz maskeleme, sessiz sizintidan yalnizca bir adim
iyidir; kullanici kac sey maskelendigini gormeli.
"""
from __future__ import annotations
import difflib, re

SEMA = 1

VARSAYILAN = {
    "tam_icerik": False,     # dosyanin TAM son icerigi ustaya gitsin mi (varsayilan HAYIR)
    "fark_siniri": 4000,     # dosya basina gonderilecek fark, karakter
    "gizli_maskele": True,   # bilinen anahtar bicimlerini maskele
}

# Bilinen sir bicimleri. DAR TUTULDU: genis desen (ornegin "her 32+ karakterlik dize")
# normal kodu maskeleyip denetimi korlestirir - maskeleme denetciyi kor etmemeli.
_DESENLER = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.S), "ozel anahtar"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "api anahtari"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "github jetonu"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github jetonu"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "slack jetonu"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws anahtari"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "google anahtari"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "jwt"),
    # atama bicimi: api_key = "..."  /  PASSWORD: '...'  (degeri maskele, ADI birak ki
    # denetci "burada bir sir var" diyebilsin)
    (re.compile(r"""((?:api[_-]?key|apikey|secret|token|passwd|password|pwd|private[_-]?key)"""
                r"""\s*[:=]\s*)(['"])([^'"\n]{6,})(\2)""", re.I), "gizli atama"),
    # baglanti dizesi: scheme://kullanici:PAROLA@host
    (re.compile(r"(://[^\s:/@]+:)([^\s@/]{3,})(@)"), "baglanti parolasi"),
)

MASKE = "[GIZLENDI]"


def maskele(metin: str) -> tuple[str, list]:
    """Bilinen sir bicimlerini maskele. Doner: (metin, [bulunan tur adlari]).

    Sayim RAPORA gider: kullanici kac sey maskelendigini gormeli. Sessiz maskeleme,
    "hicbir sey yoktu" ile "on tane vardi" arasindaki farki gizler."""
    if not metin:
        return metin, []
    bulunan = []
    for desen, ad in _DESENLER:
        if desen.groups >= 3:                    # atama/baglanti: yalnizca DEGERI maskele
            def _degistir(m, _ad=ad):
                bulunan.append(_ad)
                return m.group(1) + m.group(2) + MASKE + m.group(4) if m.lastindex >= 4 \
                    else m.group(1) + MASKE + m.group(3)
            metin = desen.sub(_degistir, metin)
        else:
            def _tam(m, _ad=ad):
                bulunan.append(_ad)
                return MASKE
            metin = desen.sub(_tam, metin)
    return metin, bulunan


def fark_uret(once: str | None, sonra: str, yol: str = "", sinir: int = 4000) -> tuple[str, bool]:
    """Sinirlandirilmis birlesik fark (unified diff). Doner: (fark, kirpildi_mi).

    NEDEN FARK: denetcinin isi "ne yazildi" degil "NE DEGISTI" - farkin denetim degeri
    tam icerikten YUKSEK, disari cikan miktar DUSUKtur. Ama fark da kaynak koddur;
    bu yuzden sinirlidir ve belgede acikca soylenir."""
    o = (once or "").splitlines()
    s = (sonra or "").splitlines()
    satirlar = list(difflib.unified_diff(o, s, fromfile=(yol or "dosya") + " (once)",
                                         tofile=(yol or "dosya") + " (sonra)", lineterm="", n=3))
    if not satirlar:
        return "", False
    metin = "\n".join(satirlar)
    if len(metin) <= sinir:
        return metin, False
    return metin[:sinir] + "\n… [fark kirpildi: %d karakterin ilk %d'i]" % (len(metin), sinir), True


def ayar(config=None) -> dict:
    """apprentice.config.json -> 'gizlilik'. Eksik anahtar varsayilandan gelir."""
    a = dict(VARSAYILAN)
    try:
        if config is None:
            from core import config as config_mod
            config = config_mod
        d = config.get("gizlilik") or {}
        if isinstance(d, dict):
            for k, v in d.items():
                if k in a and not str(k).startswith("_"):
                    a[k] = v
    except Exception:      # noqa: BLE001 - ayar okunamazsa GUVENLI varsayilan gecerli
        pass
    a["tam_icerik"] = bool(a.get("tam_icerik"))
    a["gizli_maskele"] = bool(a.get("gizli_maskele", True))
    try:
        a["fark_siniri"] = max(200, int(a.get("fark_siniri") or 4000))
    except (TypeError, ValueError):
        a["fark_siniri"] = 4000
    return a


def dosya_ozeti(yol: str, once: str | None, sonra: str, a: dict,
                icerik_siniri: int = 12000) -> dict:
    """Rapora girecek dosya kaydi. Ustaya NE gidecegine tek karar veren yer.

    Her zaman: yol, yeni, eklendi/silindi (sayim), satir
    Varsayilan  : fark (sinirli, maskeli)
    Yalnizca acikca acilirsa: icerik (tam, maskeli)"""
    o = once or ""
    ek = sil = 0
    for satir in difflib.unified_diff(o.splitlines(), (sonra or "").splitlines(),
                                      lineterm="", n=0):
        if satir.startswith("+") and not satir.startswith("+++"):
            ek += 1
        elif satir.startswith("-") and not satir.startswith("---"):
            sil += 1

    kayit = {"yol": yol, "yeni": once is None, "eklendi": ek, "silindi": sil,
             "satir": len((sonra or "").splitlines())}
    maskeli = []
    fark, kirpik = fark_uret(o, sonra or "", yol, a.get("fark_siniri", 4000))
    if a.get("gizli_maskele", True):
        fark, b = maskele(fark)
        maskeli += b
    kayit["fark"] = fark
    kayit["fark_kirpildi"] = kirpik
    if a.get("tam_icerik"):
        ic = sonra or ""
        if a.get("gizli_maskele", True):
            ic, b = maskele(ic)
            maskeli += b
        kayit["icerik"] = ic if len(ic) <= icerik_siniri else ic[:icerik_siniri] + "\n… [kirpildi]"
    if maskeli:
        kayit["maskelenen"] = sorted(set(maskeli))
    return kayit


def rapor_notu(a: dict) -> dict:
    """Rapora eklenen `gizlilik` alani: ustaya NE gonderildigini RAPORUN KENDISI soyler.

    Kullanici (ve denetci model) tahmin etmek zorunda kalmamali; ayrica bu alan, ileride
    varsayilan degisirse eski raporlarin hangi kurala gore uretildigini de belgeler."""
    return {"sema": SEMA,
            "gonderilen": "tam_icerik+fark" if a.get("tam_icerik") else "yalniz_fark",
            "fark_siniri": a.get("fark_siniri"),
            "maskeleme": bool(a.get("gizli_maskele", True)),
            "not": ("Fark da KAYNAK KODDUR. Uzak bir usta modeli kullaniliyorsa degisen kod "
                    "o modele gonderilir. Yerel usta kullaniliyorsa veri makineden cikmaz.")}

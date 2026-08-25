"""ORNEKLEME AYARLARI: yapilandirmadan GERCEK model istegine giden tek yol.

YASANDI (denetim bulgusu 4): `apprentice.config.template.json` bir `sampling` bolumu
reklam ediyordu - temperature, think, num_predict, max_steps, retries - ama bu alanlarin
HICBIRI hicbir yerde OKUNMUYORDU. `envs/code/code_runner.py` degerleri kodun icine gomulu
tutuyordu (`temperature=0.0, think=False, num_predict=6000, max_steps=12, retries=2`).
`prompt.ek_talimat` da ayni durumdaydi. Yani kullanici ayari degistiriyor, hicbir sey
olmuyordu - sessizce yok sayilan bir ayar, olmayan bir ayardan KOTUDUR: kullanici
degistirdigini saniyor.

GUVENLI VARSAYILANLAR KORUNDU (kullanici karari): temperature=0.0 ve think=false. Bunlar
olculmus kararlardir:
  - think acilinca gorev basina ~3900 dusunme tokeni yandi ve kalite artmadi.
  - temperature>0 tekrarlanabilirligi bozar; bu proje olcum iddiasinda.
Degistirilebilirler AMA riskli degerler UYARI uretir ve uyari panelde gorunur.

OLCUM PROFILI: `APPRENTICE_OLCUM_PROFILI=1` verilirse yapilandirma YOK SAYILIR ve kilitli
varsayilanlar kullanilir. Kampanyalar bunu kullanir - kiyas tek degiskenli kalsin diye
kullanicinin ayari olcumu kaydirmamalidir.

ETKIN DEGER RAPORLANIR: `etkin()` neyin gercekten uygulandigini ve kaynagini doner
(varsayilan / yapilandirma / ortam / olcum-profili). Panel ve rapor bunu gosterir -
"ayari degistirdim ama uygulandi mi" sorusu tahminle cevaplanmasin.
"""
from __future__ import annotations
import os

SEMA = 1

VARSAYILAN = {
    "temperature": 0.0,      # OLCULDU: tekrarlanabilirlik icin 0. Yukseltmek olcumu bozar.
    "think": False,          # OLCULDU: acikken ~3900 tok/gorev yandi, kalite artmadi.
    "num_predict": 6000,     # tur basina uretim ust siniri
    "max_steps": 12,         # bir turda en fazla kac arac dongusu
    "retries": 2,            # ayristirma/aktarim hatasinda yeniden deneme
}

# Riskli degerler: engellenmez, UYARILIR. Kullanicinin makinesi, kullanicinin karari -
# ama sonucun neden degistigini bilmeli.
_RISK = {
    "temperature": (lambda v: v > 0.0,
                    "temperature > 0: ayni gorev ayni sonucu vermeyebilir; olcum ve "
                    "kiyaslar guvenilmez hale gelir."),
    "think": (lambda v: bool(v),
              "think acik: olculdu - gorev basina ~3900 dusunme tokeni yandi ve kalite "
              "artmadi. Yavaslar ve pahalilasir."),
    "num_predict": (lambda v: v > 16000,
                    "num_predict cok yuksek: tek tur cok uzun surebilir ve baglami sisirir."),
    "max_steps": (lambda v: v > 40,
                  "max_steps cok yuksek: dongude kalan bir is uzun sure kendini tekrar eder."),
    "retries": (lambda v: v > 5,
                "retries cok yuksek: kalici bir hata cok kez yeniden denenir."),
}

_TIPLER = {"temperature": float, "think": bool, "num_predict": int,
           "max_steps": int, "retries": int}
_SINIR = {"temperature": (0.0, 2.0), "num_predict": (16, 200000),
          "max_steps": (1, 200), "retries": (0, 20)}


def olcum_profili() -> bool:
    return os.environ.get("APPRENTICE_OLCUM_PROFILI") == "1"


def _cevir(ad: str, ham):
    """Degeri BEKLENEN tipe cevir ve sinira sikistir. Doner: (deger, hata_metni)."""
    tip = _TIPLER[ad]
    try:
        if tip is bool:
            if isinstance(ham, str):
                d = ham.strip().lower() in ("1", "true", "evet", "yes", "on")
            else:
                d = bool(ham)
        else:
            d = tip(ham)
    except (TypeError, ValueError):
        return VARSAYILAN[ad], "%s gecersiz (%r) - varsayilan kullanildi" % (ad, ham)
    if ad in _SINIR:
        alt, ust = _SINIR[ad]
        if d < alt or d > ust:
            kirpik = min(max(d, alt), ust)
            return kirpik, "%s sinir disi (%r) - %r'e kirpildi" % (ad, d, kirpik)
    return d, ""


def etkin(config=None) -> dict:
    """GERCEKTEN uygulanacak ornekleme ayarlari + nereden geldikleri + uyarilar.

    Doner: {"deger": {...}, "kaynak": {ad: "varsayilan|yapilandirma|olcum-profili"},
            "uyarilar": [...], "hatalar": [...], "olcum_profili": bool}"""
    deger = dict(VARSAYILAN)
    kaynak = {k: "varsayilan" for k in VARSAYILAN}
    uyarilar: list = []
    hatalar: list = []

    if olcum_profili():
        return {"deger": deger, "kaynak": {k: "olcum-profili" for k in deger},
                "uyarilar": [], "hatalar": [], "olcum_profili": True}

    ham: dict = {}
    try:
        if config is None:
            from core import config as config_mod
            config = config_mod
        d = config.get("sampling") or {}
        if isinstance(d, dict):
            ham = {k: v for k, v in d.items() if k in VARSAYILAN and not str(k).startswith("_")}
    except Exception as e:  # noqa: BLE001 - ayar okunamazsa varsayilan gecerli
        hatalar.append("ayar okunamadi: %s" % str(e)[:120])

    for ad, v in ham.items():
        yeni, hata = _cevir(ad, v)
        deger[ad] = yeni
        kaynak[ad] = "yapilandirma"
        if hata:
            hatalar.append(hata)

    for ad, (riskli_mi, mesaj) in _RISK.items():
        try:
            if kaynak[ad] == "yapilandirma" and riskli_mi(deger[ad]):
                uyarilar.append({"ayar": ad, "deger": deger[ad], "mesaj": mesaj})
        except Exception:  # noqa: BLE001
            pass
    return {"deger": deger, "kaynak": kaynak, "uyarilar": uyarilar,
            "hatalar": hatalar, "olcum_profili": False}


def ek_talimat(config=None) -> str:
    """`prompt.ek_talimat`: kullanicinin sistem istemine ekledigi genel talimat.

    Sablonda vardi ama HIC OKUNMUYORDU. Sinirlidir: sistem istemi buyudukce her tur
    yeniden odenen bir vergiye doner."""
    try:
        if config is None:
            from core import config as config_mod
            config = config_mod
        return str(config.get("prompt.ek_talimat") or "").strip()[:2000]
    except Exception:  # noqa: BLE001
        return ""

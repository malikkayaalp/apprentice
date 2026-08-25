"""EKLER: panelden yuklenen dosyalar - PROJEYE DEGIL, ise ozel alana.

YASANDI (denetim bulgusu 1): panelden yuklenen dosya, adiyla DOGRUDAN proje klasorune
yaziliyordu. Projede ayni adli dosya varsa SESSIZCE eziliyordu. Uc kat zarar:
  1. Kullanicinin dosyasi uyarisiz gitti.
  2. Yazim, isin ANLIK GORUNTUSUNDEN once oluyordu - anlik goruntu o dosyayi "baslarken
     zaten kirli" goruyordu.
  3. Bu yuzden geri alma onu "kullanicinin kendi degisikligi" sayip ATLIYORDU. Yani
     Apprentice ustune yaziyor, sonra geri getirmeyi de reddediyordu.

COZUM: ek dosyalari isin KENDI klasorune (<HOME>/jobs/<is_id>/ekler/) yazilir. Orasi
calisma agacinin DISIDIR: proje kirlenmez, anlik goruntu bozulmaz, geri alma yaniltilmaz
ve is kaydi silinince ekler de gider.

YENIDEN ADLANDIRMA YOK: "dosya (1).py" gibi bir cozum projede kalici kirlilik birakir ve
kullanici hangi dosyanin hangisi oldugunu bilemez. Ek zaten projede DEGIL - cakisma
kavrami ortadan kalkar.

MODEL EKI NASIL OKUR: ise ait ek klasoru cirak'a YALNIZCA OKUMA icin acilir (bkz.
code_runner.Jail.oku_yolu). Yazma hapsi DEGISMEZ - cirak oraya yazamaz, silemez.
Kullanici eki gercekten projeye kopyalamak isterse bunu cirak normal bir write_file ile
yapar; o zaman olay gunlugune girer, geri alinabilir ve gorunur olur.
"""
from __future__ import annotations
import base64, os, re

SEMA = 1
MAX_EK = 6
MAX_BAYT = 8_000_000
MAX_AD = 80
# Cirak yalnizca METIN alir (resim/ikili dosya modele gonderilmez). Tek kaynak burasi.
METIN_UZANTILAR = (".py", ".md", ".txt", ".json", ".csv", ".html", ".js", ".ts", ".cs",
                   ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sql", ".sh", ".bat",
                   ".xml", ".log", ".c", ".h", ".cpp", ".java", ".go", ".rs")

# Ad temizligi: yol ayraci, surucu harfi, denetim karakteri ve Windows'ta yasak olanlar.
# NEDEN AGRESIF: ek adi kullanicidan (ve dolayli olarak dis kaynaktan) gelir; "..\\..\\x"
# ya da "C:evil" gibi bir ad, hedef klasorun disina yazmaya calisir.
_YASAK = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_AYRILMIS = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
                 "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
                 "LPT6", "LPT7", "LPT8", "LPT9"}


def ad_temizle(ad: str) -> str:
    """Kullanicidan gelen dosya adini GUVENLI bir ada cevir (uzantisi korunur)."""
    ad = os.path.basename(str(ad or "").replace("\\", "/").rstrip("/"))
    ad = _YASAK.sub("_", ad).strip().strip(".")
    if not ad:
        return "ek"
    kok, uzanti = os.path.splitext(ad)
    if kok.upper() in _WIN_AYRILMIS:          # Windows'ta CON.txt dosya OLUSTURULAMAZ
        kok = "_" + kok
    if len(kok) > MAX_AD:
        kok = kok[:MAX_AD]
    return (kok or "ek") + uzanti[:16]


def kaydet(ekler: list, hedef_dir: str, uzantilar: tuple | None = None) -> tuple:
    """Ekleri hedef_dir altina GUVENLI yaz. Doner: (yollar, reddedilenler).

    hedef_dir ISE OZEL ve calisma agacinin DISINDA olmali - cagiran taraf bunu saglar.
    Ayni ad iki kez gelirse ikincisi sayiyla ayrilir; PROJEDEKI bir dosyayla cakisma
    kavrami yoktur cunku burasi proje degildir."""
    os.makedirs(hedef_dir, exist_ok=True)
    yollar, red = [], []
    kullanilan: set = set()
    for e in (ekler or [])[:MAX_EK]:
        ham = str((e or {}).get("ad") or "ek")
        ad = ad_temizle(ham)
        if uzantilar and not ad.lower().endswith(uzantilar):
            red.append(ham + " (cirak yalniz metin alir)")
            continue
        kok, uzanti = os.path.splitext(ad)
        n = 1
        while ad.lower() in kullanilan or os.path.exists(os.path.join(hedef_dir, ad)):
            ad = "%s-%d%s" % (kok, n, uzanti)
            n += 1
        kullanilan.add(ad.lower())
        yol = os.path.join(hedef_dir, ad)
        try:
            if e.get("b64") is not None:
                veri = base64.b64decode(str(e["b64"]).split(",")[-1])
                if len(veri) > MAX_BAYT:
                    red.append(ham + " (8 MB siniri)")
                    continue
                with open(yol, "wb") as f:
                    f.write(veri)
            else:
                with open(yol, "w", encoding="utf-8", newline="\n") as f:
                    f.write(str(e.get("icerik") or "")[:2_000_000])
            yollar.append(yol)
        except (OSError, ValueError) as hata:
            red.append("%s (%s)" % (ham, str(hata)[:60]))
    return yollar, red


def gorev_notu(yollar: list) -> str:
    """Goreve eklenecek not: ekler NEREDE ve nasil okunur.

    MUTLAK YOL verilir - ek calisma dizininde DEGILDIR, goreli yol onu bulmaz."""
    if not yollar:
        return ""
    satirlar = "\n".join("  " + os.path.normpath(y) for y in yollar)
    return ("\n\nEKLI DOSYALAR (kullanici panelden ekledi). Bunlar calisma dizininin DISINDA,\n"
            "salt okunur bir klasorde durur; read_file ile AŞAĞIDAKI TAM YOLLA oku:\n"
            + satirlar +
            "\nGerekiyorsa iceriklerini calisma dizinindeki bir dosyaya sen yazarsin; "
            "ek klasorune yazamazsin.")

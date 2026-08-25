"""OLCUM ARSIVI: kampanya sonuclari ustune YAZILMAZ, birikir.

    python -m core.olcum                 # arsivdeki butun kosulari listele
    python -m core.olcum code_kampanya   # tek kampanyanin kosulari, yan yana

YASANDI: kampanyalar sonucu `tests/<ad>.son.json`'a yaziyordu ve her kosu oncekini
EZIYORDU. 2026-08-23'teki temel cizgi (6 gorev, 8 tur, 2416 sn) 2026-08-25 kosusuyla
(883 sn) degistirildi; aradaki 2.7 katlik farkin sebebi artik olculemiyordu - kiyas noktasi
silinmisti. Olcum iddiasindaki bir projede kabul edilemez.

Artik iki yere yazilir:
    tests/<ad>.son.json                  SON kosu (kolay erisim, eskisi gibi)
    reports/olcum/<ad>-<zaman>.json      ARSIV (asla silinmez, asla ezilmez)

Arsiv dosya adindaki zaman damgasi kosunun BASLANGICINDAN gelir; ayni saniyede iki kosu
olursa sonuna sayac eklenir - sessizce ezme YOK.
"""
from __future__ import annotations
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARSIV = os.path.join(ROOT, "reports", "olcum")


def kaydet(ad: str, veri: dict, zaman: float | None = None) -> dict:
    """Kampanya sonucunu SON + ARSIV olarak yaz. Doner: {"son": yol, "arsiv": yol}."""
    ad = "".join(c for c in str(ad) if c.isalnum() or c in "_-") or "olcum"
    os.makedirs(ARSIV, exist_ok=True)
    damga = time.strftime("%Y%m%d-%H%M%S", time.localtime(zaman or time.time()))
    arsiv = os.path.join(ARSIV, "%s-%s.json" % (ad, damga))
    k = 2
    while os.path.exists(arsiv):        # ayni saniyede iki kosu: EZME, sayac ekle
        arsiv = os.path.join(ARSIV, "%s-%s-%d.json" % (ad, damga, k))
        k += 1
    out = {}
    for yol in (os.path.join(ROOT, "tests", "%s.son.json" % ad), arsiv):
        try:
            with open(yol, "w", encoding="utf-8", newline="\n") as f:
                json.dump(veri, f, ensure_ascii=False, indent=1)
            out["arsiv" if yol == arsiv else "son"] = yol
        except OSError as e:
            out["hata"] = str(e)[:150]
    return out


def _ozet(veri: dict) -> dict:
    """Kampanya ciktisindan kiyaslanabilir sayilar. Sema kampanyadan kampanyaya biraz
    farkli (turlar 'sure' ya da 'sure_s'), ikisi de okunur."""
    g = veri.get("gorevler") or {}
    sureler, turlar, gecen, toplam = [], 0, 0, 0
    for v in g.values():
        for t in (v.get("turlar") or []):
            turlar += 1
            s = t.get("sure", t.get("sure_s"))
            if isinstance(s, (int, float)):
                sureler.append(float(s))
            if isinstance(t.get("gizli_gecen"), int):
                gecen += t["gizli_gecen"]
                toplam += t.get("gizli_toplam") or 0
            elif isinstance(t.get("gizli"), str) and "/" in t["gizli"]:
                a, b = t["gizli"].split("/", 1)
                if a.strip().isdigit() and b.strip().isdigit():
                    gecen += int(a)
                    toplam += int(b)
    return {"baslangic": veri.get("baslangic") or "?", "gorev": len(g), "tur": turlar,
            "toplam_sn": round(sum(sureler)), "tur_basi_sn": round(sum(sureler) / turlar, 1)
            if turlar else 0, "gizli": "%d/%d" % (gecen, toplam) if toplam else "-"}


def kosular(ad: str = "") -> list:
    """Arsivdeki kosular, ESKIDEN YENIYE. ad verilirse yalniz o kampanya."""
    out = []
    try:
        dosyalar = sorted(os.listdir(ARSIV))
    except OSError:
        return out
    for f in dosyalar:
        if not f.endswith(".json") or (ad and not f.startswith(ad + "-")):
            continue
        try:
            with open(os.path.join(ARSIV, f), encoding="utf-8") as fh:
                veri = json.load(fh)
        except Exception:
            continue
        out.append(dict(_ozet(veri), dosya=f))
    return out


def yazdir(ad: str = "") -> None:
    ks = kosular(ad)
    if not ks:
        print("arsivde kosu yok (%s)" % (ARSIV))
        return
    print("%-34s %-17s %5s %4s %8s %9s %8s" %
          ("dosya", "baslangic", "gorev", "tur", "toplam", "tur basi", "gizli"))
    print("-" * 92)
    for k in ks:
        print("%-34s %-17s %5d %4d %7ds %8.1fs %8s" %
              (k["dosya"][:34], str(k["baslangic"])[:17], k["gorev"], k["tur"],
               k["toplam_sn"], k["tur_basi_sn"], k["gizli"]))
    if len(ks) >= 2:
        ilk, son = ks[0], ks[-1]
        if ilk["tur_basi_sn"] and son["tur_basi_sn"]:
            oran = ilk["tur_basi_sn"] / son["tur_basi_sn"]
            print("-" * 92)
            print("ilk -> son: tur basi %.1fs -> %.1fs  (%.2fx %s)"
                  % (ilk["tur_basi_sn"], son["tur_basi_sn"], oran,
                     "hizlandi" if oran > 1 else "yavasladi"))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    yazdir(sys.argv[1] if len(sys.argv) > 1 else "")


# --- KAMPANYA CIKIS KODU SOZLESMESI (denetim bulgusu #3) ---------------------------
# Kampanyalar KOSULSUZ 0 donuyordu: gizli kontroller 11/12 kalsa bile cagiran taraf
# "TAMAM"/"GECTI" yaziyordu. Gozetimsiz gece kosusunda bu, BASARISIZLIGI BASARI gibi
# raporlar - telemetrinin "%100 basari" yanilgisiyla ayni sinif hata.
#
# UC DEGERLI, cunku iki farkli sey ayirt edilmeli:
#   0 - kampanya kostu ve butun gizli kontroller gecti
#   2 - kampanya KOSTU, olcum GECERLI, ama gizli kontroller kaldi (modelin basarisizligi)
#   1 - kampanya KOSAMADI: harness patladi, cokme/zaman asimi - olcum YOK
# 2'yi 1'den ayirmak sart: "model gorevi cozemedi" bir OLCUM SONUCU, "harness patladi"
# ise bir ARIZA. Ikisini ayni koda katlamak, gece kosusunu okunamaz yapar.
CIKIS_TAMAM = 0
CIKIS_EKSIK = 2
CIKIS_HATA = 1


def kampanya_cikis(gecen: int, toplam: int) -> int:
    """Gizli kontrol sayimindan kampanya cikis kodu. toplam=0 ise olculecek sey yoktur -
    bunu BASARI saymayiz, ariza sayariz (kampanya bir sey kosmamis demektir)."""
    if toplam <= 0:
        return CIKIS_HATA
    return CIKIS_TAMAM if gecen >= toplam else CIKIS_EKSIK

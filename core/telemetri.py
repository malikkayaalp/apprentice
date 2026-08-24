"""TELEMETRI + HATA SINIFLANDIRMA: "neyi iyilestirecegiz?" sorusunun olcum tarafi.

Bugun elimizde su yok: cirak hangi hatalarla kac kez karsilasiyor. Onsuz her yol haritasi
fikir tartismasi olur - hangi kucuk modelin, hangi kisitin, hangi orkestrasyonun neye
yarayacagi ancak bu sayilarla gerekcelenir.

TASARIM KURALLARI
  1. DETERMINISTIK. Siniflandirma regex/alt dizge ile yapilir, MODEL KULLANILMAZ. Kesin
     bilgiyi olasilikla degistirmek bu projenin kuralina aykiri.
  2. "bilinmeyen" MESRU bir siniftir. Zorlama siniflandirma yanlis istatistik uretir;
     bilinmeyen ORANI'nin kendisi bir olcumdur (yuksekse taksonomi eksik demektir).
  3. DESENLER HAYALDEN DEGIL, harness'in GERCEKTEN urettigi metinlerden alindi:
       compile_errors : "dosya.py(12): SyntaxError: invalid syntax"
       yazma ani      : "HATA dosya.py satir 12: invalid syntax"
       ruff           : "dosya.py:3:1: F821 Undefined name 'x'"
       test_metni     : "DUSTU test_x - AssertionError: ... [AYNI - onceki duzeltme bunu COZMEDI]"
       duraganlik     : "DURAGANLIK: ayni test hatalari 2 tur ust uste degismedi - ..."
  4. Bu modul TUREITIR, damgalamaz: mevcut kayittan okur, cekirdek davranisini degistirmez.
     Ileride runtime ayni sinifla()'yi cagirip hatayi olay aninda damgalayabilir.
"""
from __future__ import annotations
import json, os, re, sys

# (sinif, desen) - SIRA ONEMLI: ozelden gemele. Ilk eslesen kazanir.
DESENLER = (
    ("duraganlik",        re.compile(r"\bDURAGANLIK\b", re.I)),
    ("zaman_asimi",       re.compile(r"\b(TimeoutExpired|zaman asimi|timed out|timeout)\b", re.I)),
    ("bagimlilik",        re.compile(r"\b(ModuleNotFoundError|ImportError|No module named)\b")),
    # "HATA dosya.py satir 12: ..." = yazma anindaki derleme hatasi; bu bicimde ISTISNA ADI
    # YOK ve yalniz `except SyntaxError` dalinda uretiliyor (code_runner.py:229).
    ("sozdizimi",         re.compile(r"\b(SyntaxError|IndentationError|TabError)\b|:\s*E9\d{2}\b"
                                     r"|^HATA .+ satir \d+:")),
    ("tanimsiz_ad",       re.compile(r"\bNameError\b|\bF821\b|Undefined name")),
    ("olu_kod",           re.compile(r"\bF401\b|\bF811\b|\bF841\b")),
    ("test_beklentisi",   re.compile(r"\bAssertionError\b|\bDUSTU\b|Expected:|assert ")),
    ("tip",               re.compile(r"\b(TypeError|AttributeError)\b")),
    ("calisma_zamani",    re.compile(r"\b(ValueError|KeyError|IndexError|ZeroDivisionError|"
                                     r"FileNotFoundError|PermissionError|RecursionError|"
                                     r"OSError|RuntimeError)\b")),
)


def sinifla(metin: str) -> str:
    """Bir hata metnini SINIFA cevir. Emin degilse 'bilinmeyen' - zorlama yok."""
    m = str(metin or "")
    if not m.strip():
        return "bilinmeyen"
    for ad, desen in DESENLER:
        if desen.search(m):
            return ad
    return "bilinmeyen"


def siniflar(metinler) -> list:
    """Cok satirli hata bloklarini tek tek siniflandir (her satir ayri hata olabilir)."""
    out = []
    for m in metinler or []:
        for satir in str(m).splitlines():
            if satir.strip():
                out.append(sinifla(satir))
    # Blokta siniflanan varsa bilinmeyenleri AT: test_metni'nin "pytest testleri: 14/15"
    # gibi BILGI satirlari istatistigi kirletmesin. Hicbiri siniflanmadiysa bilinmeyen
    # KALIR - orani kendisi bir olcumdur.
    bilinen = [x for x in out if x != "bilinmeyen"]
    if bilinen:
        return bilinen
    return ["bilinmeyen"] if out else []


def _olaylar(jobs_dir: str, jid: str) -> list:
    out = []
    try:
        with open(os.path.join(jobs_dir, jid, "events.jsonl"), encoding="utf-8",
                  errors="replace") as f:
            for satir in f:
                try:
                    out.append(json.loads(satir))
                except Exception:
                    continue
    except OSError:
        pass
    return out


def is_telemetri(jobs_dir: str, jid: str) -> dict:
    """Tek isin olcum kaydi. Is duzeyindeki hukumler INCELEME sozlesmesinden gelir
    (tek dogruluk kaynagi); buraya TUR duzeyindeki hata siniflari eklenir."""
    from core.inceleme import inceleme
    inc = inceleme(jobs_dir, jid)
    if inc.get("hata"):
        return {"is_id": jid, "hata": inc["hata"]}
    olaylar = _olaylar(jobs_dir, jid)
    kayit, sonuc = {}, {}
    turlar = []
    for e in olaylar:
        t = e.get("type")
        if t == "onarim":
            turlar.append({"tur": e.get("tur"), "sinif": sinifla(e.get("mesaj") or ""),
                           "mesaj": str(e.get("mesaj") or "")[:200]})
        elif t == "result":
            sonuc = e
        elif t == "system" and e.get("subtype") == "init":
            kayit = e
    son_siniflar = siniflar(sonuc.get("errors") or [])
    k = inc.get("kullanim") or {}
    onarim = inc.get("onarim_turu") or 0
    return {
        "is_id": jid,
        "kaynak": inc.get("kaynak") or "",
        "model": inc.get("model") or kayit.get("model") or "",
        "ilk_tur_gecti": bool(sonuc) and bool(sonuc.get("ok")) and onarim == 0,
        "gecti": bool(sonuc.get("ok")),
        "onarim_turu": onarim,
        "duragan": bool((inc.get("duraganlik") or {}).get("var")),
        "devir_onerildi": bool((inc.get("devir_onerisi") or {}).get("var")),
        "turlar": turlar,                       # her onarim turunun hata SINIFI
        "son_hata_siniflari": son_siniflar,     # is bitince kalan hatalar
        "dosya_sayisi": len(inc.get("degisen_dosyalar") or []),
        "kapsam_ihlali": sum(1 for d in inc.get("degisen_dosyalar") or [] if d.get("kapsam_disi")),
        "sure": inc.get("sure") or 0,
        "istem_tok": k.get("prompt_tokens") or 0,
        "uretim_tok": k.get("gen_tokens") or 0,
        "ilk_istem_tok": k.get("ilk_prompt_tokens") or 0,
        "model_cagrisi": k.get("model_cagrisi") or 0,
    }


def _yuzde(pay: int, payda: int) -> float:
    return round(100.0 * pay / payda, 1) if payda else 0.0


def toplu(jobs_dir: str, n: int = 100) -> dict:
    """Son n isin toplu olcumu. ORNEKLEM KUCUKSE SOYLENIR - 12 is uzerinde yuzde
    konusmak gurultu uzerinde konusmaktir."""
    try:
        idler = sorted(os.listdir(jobs_dir))[-n:]
    except OSError:
        return {"hata": "is klasoru yok", "n": 0}
    kayitlar = []
    atlanan = 0
    for jid in idler:
        r = is_telemetri(jobs_dir, jid)
        if r.get("hata"):
            continue
        if r.get("kaynak") == "ornek":   # elle uretilmis gosterim isi OLCUME GIRMEZ
            atlanan += 1
            continue
        kayitlar.append(r)
    if not kayitlar:
        return {"n": 0, "uyari": "olculecek is yok", "ornek_atlandi": atlanan}

    bitmis = [r for r in kayitlar if r["gecti"] or r["onarim_turu"] or r["son_hata_siniflari"]]
    sinif_sayaci: dict = {}
    for r in kayitlar:
        for t in r["turlar"]:
            sinif_sayaci[t["sinif"]] = sinif_sayaci.get(t["sinif"], 0) + 1
        if not r["gecti"]:
            for s in r["son_hata_siniflari"]:
                sinif_sayaci[s] = sinif_sayaci.get(s, 0) + 1
    toplam_hata = sum(sinif_sayaci.values())

    modeller: dict = {}
    for r in kayitlar:
        m = modeller.setdefault(r["model"] or "?", {"n": 0, "gecti": 0, "ilk_tur": 0, "sure": 0})
        m["n"] += 1
        m["gecti"] += 1 if r["gecti"] else 0
        m["ilk_tur"] += 1 if r["ilk_tur_gecti"] else 0
        m["sure"] += r["sure"] or 0
    for m in modeller.values():
        m["basari_yuzde"] = _yuzde(m["gecti"], m["n"])
        m["ilk_tur_yuzde"] = _yuzde(m["ilk_tur"], m["n"])
        m["ort_sure"] = round(m["sure"] / m["n"], 1) if m["n"] else 0

    N = len(kayitlar)
    olculen = [r for r in kayitlar if r["istem_tok"]]
    ozet = {
        "n": N,
        "ilk_tur_basari": _yuzde(sum(1 for r in kayitlar if r["ilk_tur_gecti"]), N),
        "onarim_sonrasi_basari": _yuzde(sum(1 for r in kayitlar if r["gecti"]), N),
        "duraganlik": _yuzde(sum(1 for r in kayitlar if r["duragan"]), N),
        "devir_onerisi": _yuzde(sum(1 for r in kayitlar if r["devir_onerildi"]), N),
        "kapsam_ihlali_olan_is": sum(1 for r in kayitlar if r["kapsam_ihlali"]),
        "ort_istem_tok": round(sum(r["istem_tok"] for r in olculen) / len(olculen)) if olculen else 0,
        "ort_uretim_tok": round(sum(r["uretim_tok"] for r in olculen) / len(olculen)) if olculen else 0,
        "ort_sure": round(sum(r["sure"] for r in kayitlar) / N, 1),
        "hata_siniflari": dict(sorted(sinif_sayaci.items(), key=lambda x: -x[1])),
        "hata_sinifi_yuzde": {k: _yuzde(v, toplam_hata) for k, v in
                              sorted(sinif_sayaci.items(), key=lambda x: -x[1])},
        "bilinmeyen_orani": _yuzde(sinif_sayaci.get("bilinmeyen", 0), toplam_hata),
        "modeller": modeller,
        "bitmis_is": len(bitmis),
        "ornek_atlandi": atlanan,
    }
    if N < 20:
        ozet["uyari"] = ("orneklem KUCUK (%d is) - yuzdeler gurultu; karar vermeden once "
                         "en az 20-30 gercek is biriksin" % N)
    if toplam_hata and ozet["bilinmeyen_orani"] > 25:
        ozet["taksonomi_uyarisi"] = ("hatalarin %%%.1f'i siniflandirilamadi - taksonomi eksik, "
                                     "desen eklenmeli" % ozet["bilinmeyen_orani"])
    return ozet


def yazdir(jobs_dir: str, n: int = 100) -> None:
    o = toplu(jobs_dir, n)
    if o.get("hata"):
        print("HATA:", o["hata"])
        return
    print("SON %d IS" % o["n"])
    print("  ilk tur basari      %5.1f%%" % o["ilk_tur_basari"])
    print("  onarim sonrasi      %5.1f%%" % o["onarim_sonrasi_basari"])
    print("  duraganlik          %5.1f%%" % o["duraganlik"])
    print("  usta onerisi        %5.1f%%" % o["devir_onerisi"])
    print("  kapsam ihlali       %d is" % o["kapsam_ihlali_olan_is"])
    print("  ortalama            %s istem tok · %s uretim · %s sn"
          % (o["ort_istem_tok"], o["ort_uretim_tok"], o["ort_sure"]))
    if o["hata_siniflari"]:
        print("  hata siniflari:")
        for ad, sayi in o["hata_siniflari"].items():
            print("      %-18s %3d  (%%%.1f)" % (ad, sayi, o["hata_sinifi_yuzde"][ad]))
    else:
        print("  hata siniflari:     (hic hata kaydi yok)")
    if len(o["modeller"]) > 1:
        print("  modele gore:")
        for ad, m in sorted(o["modeller"].items(), key=lambda x: -x[1]["n"]):
            print("      %-34s n=%-3d basari %%%-5.1f ilk tur %%%-5.1f  %.0f sn"
                  % (ad[:34], m["n"], m["basari_yuzde"], m["ilk_tur_yuzde"], m["ort_sure"]))
    for anahtar in ("uyari", "taksonomi_uyarisi"):
        if o.get(anahtar):
            print("  ! %s" % o[anahtar])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ev = os.environ.get("APPRENTICE_HOME") or os.path.join(os.path.expanduser("~"), ".apprentice")
    yazdir(os.path.join(ev, "jobs"), int(sys.argv[1]) if len(sys.argv) > 1 else 100)

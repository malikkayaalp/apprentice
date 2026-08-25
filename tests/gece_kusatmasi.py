"""GECE KUSATMASI: makine bosken kosan uzun olcum + saglamlik turu.

    python tests/gece_kusatmasi.py [--saat 5] [--asama zorluk,code,ozellik,...]

NEDEN: elimizde BASARISIZLIK VERISI YOK - 9 gercek isin dokuzu da ilk turda gecmis. Hata
taksonomisi (core/telemetri.py) kagit uzerinde dogru ama sahada hic sinanmadi. Bu kosu
once ZOR gorevlerle gercek basarisizlik uretir, sonra o veriyle taksonomiyi olcer.

TASARIM KURALLARI (gozetimsiz kosuyor, kimse basinda degil):
  1. Her asama YALITIK: biri patlarsa digerleri devam eder, sebebi rapora yazilir.
  2. BUTCE var: --saat asilirsa kalan asamalar ATLANIR ve bu rapora YAZILIR. Sessiz
     kirpma yok - "kapsandi" gorunup kapsanmamak en kotusu.
  3. Her asamadan sonra OKSUZ SUREC temizligi: Ollama zorla kapatilinca llama-server
     RAM'i (10-50 GB) salmiyor (olculdu: 13 GB). Gece boyunca birikirse makine tikanir.
  4. Ham cikti diske yazilir; rapor onun OZETI. Sabah once rapora bakilir, gerekirse hama.
  5. Kullanicinin GERCEK is klasorune (~/.apprentice) DOKUNULMAZ; kampanyalar kendi test
     evinde kosar. Telemetri de o evi olcer.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TEST_EV = os.path.join(ROOT, ".apprentice_test_home")
CIKTI = os.path.join(ROOT, "reports")
PZ = 0x08000000 if os.name == "nt" else 0


def _log(mesaj: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), mesaj), flush=True)


def _oksuz_temizle() -> dict:
    """Oksuz llama-server sureclerini avla. Ollama'nin kaydinda gorunmezler ama RAM tutarlar."""
    try:
        from core import tani
        oks = tani.oksuz_kosucular()
        if not oks:
            return {"kapanan": 0, "gb": 0.0}
        r = tani.oksuz_temizle()
        return {"kapanan": len(r.get("kapanan") or oks), "gb": r.get("kazanilan_gb", 0.0)}
    except Exception as e:  # noqa: BLE001
        return {"hata": str(e)[:120]}


def _kos(ad: str, kod: list, zaman_asimi: int, ortam_ek: dict | None = None) -> dict:
    """Bir asamayi kosur. ASLA istisna firlatmaz - sonucu sozluk olarak doner."""
    t0 = time.time()
    ev = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    ev.update(ortam_ek or {})
    ham = os.path.join(CIKTI, "gece_%s.log" % ad)
    try:
        with open(ham, "w", encoding="utf-8") as f:
            r = subprocess.run(kod, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                               timeout=zaman_asimi, env=ev, creationflags=PZ)
        kod_no = r.returncode
        hata = ""
    except subprocess.TimeoutExpired:
        kod_no, hata = -1, "ZAMAN ASIMI (%d sn)" % zaman_asimi
    except Exception as e:  # noqa: BLE001
        kod_no, hata = -2, str(e)[:200]
    sure = round(time.time() - t0, 1)
    son = ""
    try:
        with open(ham, encoding="utf-8", errors="replace") as f:
            satirlar = [s.rstrip() for s in f.read().splitlines() if s.strip()]
        son = "\n".join(satirlar[-12:])
    except OSError:
        pass
    return {"ad": ad, "cikis": kod_no, "sure": sure, "hata": hata, "son": son, "ham": ham}


def _telemetri(jobs_dir: str) -> dict:
    try:
        from core.telemetri import toplu
        return toplu(jobs_dir, 500)
    except Exception as e:  # noqa: BLE001
        return {"hata": str(e)[:200]}


def asamalar(butce_sn: float) -> list:
    """Sira ONEM + SURE'ye gore: model gerektiren uzun isler once (butce onlara ayrilsin),
    CPU'luk hizli denetimler sonra."""
    zor = max(1800, int(butce_sn * 0.40))
    kolay = max(1200, int(butce_sn * 0.25))
    return [
        # 1) BASARISIZLIK URET: zor gorevler, gizli denetci kontrolleriyle
        ("zorluk", [sys.executable, "tests/zorluk_kampanya.py", "--tur", "2"], zor, {}),
        # 2) TEMEL CIZGI: 6 gorevlik standart kampanya
        ("code", [sys.executable, "tests/code_kampanya.py", "--tur", "2"], kolay, {}),
        # 3) DERIN OZELLIK TARAMASI: 20000 uretilmis girdi (gunluk kosu 400)
        ("ozellik_derin", [sys.executable, "tests/test_ozellik.py"], 3600,
         {"APPRENTICE_OZELLIK": "20000"}),
        # 4) BUGUN EKLENENLERIN SENARYO TESTLERI (varsa)
        ("senaryo", [sys.executable, "tests/test_senaryo.py"], 1800, {}),
        # 5) TAM BATARYA: hicbir sey bozulmamis olmali
        ("batarya", [sys.executable, "tests/hepsi.py", "--hizli"], 1800, {}),
    ]


def rapor_yaz(sonuclar: list, tel_once: dict, tel_sonra: dict, t0: float,
              atlanan: list) -> str:
    yol = os.path.join(CIKTI, "gece_raporu.md")
    S = []
    S.append("# Gece kusatmasi raporu")
    S.append("")
    S.append("baslangic: %s · sure: %.0f dk"
             % (time.strftime("%Y-%m-%d %H:%M", time.localtime(t0)), (time.time() - t0) / 60))
    S.append("")
    S.append("## Asamalar")
    S.append("")
    S.append("| asama | sonuc | sure |")
    S.append("|---|---|---|")
    for r in sonuclar:
        durum = "GECTI" if r["cikis"] == 0 else ("ATLANDI" if r["cikis"] is None
                                                 else "KALDI (%s)" % (r["hata"] or r["cikis"]))
        S.append("| %s | %s | %.0f sn |" % (r["ad"], durum, r["sure"]))
    for a in atlanan:
        S.append("| %s | ATLANDI - butce bitti | - |" % a)
    S.append("")
    for r in sonuclar:
        if r["cikis"] != 0 and r.get("son"):
            S.append("### %s son satirlar" % r["ad"])
            S.append("```")
            S.append(r["son"][:1500])
            S.append("```")
            S.append("")
    S.append("## Telemetri: kampanya ONCESI -> SONRASI")
    S.append("")
    S.append("| olcum | once | sonra |")
    S.append("|---|---|---|")
    for anahtar, etiket in (("n", "is sayisi"), ("ilk_tur_basari", "ilk tur basari %"),
                            ("onarim_sonrasi_basari", "onarim sonrasi %"),
                            ("duraganlik", "duraganlik %"), ("devir_onerisi", "usta onerisi %"),
                            ("ort_istem_tok", "ort istem tok"), ("ort_sure", "ort sure sn"),
                            ("bilinmeyen_orani", "siniflanamayan %")):
        S.append("| %s | %s | %s |" % (etiket, tel_once.get(anahtar, "-"),
                                       tel_sonra.get(anahtar, "-")))
    S.append("")
    hs = tel_sonra.get("hata_siniflari") or {}
    S.append("## Hata siniflari (taksonomi SAHADA)")
    S.append("")
    if hs:
        S.append("| sinif | adet | %% |")
        S.append("|---|---|---|")
        for ad, sayi in hs.items():
            S.append("| %s | %d | %.1f |" % (ad, sayi,
                                             (tel_sonra.get("hata_sinifi_yuzde") or {}).get(ad, 0)))
    else:
        S.append("Hic hata kaydi olusmadi - kampanyalar basarisizlik uretmedi.")
    S.append("")
    for anahtar in ("uyari", "taksonomi_uyarisi"):
        if tel_sonra.get(anahtar):
            S.append("> %s" % tel_sonra[anahtar])
            S.append("")
    mod = tel_sonra.get("modeller") or {}
    if len(mod) > 1:
        S.append("## Modele gore (kendi gercek islerinden)")
        S.append("")
        S.append("| model | is | basari %% | ilk tur %% | ort sure |")
        S.append("|---|---|---|---|---|")
        for ad, m in sorted(mod.items(), key=lambda x: -x[1]["n"]):
            S.append("| %s | %d | %.1f | %.1f | %.0f sn |"
                     % (ad[:44], m["n"], m["basari_yuzde"], m["ilk_tur_yuzde"], m["ort_sure"]))
        S.append("")
    S.append("Ham ciktilar: `reports/gece_*.log`")
    metin = "\n".join(S) + "\n"
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    return yol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saat", type=float, default=5.0, help="toplam butce (saat)")
    ap.add_argument("--asama", default="", help="virgulle: yalniz bunlar kossun")
    a = ap.parse_args()
    os.makedirs(CIKTI, exist_ok=True)
    os.makedirs(os.path.join(TEST_EV, "jobs"), exist_ok=True)
    t0 = time.time()
    butce = a.saat * 3600
    secili = {x.strip() for x in a.asama.split(",") if x.strip()}

    _log("GECE KUSATMASI basliyor - butce %.1f saat" % a.saat)
    tel_once = _telemetri(os.path.join(TEST_EV, "jobs"))
    _log("kampanya oncesi test evi: %s gercek is" % tel_once.get("n", 0))
    t = _oksuz_temizle()
    if t.get("kapanan"):
        _log("oksuz temizligi: %s surec, %.1f GB" % (t["kapanan"], t.get("gb", 0)))

    sonuclar, atlanan = [], []
    for ad, kod, sinir, ek in asamalar(butce):
        if secili and ad not in secili:
            continue
        kalan = butce - (time.time() - t0)
        if kalan < 120:
            _log("BUTCE BITTI - atlanan: %s" % ad)
            atlanan.append(ad)
            continue
        sinir = int(min(sinir, kalan))
        betik = kod[1] if len(kod) > 1 else ""
        if betik.endswith(".py") and not os.path.isfile(os.path.join(ROOT, betik)):
            _log("!! %s betigi YOK (%s) - atlandi" % (ad, betik))
            sonuclar.append({"ad": ad, "cikis": None, "sure": 0.0,
                             "hata": "betik yok: %s" % betik, "son": "", "ham": ""})
            continue
        _log("-> %s basliyor (sinir %d sn, kalan butce %d dk)" % (ad, sinir, kalan / 60))
        r = _kos(ad, kod, sinir, ek)
        sonuclar.append(r)
        _log("<- %s: %s (%.0f sn)" %
             (ad, "GECTI" if r["cikis"] == 0 else "KALDI/%s" % (r["hata"] or r["cikis"]), r["sure"]))
        t = _oksuz_temizle()
        if t.get("kapanan"):
            _log("   oksuz temizligi: %s surec, %.1f GB" % (t["kapanan"], t.get("gb", 0)))

    tel_sonra = _telemetri(os.path.join(TEST_EV, "jobs"))
    yol = rapor_yaz(sonuclar, tel_once, tel_sonra, t0, atlanan)
    _log("BITTI - %.0f dk. Rapor: %s" % ((time.time() - t0) / 60, yol))
    gecen = sum(1 for r in sonuclar if r["cikis"] == 0)
    _log("asama: %d/%d gecti, %d atlandi" % (gecen, len(sonuclar), len(atlanan)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

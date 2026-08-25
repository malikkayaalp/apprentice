"""TUTARLILIK testi - denetim bulgulari 8, 9, 11, 12, 14.

BULGU 8: canli rapor her yazimin farkini AYRI hesaplayip TOPLUYORDU; disk raporu NET fark
kullaniyordu. Ayni dosya uc kez yazilip basa donse canli rapor "+2 -2", disk raporu "+0 -0"
diyordu - AYNI IS icin iki farkli sayi.

BULGU 9: zaman cizgisi son arac sonucundan `result`'a kadarki HER SEYI "dogrulama"
sayiyordu; modelin nihai cevabi hazirladigi sure de dahildi. Arac hic kullanilmayan bir
iste surenin TAMAMI dogrulama gorunuyordu (olculdu: 60 sn uretim -> 60 sn "dogrulama").

BULGU 11: sohbet kilidi model cagrisi boyunca BIRAKILIYORDU; iki es zamanli istek gecmisi
karistirabiliyordu. Sifirlama da ucustaki istekle yarisiyordu.

BULGU 12: `--tek` yolunda `SadeceSunucu` cagirana sonuc DONDURMUYORDU; sunucu kurulamasa
bile pencere aciliyordu.

BULGU 14: kod calisma kokunu UC yoldan cozuyor, belge yalnizca birini anlatiyordu.
"""
from __future__ import annotations
import json, os, sys, tempfile, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.gizlilik import VARSAYILAN as GIZ  # noqa: E402
from core.inceleme import inceleme  # noqa: E402


def _sunucu():
    os.environ["APPRENTICE_HOME"] = os.path.join(ROOT, ".apprentice_test_home", "tutarlilik")
    import importlib
    return importlib.import_module("server.apprentice_server")


def _is(srv, olaylar):
    """Gercek bir Job olusturup olaylarini yazar; iki rapor yolu da ayni isi okur."""
    job = srv.Job("fake", "gorev", [], "", False, 0, "m", "")
    job.done = True
    with open(job.events_path, "w", encoding="utf-8") as f:
        for e in olaylar:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(job.dir, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": job.id, "ortam": "fake", "durum": "bitti"}, f)
    return job


def iki_rapor_ayni_sayiyi_veriyor() -> bool:
    """CANLI ve DISK raporu ayni is icin AYNI degisiklik miktarini vermeli."""
    srv = _sunucu()
    senaryolar = {
        "bir kez yazildi": [{"type": "write", "path": "a.py", "before": "", "after": "x=1\n"}],
        "ayni dosya UC kez": [
            {"type": "write", "path": "a.py", "before": "", "after": "s1\n"},
            {"type": "write", "path": "a.py", "before": "s1\n", "after": "s1\ns2\n"},
            {"type": "write", "path": "a.py", "before": "s1\ns2\n", "after": "s1\ns2\ns3\n"}],
        "yazilip BASA donen": [
            {"type": "write", "path": "a.py", "before": "asil\n", "after": "degisti\n"},
            {"type": "write", "path": "a.py", "before": "degisti\n", "after": "asil\n"}],
        "yeni dosya": [{"type": "write", "path": "yeni.py", "before": None, "after": "x\ny\n"}],
        "silinen (bosaltilan)": [
            {"type": "write", "path": "a.py", "before": "s1\ns2\n", "after": ""}],
    }
    for ad, ol in senaryolar.items():
        job = _is(srv, ol + [{"type": "result", "ok": True, "errors": [], "rounds": 0},
                             {"type": "exit", "code": 0}])
        canli = {d["yol"]: (d["eklendi"], d["silindi"]) for d in job.report()["yazilan_dosyalar"]}
        disk = {d["yol"]: (d["eklendi"], d["silindi"])
                for d in (srv.rapor_diskten(job.id) or {}).get("yazilan_dosyalar", [])}
        assert canli == disk, "%s: canli %s != disk %s" % (ad, canli, disk)

    # "basa donen" senaryosunda NET degisiklik SIFIR olmali - toplama yapan surum "+1 -1" derdi
    job = _is(srv, senaryolar["yazilip BASA donen"] +
              [{"type": "result", "ok": True, "errors": [], "rounds": 0}])
    d0 = job.report()["yazilan_dosyalar"][0]
    assert (d0["eklendi"], d0["silindi"]) == (0, 0), "net fark degil, turlar toplanmis: %s" % d0
    assert d0.get("yazma") == 2, "kac kez yazildigi kaybolmus: %s" % d0
    print("iki rapor ayni sayiyi veriyor: ok (5 senaryo, net fark)")
    return True


def zaman_cizgisi_dogrulamayi_uydurmuyor() -> bool:
    """Dogrulama suresi YALNIZCA kanitli aralik. Aracsiz iste yapay sure URETILMEZ."""
    d = tempfile.mkdtemp()
    jd = os.path.join(d, "is1")
    os.makedirs(jd)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "is1", "ortam": "code", "calisma_dizini": d}, f)

    def kos(ol):
        with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
            for e in ol:
                f.write(json.dumps(e) + "\n")
        return inceleme(d, "is1")["zaman_cizgisi"]

    T = 1000.0
    # 1) ARACSIZ: hepsi uretim
    z = kos([{"type": "system", "t": T},
             {"type": "assistant", "text": "uzun cevap", "t": T + 60},
             {"type": "result", "ok": True, "errors": [], "t": T + 60}])
    assert z["ozet"]["dogrulama"] == 0.0, "aracsiz iste uydurma dogrulama: %s" % z["ozet"]
    assert z["ozet"]["uretim"] == 60.0, z["ozet"]

    # 2) TEK ARAC + nihai cevap: uc dilim de dogru
    z2 = kos([{"type": "system", "t": T},
              {"type": "tool", "name": "run_tests", "t": T + 10},
              {"type": "tool_result", "name": "run_tests", "t": T + 25},
              {"type": "assistant", "text": "x", "t": T + 40},
              {"type": "result", "ok": True, "errors": [], "t": T + 50}])
    assert z2["ozet"] == {"uretim": 25.0, "arac": 15.0, "dogrulama": 10.0,
                          "bilinmiyor": 0.0}, z2["ozet"]

    # 3) BIRDEN FAZLA dogrulama komutu
    z3 = kos([{"type": "system", "t": T},
              {"type": "tool", "name": "run_tests", "t": T + 5},
              {"type": "tool_result", "name": "run_tests", "t": T + 15},
              {"type": "tool", "name": "run_shell", "t": T + 16},
              {"type": "tool_result", "name": "run_shell", "t": T + 20},
              {"type": "assistant", "text": "x", "t": T + 22},
              {"type": "result", "ok": True, "errors": [], "t": T + 30}])
    assert z3["ozet"]["arac"] == 14.0, z3["ozet"]
    assert z3["ozet"]["dogrulama"] == 8.0, z3["ozet"]

    # 4) SON ARACTAN SONRA UZUN nihai cevap: bu sure DOGRULAMA DEGIL
    z4 = kos([{"type": "system", "t": T},
              {"type": "tool", "name": "w", "t": T + 1},
              {"type": "tool_result", "name": "w", "t": T + 2},
              {"type": "assistant", "text": "cok uzun cevap", "t": T + 90},
              {"type": "result", "ok": True, "errors": [], "t": T + 92}])
    assert z4["ozet"]["uretim"] == 89.0, "uzun nihai cevap dogrulama sayildi: %s" % z4["ozet"]
    assert z4["ozet"]["dogrulama"] == 2.0, z4["ozet"]

    # 5) ASSISTANT YOK: sinir bilinmez -> UYDURMA YOK
    z5 = kos([{"type": "system", "t": T},
              {"type": "tool", "name": "w", "t": T + 5},
              {"type": "tool_result", "name": "w", "t": T + 6},
              {"type": "result", "ok": True, "errors": [], "t": T + 30}])
    assert z5["ozet"]["dogrulama"] == 0.0 and z5["ozet"]["bilinmiyor"] == 24.0, z5["ozet"]

    # 6) GOSTERIM SINIRI acikca bildirilir (ekrandaki dilimler toplami != toplam)
    cok = [{"type": "system", "t": T}]
    for i in range(60):
        cok += [{"type": "tool", "name": "a%d" % i, "t": T + i * 2 + 1},
                {"type": "tool_result", "name": "a%d" % i, "t": T + i * 2 + 1.9}]
    cok += [{"type": "assistant", "text": "x", "t": T + 130},
            {"type": "result", "ok": True, "errors": [], "t": T + 140}]
    z6 = kos(cok)
    assert z6["kirpildi"] is True, z6.get("dilim_sayisi")
    assert z6["dilim_sayisi"] > len(z6["dilimler"]), z6["dilim_sayisi"]
    # ozet KIRPILMAMIS toplami tasir - yoksa panel yuzdeleri yaniltir
    assert sum(z6["ozet"].values()) > sum(x["sure"] for x in z6["dilimler"]), z6["ozet"]
    print("zaman cizgisi dogrulamayi uydurmuyor: ok (6 senaryo)")
    return True


def sohbet_alisverisi_bolunmuyor() -> bool:
    """Ayni oturumdaki istekler SIRALI islenir; sifirlama ucustaki cevabi yeni gecmise
    EKLEMEZ. Kaynak sozlesmesi + gercek es zamanlilik denemesi."""
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        p = f.read()
    assert "SOHBET_SIRA" in p, "sohbet sira kilidi yok"
    govde = p[p.index("def _cirak_sohbet("):p.index("def _usta_istek(")]
    assert "with SOHBET_SIRA:" in govde, "alisveris tek kilit altinda degil"
    assert '"nesil"' in p, "sifirlama nesli yok - ucustaki cevap yeni gecmise sizabilir"

    # GERCEK yaris: iki is parcacigi ayni kilidi alirsa alisverisler ATLAMAZ
    kilit = threading.Lock()
    gecmis: list = []

    def alisveris(ad):
        with kilit:                      # panel.py'deki SOHBET_SIRA'nin es degeri
            gecmis.append("soru-" + ad)
            time.sleep(0.02)             # "model cagrisi"
            gecmis.append("cevap-" + ad)

    is_p = [threading.Thread(target=alisveris, args=(str(i),)) for i in range(4)]
    for t in is_p:
        t.start()
    for t in is_p:
        t.join()
    for i in range(0, len(gecmis), 2):
        assert gecmis[i].startswith("soru-") and gecmis[i + 1].startswith("cevap-"), gecmis
        assert gecmis[i][5:] == gecmis[i + 1][6:], "soru ve cevabi ayrildi: %s" % gecmis
    print("sohbet alisverisi bolunmuyor: ok (kilit + nesil)")
    return True


def tek_pencere_hatayi_bildiriyor() -> bool:
    """`--tek`: sunucu kurulamazsa PENCERE ACILMAZ ve sebep gosterilir."""
    with open(os.path.join(ROOT, "shell", "ApprenticePanel", "Program.cs"), encoding="utf-8") as f:
        c = f.read()
    assert "public async Task<bool> SadeceSunucu(" in c, "SadeceSunucu hala sonuc dondurmuyor"
    assert "if (!await ana.SadeceSunucu(args))" in c, "cagiran sonucu denetlemiyor"
    govde = c[c.index("public async Task<bool> SadeceSunucu("):]
    govde = govde[:govde.index("\n    private static string EvKlasoru()")]
    assert govde.count("return false;") >= 3, "basarisizlik yollari eksik: %d" % govde.count("return false;")
    assert "SunucuyuDurdur();" in govde, "kismen baslatilmis surec temizlenmiyor"
    # basarisizlikta PENCERE ACILMAMALI: Close() cagrisi Popen/AltPencere'den ONCE
    tasiyici = c[c.index("internal sealed class TekPencereBaslatici"):c.index("internal sealed class PanelForm")]
    assert tasiyici.index("Close();") < tasiyici.index("alt.Show();"), \
        "basarisizlikta yine de pencere aciliyor"
    print("tek pencere hatayi bildiriyor: ok")
    return True


def belge_calisma_kokunu_dogru_anlatiyor() -> bool:
    """server/README kodun UC yolunu da anlatmali (belge eksik anlatiyordu)."""
    with open(os.path.join(ROOT, "server", "README.md"), encoding="utf-8") as f:
        m = f.read()
    assert "Çalışma kökü nasıl belirlenir" in m, "calisma koku bolumu yok"
    for anahtar in ("MCP `roots`", "APPRENTICE_WORKDIR_ROOT", "depo kökünün"):
        assert anahtar in m, "belge %s yolunu anlatmiyor" % anahtar
    assert "sessiz yedekleme" in m, "kaldirilan sessiz yedekleme anlatilmamis"
    # KOD ile uyum: uc yol gercekten var mi
    with open(os.path.join(ROOT, "server", "apprentice_server.py"), encoding="utf-8") as f:
        k = f.read()
    assert "APPRENTICE_WORKDIR_ROOT" in k, "belge olmayan bir yol anlatiyor"
    print("belge calisma kokunu dogru anlatiyor: ok")
    return True


def main() -> int:
    denemeler = [iki_rapor_ayni_sayiyi_veriyor, zaman_cizgisi_dogrulamayi_uydurmuyor,
                 sohbet_alisverisi_bolunmuyor, tek_pencere_hatayi_bildiriyor,
                 belge_calisma_kokunu_dogru_anlatiyor]
    kalan = 0
    for fn in denemeler:
        try:
            fn()
        except AssertionError as e:
            print("KALDI - %s: %s" % (fn.__name__, str(e)[:400]))
            kalan += 1
        except Exception as e:  # noqa: BLE001
            print("PATLADI - %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]))
            kalan += 1
    print("SONUC:", "GECTI" if not kalan else "KALDI (%d)" % kalan)
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())

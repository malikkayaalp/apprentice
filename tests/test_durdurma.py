"""DURDURMA ve YENIDEN BASLATMA testi - denetim bulgulari 7 ve 6.

BULGU 7: `Job.kill()` taskkill'in DONUS KODUNU okumadan kosulsuz `return` ediyordu. Komut
basarisiz olsa bile (erisim reddedildi, taskkill yok, PID bulunamadi) cagiran taraf
"olduruldu" saniyordu; ustelik surecin gercekten oldugu HIC dogrulanmiyordu. Gunluge de
kosulsuz "olduruldu" yaziliyordu.

BULGU 6: panel yeniden baslatilirken calisan isler durdurulmuyordu (`os._exit(0)`). Yeni
kuyruk eski isi "yarim" sayip SIRADAKINI baslatiyor, eski isci ise HALA ayni projeye
yaziyordu: iki yazan, tek proje.

Cakilan sozlesme:
  1. kill() ne yaptigini SOYLER: durum/yontem/sebep/pid doner.
  2. "durduruldu" ANCAK surec gercekten kapandiysa denir; kapanmazsa "DURMADI".
  3. taskkill basarisizsa proc.kill()'e DUSULUR - tek yola bagli kalmayiz.
  4. Bitmis/olmayan surec icin dogru ve AYRI durumlar doner.
  5. Yeniden baslatma once isleri durdurur; DURMAYAN varsa yeniden baslatmaz.
  6. Cokme kurtarma: isci HALA CALISIYORSA is "yarim" sayilmaz, kuyruk yeni is baslatmaz.
  7. Bitmis islerin surec kayitlari birikmez (JOBS sinirsiz buyumez).
"""
from __future__ import annotations
import os, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
PZ = 0x08000000 if os.name == "nt" else 0


def _sunucu():
    os.environ["APPRENTICE_HOME"] = os.path.join(ROOT, ".apprentice_test_home", "durdurma")
    import importlib
    return importlib.import_module("server.apprentice_server")


def _uyuyan(srv, saniye=60):
    """Gercek bir alt surec baslatan sahte is."""
    job = srv.Job("fake", "uyu", [], "", False, 0, "m", "")
    job.proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%d)" % saniye],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=PZ)
    return job


def gercekten_durduruyor() -> bool:
    """kill() surecin OLDUGUNU dogrular ve ne yaptigini soyler."""
    srv = _sunucu()
    job = _uyuyan(srv)
    pid = job.proc.pid
    assert job.proc.poll() is None, "alt surec baslamadi"

    sonuc = job.kill()
    assert sonuc["durum"] == "durduruldu", sonuc
    assert sonuc["pid"] == pid and sonuc["yontem"], sonuc
    assert job.proc.poll() is not None, "surec hala yasiyor ama 'durduruldu' dendi"
    assert sonuc["sure"] < 5.0, sonuc

    # ZATEN BITMIS surec: ayri ve dogru durum, yeniden oldurmeye calismaz
    s2 = job.kill()
    assert s2["durum"] == "zaten_bitmis", s2

    # SUREC HIC YOK
    bos = srv.Job("fake", "x", [], "", False, 0, "m", "")
    assert bos.kill()["durum"] == "surec_yok", bos.kill()
    print("gercekten durduruyor: ok (durduruldu / zaten_bitmis / surec_yok ayri)")
    return True


def taskkill_basarisizsa_duser() -> bool:
    """taskkill patlarsa proc.kill()'e DUSULUR - tek yola bagli kalmayiz."""
    if os.name != "nt":
        print("taskkill basarisizsa duser: yalniz Windows, atlandi")
        return True
    srv = _sunucu()
    job = _uyuyan(srv)
    asil = subprocess.run

    def patlak(cmd, *a, **k):
        if isinstance(cmd, list) and cmd and str(cmd[0]).lower().startswith("taskkill"):
            raise OSError("taskkill yok (simule)")
        return asil(cmd, *a, **k)

    subprocess.run = patlak
    try:
        sonuc = job.kill()
    finally:
        subprocess.run = asil
    assert sonuc["durum"] == "durduruldu", "taskkill patlayinca yedek yol calismadi: %s" % sonuc
    assert "proc.kill()" in sonuc["yontem"], sonuc
    assert "simule" in (sonuc.get("sebep") or ""), "taskkill hatasi yutuldu: %s" % sonuc
    assert job.proc.poll() is not None
    print("taskkill basarisizsa duser: ok (yedek yol + sebep kayitli)")
    return True


def durmayan_surec_yalan_soylemez() -> bool:
    """Surec kapanmazsa 'DURMADI' doner - kullaniciya 'durduruldu' DENMEZ."""
    srv = _sunucu()
    job = _uyuyan(srv)

    class Olmez:
        """Oldurulemeyen surec taklidi: kill cagrilir ama surec yasamaya devam eder."""
        def __init__(self, gercek):
            self._g = gercek
            self.pid = gercek.pid
        def poll(self):
            return None                 # ASLA olmedi de
        def kill(self):
            pass

    gercek = job.proc
    job.proc = Olmez(gercek)
    asil = subprocess.run
    subprocess.run = lambda *a, **k: type("R", (), {"returncode": 1, "stderr": b"erisim reddedildi"})()
    try:
        sonuc = job.kill(bekle=0.3)
    finally:
        subprocess.run = asil
        job.proc = gercek
        job.kill()                      # gercek sureci temizle
    assert sonuc["durum"] == "DURMADI", "olmeyen surec icin 'durduruldu' dendi: %s" % sonuc
    assert sonuc["sebep"], "sebep bos - kullanici neden durmadigini bilemez"
    print("durmayan surec yalan soylemez: ok (DURMADI + sebep)")
    return True


def yeniden_baslatma_once_durdurur() -> bool:
    """Yeniden baslatma calisan isi durdurur; DURDURAMAZSA yeniden baslatmaz.

    Kaynak sozlesmesi: eski surum dogrudan Popen + os._exit(0) yapiyordu."""
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        p = f.read()
    govde = p[p.index("def _yeniden_baslat("):p.index("def _sayi(")]
    i_kill = govde.index("job.kill()")
    i_popen = govde.index("Popen(")
    assert i_kill < i_popen, "yeni surec, calisan isler durdurulmadan aciliyor"
    assert "if sorunlu:" in govde, "durdurulamayan is varken yine de yeniden baslatiliyor"
    assert govde.index("if sorunlu:") < i_popen, "sorun denetimi Popen'dan SONRA"
    assert "durdurulamayan" in govde, "durdurulamayan isler cagirana bildirilmiyor"
    print("yeniden baslatma once durdurur: ok (kill -> denetim -> Popen)")
    return True


def canli_isci_yarim_sayilmaz() -> bool:
    """Cokme kurtarma: isci HALA CALISIYORSA is 'yarim' sayilmaz ve yeni is BASLAMAZ."""
    from core.kuyruk import Kuyruk
    ev = tempfile.mkdtemp()
    baslatilan = []

    def calistir(istek):
        baslatilan.append(istek)
        return {"is_id": "is%d" % len(baslatilan)}

    k = Kuyruk(ev, calistir, lambda j: False)
    k.ekle({"gorev": "bir"}); k.ekle({"gorev": "iki"})
    k.adim()                                   # birinci kosuyor
    assert k.liste()["sayim"]["kosuyor"] == 1

    # --- panel yeniden baslatildi; ISCI HALA CANLI ---
    k2 = Kuyruk(ev, calistir, lambda j: False, hala_calisiyor=lambda j: True)
    d = k2.liste()
    assert d["sayim"]["yarim"] == 0, "canli isci 'yarim' sayildi: %s" % d["sayim"]
    assert d["sayim"]["kosuyor"] == 1, d["sayim"]
    kosan = [o for o in d["ogeler"] if o["durum"] == "kosuyor"][0]
    assert kosan.get("sahipsiz") is True and "HALA" in kosan["sebep"], kosan
    # IKINCI YAZAN OLUSMAMALI
    assert k2.adim() in ("bekleniyor", "bosta"), "canli isci varken yeni is baslatildi"
    assert len(baslatilan) == 1, "ikinci isci baslatildi: %s" % baslatilan

    # --- isci GERCEKTEN olmusse: yarim ---
    k3 = Kuyruk(ev, calistir, lambda j: False, hala_calisiyor=lambda j: False)
    assert k3.liste()["sayim"]["yarim"] == 1, k3.liste()["sayim"]

    # --- biz yokken BITMISSE: bitti (yarim degil) ---
    ev2 = tempfile.mkdtemp()
    k4 = Kuyruk(ev2, calistir, lambda j: False)
    k4.ekle({"gorev": "x"}); k4.adim()
    k5 = Kuyruk(ev2, calistir, lambda j: True, hala_calisiyor=lambda j: False)
    assert k5.liste()["sayim"]["bitti"] == 1, k5.liste()["sayim"]
    print("canli isci yarim sayilmaz: ok (canli/olu/bitmis uc hal ayri)")
    return True


def is_kayitlari_birikmez() -> bool:
    """JOBS sinirsiz buyumez; BITMEMIS is asla dusurulmez."""
    srv = _sunucu()
    srv.JOBS.clear()
    eski_sinir = srv.JOBS_SINIR
    srv.JOBS_SINIR = 10
    try:
        for i in range(25):
            j = srv.Job("fake", "is%d" % i, [], "", False, 0, "m", "")
            j.done = True
            j.t0 = 1000.0 + i
            srv.JOBS[j.id] = j
            srv._jobs_buda()
        assert len(srv.JOBS) <= srv.JOBS_SINIR, "JOBS budanmadi: %d" % len(srv.JOBS)
        # BITMEMIS isler korunur
        srv.JOBS.clear()
        canli = []
        for i in range(15):
            j = srv.Job("fake", "canli%d" % i, [], "", False, 0, "m", "")
            j.done = False
            srv.JOBS[j.id] = j
            canli.append(j.id)
        for i in range(15):
            j = srv.Job("fake", "bitmis%d" % i, [], "", False, 0, "m", "")
            j.done = True
            srv.JOBS[j.id] = j
            srv._jobs_buda()
        for jid in canli:
            assert jid in srv.JOBS, "BITMEMIS is dusuruldu: %s" % jid
    finally:
        srv.JOBS_SINIR = eski_sinir
        srv.JOBS.clear()
    print("is kayitlari birikmez: ok (bitmisler budandi, calisanlar korundu)")
    return True


def main() -> int:
    denemeler = [gercekten_durduruyor, taskkill_basarisizsa_duser,
                 durmayan_surec_yalan_soylemez, yeniden_baslatma_once_durdurur,
                 canli_isci_yarim_sayilmaz, is_kayitlari_birikmez]
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

"""KUYRUK: isleri SIRAYLA kosturur, panelin basinda beklemek gerekmesin.

NEDEN: bugun panel tek is aliyor ve o bitene kadar makine bosta bekliyor - kullanici
disari cikinca 40 dakikalik GPU bosa gidiyor. Kuyruk, "sirala ve git" demeyi saglar.

SERI, PARALEL DEGIL (olculmus karar): tek Ollama modeli, tek GPU. Ikinci isi ayni anda
kosturmak bellek baskisi yaratir - num_batch olcumu VRAM'in sinir kaynak oldugunu gosterdi
(4096 => +%285 prefill AMA VRAM harciyor, kucuk kartta sigmiyor). Iki is ayni anda model
yuklerse ikisi de yavaslar; toplam is AZALIR. Bu yuzden es zamanlilik = 1.
`es_zamanli` parametresi var ama varsayilani 1 ve degistirmeden ONCE olculmelidir.

COKME GUVENLIGI: kuyruk diske yazilir. Panel kapanip acilirsa "kosuyor" durumundaki oge
SESSIZCE YENIDEN KOSTURULMAZ - "yarim" isaretlenir. Sebep: o is calisma alanina dosya
YAZMIS olabilir; yeniden kosturmak ayni dosyayi ikinci kez ezmek demektir. Karar
kullanicinin: panelden yeniden sirala ya da at.

TEK YAZAR KURALI KORUNUR: kuyruk kendi dosyasinda (`kuyruk.json`). Is kaydina
(`events.jsonl`) YAZMAZ - oraya yalnizca isin sahibi yazar.

BAGIMLILIK ENJEKSIYONU: `calistir` ve `bitti_mi` disaridan verilir. Boylece kuyruk mantigi
panel/Ollama olmadan test edilebilir - is baslatmadan sira, duraklatma, cokme kurtarma ve
politika kararlari sinanir.
"""
from __future__ import annotations
import json, os, threading, time

SEMA = 1
DURUMLAR = ("bekliyor", "kosuyor", "bitti", "hata", "iptal", "yarim")


def _simdi() -> float:
    return time.time()


class Kuyruk:
    def __init__(self, home: str, calistir, bitti_mi, politika=None,
                 es_zamanli: int = 1, yoklama_s: float = 2.0, hala_calisiyor=None):
        self.yol = os.path.join(home, "kuyruk.json")
        self.calistir = calistir          # (istek) -> {"is_id": ...} | {"hata": ...}
        self.bitti_mi = bitti_mi          # (is_id) -> True/False/None
        # (is_id) -> True: isin isci sureci HALA CANLI (panel yeniden baslatilmis olabilir).
        # Verilmezse cokme kurtarma eski (temkinsiz) davranisa duser.
        self.hala_calisiyor = hala_calisiyor
        self.politika = politika          # (oge, kuyruk) -> "devam" | "dur"
        self.es_zamanli = max(1, int(es_zamanli))
        self.yoklama_s = yoklama_s
        self.kilit = threading.RLock()
        self.durdur_bayragi = threading.Event()
        self._is_parcacigi = None
        self.veri = {"sema": SEMA, "duraklatildi": False, "ogeler": [], "sonraki_no": 1}
        self.son_yazma_hatasi = ""     # kalicilik hatalari GORUNUR olmali, yutulmaz
        self.yukleme_hatasi = ""
        self._yukle()

    # ------------------------------------------------------------------ kalicilik
    def _yukle(self) -> None:
        try:
            with open(self.yol, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("ogeler"), list):
                self.veri = {"sema": SEMA,
                             "duraklatildi": bool(d.get("duraklatildi")),
                             "ogeler": [o for o in d["ogeler"] if isinstance(o, dict)],
                             "sonraki_no": int(d.get("sonraki_no") or 1)}
        except FileNotFoundError:
            return                     # ilk calistirma: kuyruk yok, bu NORMAL
        except Exception as e:         # noqa: BLE001
            # BOZUK DOSYA SESSIZCE BOS KUYRUGA DONMEZ (denetim bulgusu 10). Eskiden
            # `return` ediliyordu: bozuk bir dosya "kuyruk bos" gibi gorunuyor ve ilk
            # yazimda UZERINE yazilarak veri KALICI olarak kayboluyordu.
            # Bozuk icerik KORUNUR (.bozuk-<zaman>) ve durum bildirilir.
            self.yukleme_hatasi = "kuyruk dosyasi OKUNAMADI: %s" % str(e)[:160]
            try:
                yedek = "%s.bozuk-%d" % (self.yol, int(_simdi()))
                os.replace(self.yol, yedek)
                self.yukleme_hatasi += " (bozuk dosya korundu: %s)" % os.path.basename(yedek)
            except OSError:
                pass
            return
        # COKME KURTARMA. Yarida kalan is YENIDEN KOSTURULMAZ (dosya yazmis olabilir) - ama
        # once "gercekten yarida mi kaldi" diye BAKARIZ (denetim bulgusu 6).
        #
        # NEDEN: ilk surum "kosuyor" olan HER ogeyi kosulsuz "yarim" isaretliyordu. Panel
        # yeniden baslatildiginda isci ALT SURECI olmemis olabilir (Windows'ta ebeveynin
        # olmesi cocugu oldurmez). O zaman kuyruk isi yarim sanip SIRADAKINI baslatiyor ve
        # ESKI isci hala AYNI projeye yaziyor: iki yazan, tek proje.
        for o in self.veri["ogeler"]:
            if o.get("durum") != "kosuyor":
                continue
            jid = o.get("is_id") or ""
            if jid and self.bitti_mi(jid):
                o["durum"] = "bitti"          # biz yokken bitmis
                o["bitti_t"] = _simdi()
                continue
            if jid and self.hala_calisiyor and self.hala_calisiyor(jid):
                # SAHIPSIZ ama CANLI: durumu "kosuyor" BIRAKIRIZ. `_sirdaki()` kosan is
                # varken yeni is baslatmaz - yani ikinci yazan olusmaz. Kullanici panelden
                # gorur ve karar verir.
                o["sahipsiz"] = True
                o["sebep"] = ("panel yeniden baslatildi ama bu isin isci sureci HALA "
                              "CALISIYOR - kuyruk yeni is baslatmiyor")
                continue
            o["durum"] = "yarim"
            o["sebep"] = "panel kapandi, is yarida kaldi - yeniden kosturulmadi"
            o["bitti_t"] = _simdi()

    def _yaz(self) -> str:
        """ATOMIK yaz: gecici dosya + replace. Doner: hata metni ('' = basarili).

        NEDEN DONUS DEGERI (denetim bulgusu 10): eski surum `except OSError: pass` diyordu.
        Disk doluysa, dosya salt-okunursa ya da kilitliyse kuyruk BELLEKTE degisiyor ama
        DISKE yazilmiyordu; panel yine "eklendi" diyordu. Panel kapaninca o isler yok
        oluyor ve kullanici sebebini goremiyordu. Artik hata YUKARI TASINIR.

        ATOMIK: once .gecici'ye yazilir, sonra os.replace. Yazim yarida kalirsa ONCEKI
        GECERLI dosya yerinde kalir - yarim JSON birakmak kuyrugu bastan silerdi."""
        gec = self.yol + ".gecici"
        try:
            os.makedirs(os.path.dirname(self.yol) or ".", exist_ok=True)
            with open(gec, "w", encoding="utf-8", newline="\n") as f:
                json.dump(self.veri, f, ensure_ascii=False, indent=1)
            os.replace(gec, self.yol)
            self.son_yazma_hatasi = ""
            return ""
        except (OSError, TypeError, ValueError) as e:
            self.son_yazma_hatasi = "kuyruk diske YAZILAMADI: %s" % str(e)[:160]
            try:                       # yarim gecici dosya birakma
                if os.path.exists(gec):
                    os.remove(gec)
            except OSError:
                pass
            return self.son_yazma_hatasi

    # ------------------------------------------------------------------ islemler
    def ekle(self, istek: dict, baslik: str = "") -> dict:
        with self.kilit:
            no = self.veri["sonraki_no"]
            self.veri["sonraki_no"] = no + 1
            oge = {"no": no, "durum": "bekliyor",
                   "baslik": (baslik or " ".join(str(istek.get("gorev") or "").split()[:6])[:48]
                              or "isim yok"),
                   "istek": istek, "eklendi_t": _simdi(),
                   "is_id": "", "basladi_t": 0, "bitti_t": 0, "sebep": ""}
            self.veri["ogeler"].append(oge)
            hata = self._yaz()
            if hata:
                # DISKE YAZILAMADIYSA "eklendi" DEMEYIZ: bellekteki oge panel kapaninca
                # yok olur ve kullanici sebebini goremez. Ogeyi geri alip hata doneriz.
                self.veri["ogeler"].remove(oge)
                self.veri["sonraki_no"] = no
                return {"hata": hata}
            return dict(oge)

    def sil(self, no: int) -> dict:
        """BEKLEYEN ogeyi kuyruktan cikar. KOSAN oge silinmez - once durdurulmali."""
        with self.kilit:
            for o in self.veri["ogeler"]:
                if o.get("no") == no:
                    if o.get("durum") == "kosuyor":
                        return {"hata": "bu is KOSUYOR - kuyruktan silinemez"}
                    o["durum"] = "iptal"
                    o["bitti_t"] = _simdi()
                    hata = self._yaz()
                    return {"hata": hata} if hata else {"ok": True, "no": no}
        return {"hata": "oge bulunamadi: %s" % no}

    def tasi(self, no: int, yon: int) -> dict:
        """BEKLEYEN ogeyi sirada yukari/asagi tasi. Kosan/bitmis ogeler yerinde kalir."""
        with self.kilit:
            bekleyen = [i for i, o in enumerate(self.veri["ogeler"])
                        if o.get("durum") == "bekliyor"]
            yerler = {self.veri["ogeler"][i]["no"]: k for k, i in enumerate(bekleyen)}
            if no not in yerler:
                return {"hata": "yalnizca BEKLEYEN oge tasinabilir"}
            k = yerler[no]
            h = k + (1 if yon > 0 else -1)
            if h < 0 or h >= len(bekleyen):
                return {"ok": True, "no": no}         # ucta: sessizce yerinde kalir
            i, j = bekleyen[k], bekleyen[h]
            ogeler = self.veri["ogeler"]
            ogeler[i], ogeler[j] = ogeler[j], ogeler[i]
            hata = self._yaz()
            return {"hata": hata} if hata else {"ok": True, "no": no}

    def duraklat(self, deger: bool = True) -> dict:
        with self.kilit:
            self.veri["duraklatildi"] = bool(deger)
            if not deger:
                self.veri.pop("durma_sebebi", None)   # surduruldu: eski sebep bayat
            hata = self._yaz()
            if hata:
                return {"hata": hata}
            return {"ok": True, "duraklatildi": self.veri["duraklatildi"]}

    def temizle(self) -> dict:
        """Bitmis/iptal/hata/yarim ogeleri listeden dusur. Kosan ve bekleyen kalir."""
        with self.kilit:
            once = len(self.veri["ogeler"])
            self.veri["ogeler"] = [o for o in self.veri["ogeler"]
                                   if o.get("durum") in ("bekliyor", "kosuyor")]
            hata = self._yaz()
            if hata:
                return {"hata": hata}
            return {"ok": True, "silinen": once - len(self.veri["ogeler"])}

    def liste(self) -> dict:
        with self.kilit:
            ogeler = [dict(o) for o in self.veri["ogeler"]]
        sayim = {d: sum(1 for o in ogeler if o.get("durum") == d) for d in DURUMLAR}
        return {"sema": SEMA, "duraklatildi": self.veri["duraklatildi"],
                "durma_sebebi": self.veri.get("durma_sebebi") or None,
                "kalicilik_hatasi": self.son_yazma_hatasi or self.yukleme_hatasi or None,
                "ogeler": ogeler, "sayim": sayim,
                "calisiyor": bool(self._is_parcacigi and self._is_parcacigi.is_alive())}

    # ------------------------------------------------------------------ surucu
    def _sirdaki(self) -> dict | None:
        with self.kilit:
            if self.veri["duraklatildi"]:
                return None
            if sum(1 for o in self.veri["ogeler"] if o.get("durum") == "kosuyor") >= self.es_zamanli:
                return None
            for o in self.veri["ogeler"]:
                if o.get("durum") == "bekliyor":
                    return o
        return None

    def adim(self) -> str:
        """Kuyrugu BIR adim ilerlet. Doner: ne yapildi ('bosta'|'baslatildi'|'bitti'|...).

        Test edilebilirlik icin ayri: dongu yerine tek adim cagirilarak sira, duraklatma,
        politika ve hata yollari zamanlamaya bagli olmadan sinanir."""
        # 1) kosanlar bitti mi?
        with self.kilit:
            kosanlar = [o for o in self.veri["ogeler"] if o.get("durum") == "kosuyor"]
        for o in kosanlar:
            bitti = self.bitti_mi(o.get("is_id") or "")
            if bitti:
                with self.kilit:
                    o["durum"] = "bitti"
                    o["bitti_t"] = _simdi()
                    self._yaz()
                self._politika_uygula(o)
                return "bitti"
        if kosanlar:
            return "bekleniyor"
        # 2) sirdakini baslat
        oge = self._sirdaki()
        if oge is None:
            return "bosta"
        with self.kilit:
            oge["durum"] = "kosuyor"
            oge["basladi_t"] = _simdi()
            self._yaz()
        try:
            r = self.calistir(dict(oge["istek"])) or {}
        except Exception as e:            # noqa: BLE001
            r = {"hata": str(e)[:200]}
        with self.kilit:
            if r.get("hata") or not r.get("is_id"):
                oge["durum"] = "hata"
                oge["sebep"] = str(r.get("hata") or "is baslatilamadi")[:200]
                oge["bitti_t"] = _simdi()
                self._yaz()
                bitti_oge = dict(oge)
            else:
                oge["is_id"] = r["is_id"]
                oge["klasor"] = r.get("klasor", "")
                self._yaz()
                bitti_oge = None
        if bitti_oge:
            self._politika_uygula(bitti_oge)
            return "hata"
        return "baslatildi"

    def _politika_uygula(self, oge: dict) -> None:
        """Politika 'dur' derse kuyruk DURAKLATILIR - sessizce devam edilmez.

        Gozetimsiz kosuda asil risk 'bir is kaldi' degil, 'bir is kaldi ve kuyruk ayni
        hatayi 12 kez tekrarladi'dir. Politikanin gorevi bu zinciri kesmek."""
        if not self.politika:
            return
        try:
            karar = self.politika(dict(oge), self) or "devam"
            hata = ""
        except Exception as e:            # noqa: BLE001
            # POLITIKA PATLARSA DURURUZ (denetim bulgusu 3). Eski surum sessizce `return`
            # ediyordu: koruma katmani coktugu halde kuyruk devam ediyordu - yani en cok
            # korumaya ihtiyac duyulan anda koruma YOKTU ve kimse bilmiyordu.
            karar, hata = "dur", "politika degerlendirmesi PATLADI: %s: %s" % (
                type(e).__name__, str(e)[:160])
        if karar == "dur":
            with self.kilit:
                self.veri["duraklatildi"] = True
                oge_ref = next((o for o in self.veri["ogeler"]
                                if o.get("no") == oge.get("no")), None)
                sebep = hata or getattr(self.politika, "son_sebep", "") or "politika kuyrugu durdurdu"
                if oge_ref is not None and not oge_ref.get("sebep"):
                    oge_ref["sebep"] = sebep
                # KUYRUK DUZEYINDE de sakla: durduran oge "bitti" gorunuyor olabilir ve
                # panel yalnizca hatali ogelerin sebebine bakiyordu - kullanici kuyrugun
                # NEDEN durdugunu goremiyordu.
                self.veri["durma_sebebi"] = {"no": oge.get("no"), "is_id": oge.get("is_id"),
                                             "baslik": oge.get("baslik"), "sebep": sebep,
                                             "t": _simdi()}
                self._yaz()

    def _dongu(self) -> None:
        while not self.durdur_bayragi.is_set():
            try:
                ne = self.adim()
            except Exception:             # noqa: BLE001 - surucu ASLA olmemeli
                ne = "bosta"
            self.durdur_bayragi.wait(0.1 if ne == "baslatildi" else self.yoklama_s)

    def basla(self) -> None:
        if self._is_parcacigi and self._is_parcacigi.is_alive():
            return
        self.durdur_bayragi.clear()
        self._is_parcacigi = threading.Thread(target=self._dongu, daemon=True,
                                              name="apprentice-kuyruk")
        self._is_parcacigi.start()

    def dur(self) -> None:
        self.durdur_bayragi.set()

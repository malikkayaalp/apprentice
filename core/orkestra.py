"""ORKESTRA: cok dosyali isi DUGUMLERE bolup her dugumu TAZE baglamla kosturur.

ANA FIKIR (ve kurucu olcume dayanagi): bugun bir `worker_run` butun gorevi TEK yorungede
tasiyor - her onarim turunda sohbet birikiyor. Olculdu: oturum surekliligi +%59 token ve
KALITE DUSUK. Yani biriken baglam yalniz pahali degil, ZARARLI.

Burada her dugum kendi TAZE baglamiyla kosar:
    dugum = en kucuk DOGRULANABILIR birim (bir dosya + onun kabul kontrolu + kendi
            yazma kapsami)

ORKESTRASYON KODDA, MODEL DEGIL. Bu projenin kurucu olcumu: isci ham olcumu kendi
yorumlayip duzeltmeye kalkinca YAKINSAMADI; ozetlenmis kanitla 2 turda cozdu. Bu yuzden
"bitti mi" sorusuna model degil DOGRULAYICI cevap verir, siradaki dugume kod karar verir.

PLAN DOGRULAMASI DETERMINISTIK: kotu plan KOSMADAN yakalanir - her dugumun calistirabilir
bir kabul kontrolu var mi, yazma kapsamlari AYRIK mi, bagimlilik dongusu var mi.

NOT: bu ilk surum PLANI URETMEZ, VERILEN plani kosar. Sebep: "boler miyiz" ile "bolmek
ise yariyor mu" AYRI sorular. Once ikincisi tek degiskenli olculur (ayni gorev, ayni
model, elle yazilmis ayni plan), sonra plan uretimi konusulur.
"""
from __future__ import annotations
import json, os, time

SEMA = 1


class PlanHatasi(ValueError):
    """Plan KOSMADAN reddedildi - sebebi mesajda."""


def dugum(ad: str, gorev: str, yazilabilir: list, kriterler: list | None = None,
          bagimli: list | None = None) -> dict:
    return {"ad": ad, "gorev": gorev, "yazilabilir": list(yazilabilir),
            "kriterler": list(kriterler or []), "bagimli": list(bagimli or [])}


def plan_dogrula(plan: list) -> list:
    """Plani KOSMADAN denetle. Doner: hata mesajlari (bos = gecerli).

    Kotu plan, kotu kod uretmekten pahalidir: model calisir, token yanar, sonuc cope
    gider. Bu yuzden denetim ONCE ve DETERMINISTIK."""
    hatalar = []
    if not plan:
        return ["plan bos"]
    adlar = [d.get("ad") for d in plan]
    for ad in set(adlar):
        if adlar.count(ad) > 1:
            hatalar.append("dugum adi tekrarliyor: %s" % ad)
    for d in plan:
        if not d.get("ad"):
            hatalar.append("adsiz dugum")
        if not str(d.get("gorev") or "").strip():
            hatalar.append("%s: gorev bos" % d.get("ad"))
        if not d.get("yazilabilir"):
            # KAPSAMSIZ dugum, butun calisma alanina yazabilir demektir - o zaman
            # dugumler birbirinin isini bozabilir ve paralellik imkansizlasir.
            hatalar.append("%s: yazma kapsami bos (dugum kapsamsiz kosamaz)" % d.get("ad"))
        for b in d.get("bagimli") or []:
            if b not in adlar:
                hatalar.append("%s: olmayan dugume bagimli (%s)" % (d.get("ad"), b))
    # yazma kapsamlari AYRIK olmali: iki dugum ayni dosyaya yazarsa sonuc sirayla degisir
    sahip: dict = {}
    for d in plan:
        for y in d.get("yazilabilir") or []:
            n = str(y).replace("\\", "/").strip("/")
            if n in sahip:
                hatalar.append("yazma kapsami cakisiyor: %s -> %s ve %s"
                               % (n, sahip[n], d.get("ad")))
            sahip[n] = d.get("ad")
    hatalar.extend(_dongu_bul(plan, adlar))
    return hatalar


def _dongu_bul(plan: list, adlar: list) -> list:
    durum = {ad: 0 for ad in adlar}          # 0 goruilmedi, 1 yolda, 2 bitti
    kenar = {d["ad"]: list(d.get("bagimli") or []) for d in plan if d.get("ad")}
    bulunan = []

    def gez(ad, yol):
        if durum.get(ad) == 1:
            bulunan.append("bagimlilik dongusu: %s" % " -> ".join(yol + [ad]))
            return
        if durum.get(ad) == 2:
            return
        durum[ad] = 1
        for b in kenar.get(ad, []):
            gez(b, yol + [ad])
        durum[ad] = 2

    for ad in adlar:
        gez(ad, [])
    return bulunan


def sirala(plan: list) -> list:
    """Bagimliliga gore kosum sirasi (topolojik). Plan dogrulanmis olmali."""
    kalan = {d["ad"]: set(d.get("bagimli") or []) for d in plan}
    haritada = {d["ad"]: d for d in plan}
    out = []
    while kalan:
        hazir = sorted(a for a, b in kalan.items() if not (b - {x["ad"] for x in out}))
        if not hazir:
            raise PlanHatasi("plan siralanamadi (dongu?)")
        for a in hazir:
            out.append(haritada[a])
            del kalan[a]
    return out


def kos(plan: list, calistir, kok: str = "", oturum_oneki: str = "") -> dict:
    """Plani kostur. `calistir(dugum, indeks)` -> worker_run raporu (dict).

    TAZE BAGLAM: her dugum AYRI is olarak kosar, oturum PAYLASILMAZ. Biriken sohbet
    ölçüldü: +%59 token ve kalite dusuk. Dugumler arasi bilgi yalniz DOGRULANMIS
    ciktilarla tasinir (dosyalar diskte), sohbet gecmisiyle degil.

    Bir dugum kalirsa ONA BAGIMLI olanlar ATLANIR - yarim temel uzerine insa etmeyiz.
    Atlananlar rapora yazilir; sessiz kirpma yok."""
    hatalar = plan_dogrula(plan)
    if hatalar:
        raise PlanHatasi("; ".join(hatalar[:5]))
    t0 = time.time()
    sonuclar, basarisiz = [], set()
    for i, d in enumerate(sirala(plan)):
        engel = sorted(set(d.get("bagimli") or []) & basarisiz)
        if engel:
            sonuclar.append({"ad": d["ad"], "durum": "atlandi",
                             "sebep": "bagimli oldugu dugum kaldi: %s" % ", ".join(engel)})
            basarisiz.add(d["ad"])
            continue
        try:
            rap = calistir(d, i) or {}
        except Exception as e:  # noqa: BLE001
            rap = {"hata": str(e)[:200]}
        gecti = bool(rap.get("derleme_durumu") == "derlendi" and not rap.get("hatalar"))
        if rap.get("hata"):
            gecti = False
        if not gecti:
            basarisiz.add(d["ad"])
        sonuclar.append({"ad": d["ad"], "durum": "gecti" if gecti else "kaldi",
                         "is_id": rap.get("is_id"), "sure": rap.get("sure"),
                         "kullanim": rap.get("kullanim") or {},
                         "hatalar": (rap.get("hatalar") or [])[:3],
                         "hata": rap.get("hata", "")})
    k = {"prompt_tokens": 0, "gen_tokens": 0}
    for s in sonuclar:
        for alan in k:
            k[alan] += (s.get("kullanim") or {}).get(alan) or 0
    return {"sema": SEMA, "dugum": len(plan),
            "gecti": sum(1 for s in sonuclar if s["durum"] == "gecti"),
            "kaldi": sum(1 for s in sonuclar if s["durum"] == "kaldi"),
            "atlandi": sum(1 for s in sonuclar if s["durum"] == "atlandi"),
            "sure": round(time.time() - t0, 1), "kullanim": k, "dugumler": sonuclar,
            "kok": kok, "oturum_oneki": oturum_oneki}


def plan_yukle(yol: str) -> list:
    with open(yol, encoding="utf-8") as f:
        veri = json.load(f)
    plan = veri.get("plan") if isinstance(veri, dict) else veri
    if not isinstance(plan, list):
        raise PlanHatasi("plan listesi bulunamadi: %s" % os.path.basename(yol))
    return [dugum(d.get("ad", ""), d.get("gorev", ""), d.get("yazilabilir") or [],
                  d.get("kriterler"), d.get("bagimli")) for d in plan]

"""ORKESTRA testi (core/orkestra.py).

Cakilan sozlesme uc madde:
  1. KOTU PLAN KOSMADAN reddedilir. Kotu plan, kotu koddan pahalidir: model calisir,
     token yanar, sonuc cope gider.
  2. TAZE BAGLAM: her dugum ayri is, oturum PAYLASILMAZ (olculdu: oturum surekliligi
     +%59 token ve kalite dusuk).
  3. DUSEN DUGUME BAGIMLI olanlar ATLANIR ve bu RAPORLANIR - yarim temel uzerine insa
     etmeyiz, sessiz kirpma da yapmayiz.
"""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core.orkestra import (PlanHatasi, dugum, kos, plan_dogrula,  # noqa: E402
                           plan_yukle, sirala)


def _plan():
    return [dugum("kdv", "KDV hesapla", ["kdv.py"], ["oran 20 olmali"]),
            dugum("sepet", "sepeti topla", ["sepet.py"], ["bos sepet 0"], ["kdv"]),
            dugum("rapor", "rapor yaz", ["rapor.py"], [], ["sepet", "kdv"])]


def _sahte(gecmeyen=()):
    def calistir(d, i):
        if d["ad"] in gecmeyen:
            return {"derleme_durumu": "derleme_hatasi", "hatalar": ["patladi"],
                    "is_id": "is_" + d["ad"], "kullanim": {"prompt_tokens": 100, "gen_tokens": 10}}
        return {"derleme_durumu": "derlendi", "hatalar": [], "is_id": "is_" + d["ad"],
                "sure": 1.0, "kullanim": {"prompt_tokens": 100, "gen_tokens": 10}}
    return calistir


def kotu_plan_kosmaz() -> bool:
    """Gecersiz plan KOSMADAN reddedilir; sebep MESAJDA olur."""
    assert plan_dogrula(_plan()) == [], plan_dogrula(_plan())
    assert plan_dogrula([]) == ["plan bos"]

    # ayni dosyaya iki dugum yazamaz - yoksa sonuc kosum sirasina gore degisir
    cak = [dugum("a", "x", ["ayni.py"]), dugum("b", "y", ["ayni.py"])]
    assert any("cakisiyor" in h for h in plan_dogrula(cak)), plan_dogrula(cak)

    # kapsamsiz dugum: butun calisma alanina yazabilir demektir
    assert any("kapsam" in h for h in plan_dogrula([dugum("a", "x", [])]))
    # gorevi bos dugum
    assert any("gorev bos" in h for h in plan_dogrula([dugum("a", "  ", ["a.py"])]))
    # olmayan dugume bagimlilik
    assert any("olmayan" in h for h in plan_dogrula([dugum("a", "x", ["a.py"], [], ["yok"])]))
    # ad tekrari
    iki = [dugum("a", "x", ["a.py"]), dugum("a", "y", ["b.py"])]
    assert any("tekrarliyor" in h for h in plan_dogrula(iki))
    # dongu
    dongu = [dugum("a", "x", ["a.py"], [], ["b"]), dugum("b", "y", ["b.py"], [], ["a"])]
    assert any("dongu" in h for h in plan_dogrula(dongu)), plan_dogrula(dongu)

    # kos() gecersiz plani KOSTURMAZ - calistir HIC cagrilmamali
    cagri = []
    try:
        kos(cak, lambda d, i: cagri.append(d) or {})
        raise AssertionError("gecersiz plan kosturuldu")
    except PlanHatasi:
        pass
    assert not cagri, "gecersiz planda dugum kosturuldu"
    print("kotu plan kosmaz: ok (7 gecersiz plan, hicbiri kosturulmadi)")
    return True


def sira_ve_atlama() -> bool:
    """Topolojik sira dogru; dusen dugume BAGIMLI olanlar ATLANIR ve raporlanir."""
    assert [d["ad"] for d in sirala(_plan())] == ["kdv", "sepet", "rapor"]

    r = kos(_plan(), _sahte())
    assert (r["gecti"], r["kaldi"], r["atlandi"]) == (3, 0, 0), r
    assert r["kullanim"]["prompt_tokens"] == 300, r["kullanim"]

    # ilk dugum duserse ONA BAGIMLI olanlar kosmaz
    r2 = kos(_plan(), _sahte(gecmeyen={"kdv"}))
    durum = {s["ad"]: s["durum"] for s in r2["dugumler"]}
    assert durum == {"kdv": "kaldi", "sepet": "atlandi", "rapor": "atlandi"}, durum
    assert (r2["gecti"], r2["kaldi"], r2["atlandi"]) == (0, 1, 2), r2
    atl = [s for s in r2["dugumler"] if s["durum"] == "atlandi"][0]
    assert "kdv" in atl["sebep"], "atlama SEBEBI yazilmamis: %s" % atl
    # atlanan dugum icin token YANMAZ
    assert r2["kullanim"]["prompt_tokens"] == 100, r2["kullanim"]

    # BAGIMSIZ dugum, baskasi duse de kosar
    p = [dugum("a", "x", ["a.py"]), dugum("b", "y", ["b.py"])]
    r3 = kos(p, _sahte(gecmeyen={"a"}))
    durum3 = {s["ad"]: s["durum"] for s in r3["dugumler"]}
    assert durum3 == {"a": "kaldi", "b": "gecti"}, durum3
    print("sira ve atlama: ok (topolojik sira, bagimli atlandi, bagimsiz kostu)")
    return True


def taze_baglam() -> bool:
    """Her dugum AYRI is: oturum paylasilmaz, dugume yalniz KENDI kapsami verilir."""
    gorulen = []

    def calistir(d, i):
        gorulen.append({"ad": d["ad"], "yazilabilir": list(d["yazilabilir"]),
                        "gorev": d["gorev"]})
        return {"derleme_durumu": "derlendi", "hatalar": [], "is_id": "is%d" % i,
                "kullanim": {}}

    kos(_plan(), calistir)
    assert len(gorulen) == 3, gorulen
    # her dugum YALNIZ kendi dosyasini yazabilir - kapsam sizmiyor
    assert gorulen[0]["yazilabilir"] == ["kdv.py"], gorulen[0]
    assert gorulen[1]["yazilabilir"] == ["sepet.py"], gorulen[1]
    # gorev metinleri birbirine karismiyor (baglam BIRIKMIYOR)
    assert "KDV" in gorulen[0]["gorev"] and "KDV" not in gorulen[1]["gorev"], gorulen

    # calistir PATLARSA orkestra patlamaz, dugum "kaldi" sayilir
    def patlak(d, i):
        raise RuntimeError("baglanti koptu")
    r = kos([dugum("a", "x", ["a.py"])], patlak)
    assert r["kaldi"] == 1 and "baglanti koptu" in r["dugumler"][0]["hata"], r
    print("taze baglam: ok (kapsam sizmiyor, gorev karismiyor, istisna yutuluyor)")
    return True


def plan_dosyadan() -> bool:
    """Plan dosyadan okunabilmeli (elle yazilan plan A/B icin gerekli)."""
    d = tempfile.mkdtemp()
    yol = os.path.join(d, "plan.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"plan": [{"ad": "a", "gorev": "x", "yazilabilir": ["a.py"],
                             "kriterler": ["k"], "bagimli": []}]}, f)
    p = plan_yukle(yol)
    assert len(p) == 1 and p[0]["ad"] == "a" and p[0]["kriterler"] == ["k"], p
    assert plan_dogrula(p) == []
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"yanlis": 1}, f)
    try:
        plan_yukle(yol)
        raise AssertionError("bozuk plan kabul edildi")
    except PlanHatasi:
        pass
    print("plan dosyadan: ok")
    return True


def main() -> int:
    ok = kotu_plan_kosmaz() and sira_ve_atlama() and taze_baglam() and plan_dosyadan()
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

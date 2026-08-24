"""Kurulum penceresi (kur_gui) duman testi - Ollama/model GEREKMEZ.

    python tests/test_kurulum_gui.py

Neden var: "Kur" dugmesi iki kez kirpildi ("K", sonra "Kı") - alt bara dugme eklendikce
tkinter EN SON paketleneni daraltiyor. Goz kararina birakilamaz; burada dugmelerin
ISTENEN genisligi ile GERCEK genisligi olculur.

Kapsam:
  1. Pencere kuruluyor mu (import + Sihirbaz() + update)
  2. Alt bardaki dugmelerin hicbiri KIRPILMIYOR (gercek genislik >= istenen genislik)
  3. Adim listesi (ADIMLAR) ile _kur() icinde koslanan adimlar ORTUSUYOR - ortusmezse
     "kurulum tamam" kontrolu hep False doner ve ozet penceresi hic acilmaz (yasandi riski)
  4. Cokme gunlugu kancasi bagli (sessiz cokme yok)
"""
from __future__ import annotations
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        print("tkinter yok, atlaniyor:", e)
        print("SONUC: GECTI")
        return 0

    import kur_gui

    # 3) ADIMLAR <-> _kur() ortusmesi (kaynak metinden okunur - GUI kosmadan)
    with open(os.path.join(ROOT, "kur_gui.py"), encoding="utf-8") as f:
        kaynak = f.read()
    adim_anahtarlari = {k for k, _ in kur_gui.ADIMLAR}
    kosulan = set(re.findall(r'calistir\("(\w+)"', kaynak)) | \
        set(re.findall(r'sonuc\["(\w+)"\]\s*=', kaynak))
    eksik = adim_anahtarlari - kosulan
    assert not eksik, ("ADIMLAR'da olup _kur()'da HIC yazilmayan adim var: %s "
                       "-> 'kurulum tamam' kontrolu hep False doner" % eksik)
    fazla = kosulan - adim_anahtarlari - {"dosyalar"}
    assert not fazla, "_kur() ADIMLAR'da olmayan adim yaziyor: %s" % fazla
    print("adim listesi <-> kurulum akisi: ok (%d adim)" % len(adim_anahtarlari))

    assert "sys.excepthook = _cokme_gunlugu" in kaynak, "cokme gunlugu kancasi yok"
    print("cokme gunlugu kancasi: ok")

    # 1-2) pencereyi kur, olc
    app = kur_gui.Sihirbaz()
    try:
        # EN KOTU DURUM: pencerenin izin verilen EN KUCUK boyutu. Varsayilan boyutta sigan
        # duzen, kullanici pencereyi kucultunce kirpilabiliyordu (yasandi: "Kur" -> "Kı").
        en_kucuk = app.minsize()
        app.geometry("%dx%d" % (en_kucuk[0], en_kucuk[1]))
        app.update_idletasks()
        app.update()
        # OLCUM (kanitlandi): pack alani yetmeyince ttk dugmesi genisligi 1 PIKSELE coker -
        # "Kur" ekranda "Kı" gorunuyordu. Metrik: gercek genislik << istenen genislik.
        def kirpilanlar():
            out = []
            for ad in ("btn_kur", "btn_kapat", "btn_kural", "btn_panel"):
                b = getattr(app, ad, None)
                if b is None:
                    continue
                if b.winfo_width() < b.winfo_reqwidth() - 2:
                    out.append("%s (%r): %d px yerine %d px" %
                               (ad, b["text"], b.winfo_width(), b.winfo_reqwidth()))
            return out

        k = kirpilanlar()
        assert not k, "EN KUCUK boyutta kirpilan dugme: " + "; ".join(k)

        # YAPISAL GUVENCE: alt barin istedigi genislik, izin verilen en kucuk pencereden
        # KUCUK olmali - yoksa kullanici pencereyi kucultunce dugme kaybolur.
        alt_bar = app.btn_kur.master
        gerek = alt_bar.winfo_reqwidth()
        assert gerek <= en_kucuk[0] - 20,             ("alt bar %d px istiyor, pencere en fazla %d px kuculebiliyor - dugme kirpilir "
             "(uzun etiket ya da fazla dugme var)" % (gerek, en_kucuk[0]))

        # STRES: pencere zorla daraltilirsa ONCE SOL dugmeler kirpilmali, "Kur"/"Kapat" ASLA
        app.geometry("640x600")
        app.update_idletasks(); app.update()
        onemli = [x for x in kirpilanlar() if x.startswith(("btn_kur", "btn_kapat"))]
        assert not onemli, "640 px'te ana dugmeler kirpildi: " + "; ".join(onemli)
        print("alt bar: ok (istenen %d px <= en kucuk %d px; 640 px'te Kur/Kapat saglam)"
              % (gerek, en_kucuk[0]))
    finally:
        try:
            app.destroy()
        except Exception:
            pass
    print("SONUC: GECTI")
    return 0


if __name__ == "__main__":
    sys.exit(main())

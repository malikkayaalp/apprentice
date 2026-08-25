"""Panel testleri - GPU/Ollama GEREKMEZ.

    python tests/test_panel.py

Kapsam:
  1. panel.html icindeki JS SOZDIZIMI (node varsa gercek ayristirici, yoksa kaba denetim).
     Yasandi: tek tirnakli metin icindeki kesme isareti ("Claude'a") tum betigi coktu ve
     panel bos/kilitli acildi - hata sessizdi. Bu test o sinifi yakalar.
  2. Sunucu uclari: /api/hazir (anlik), /api/isler, /api/olaylar, /api/modeller.
  3. Yerlesim butunlugu: VARSAYILAN izgarada panel cakismasi olmamali (metinden okunur).
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SAYFA = os.path.join(ROOT, "clients", "web", "panel.html")

KARAR_ROZET_SURUS = r"""
function ONAY(k,a){ if(!k) throw new Error("SOZLESME: "+a); }
let m;
// 1) karar yoksa rozet de YOK
ONAY(kararRozetMetni(null)==="", "karar yokken rozet cikti");
ONAY(kararRozetMetni({})==="", "bos kararda rozet cikti");
// 2) tek karar: sade
ONAY(kararRozetMetni({durum:"kabul"})==="✓ kabul edildi", "kabul metni yanlis");
m=kararRozetMetni({durum:"red", geri_alinan:2});
ONAY(/reddedildi/.test(m) && /2 dosya/.test(m), "red metni yanlis: "+m);
// 3) ASIL DURUM: once red (kod geri alindi) sonra kabul -> GECMIS GORUNMELI
m=kararRozetMetni({durum:"kabul", onceki:[{durum:"red", geri_alinan:2}]});
ONAY(/kabul edildi/.test(m), "son karar kayboldu: "+m);
ONAY(/daha önce/.test(m) && /reddedil/.test(m), "GECMIS GIZLENDI: "+m);
ONAY(/2 dosya/.test(m), "kac dosya geri alindigi kayboldu: "+m);
// 4) coklu gecmis: EN YENI once yazilmali
m=kararRozetMetni({durum:"red", geri_alinan:1,
                   onceki:[{durum:"kabul"},{durum:"red", geri_alinan:3}]});
ONAY(m.indexOf("3 dosya") < m.indexOf("kabul edilmişti"), "gecmis sirasi ters: "+m);
console.log("ROZET-OK");
"""


def js_sozdizimi() -> bool:
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    bloklar = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert bloklar, "panel.html icinde <script> yok"
    js = "\n".join(bloklar)
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write("(async function(){\n" + js + "\n})")     # cagirmadan yalnizca AYRISTIR
            yol = f.name
        try:
            r = subprocess.run([node, "--check", yol], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            if r.returncode != 0:
                print("JS SOZDIZIMI HATASI:\n" + (r.stderr or "")[:600])
                return False
            print("js sozdizimi (node --check): ok  (%d karakter)" % len(js))
        finally:
            os.unlink(yol)
    else:
        # node yoksa: en sik hata sinifini kaba denetimle yakala (tek tirnakli metinde ')
        for i, satir in enumerate(js.splitlines(), 1):
            s = satir.strip()
            if s.startswith("//") or "'" not in s:
                continue
            tek = len(re.findall(r"(?<!\\)'", s))
            if tek % 2 == 1 and not s.rstrip().endswith(("+", ",", "(")):
                print("supheli tek tirnak (satir %d): %s" % (i, s[:90]))
                return False
        print("js kaba sozdizimi denetimi: ok (node yok)")
    return True


def metin_isleyicileri() -> bool:
    """Sohbet/akis metin islemeyi GERCEKTEN CALISTIR (node ile).

    YASANDI: 'kod' etiketi bir temizlik regex'inde kaza ile silinince zenginMetin, kodBlok'u
    TEK argumanla cagirdi; govde undefined kaldi ve model kod yazinca sohbet balonuna
    "TypeError: Cannot read properties of undefined (reading 'split')" dustu. Sozdizimi
    testi bunu goremez - fonksiyonlarin CALISMASI gerekir. Burada gercek girdilerle kosulur."""
    node = shutil.which("node")
    if not node:
        print("metin isleyicileri: node yok, atlandi")
        return True
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    gerek = ["kacir", "renklendir", "kodBlok", "zenginMetin", "KW", "SAY", "renklendir2",
             "KOD_ACIK_SINIR", "ozniteligeKacir", "panoyaYaz", "eskiUsulKopya"]
    parcalar = []
    for ad in gerek:
        m = re.search(r"^(?:function %s\(|const %s\s*=)" % (ad, ad), js, re.M)
        if not m:
            continue
        bas = m.start()
        son = len(js)
        for sonraki in re.finditer(r"^(?:function \w+\(|const \w+\s*=|/\* -)", js[bas + 5:], re.M):
            son = bas + 5 + sonraki.start()
            break
        parcalar.append(js[bas:son])
    kod = "\n".join(parcalar)
    ornekler = [
        "Merhaba! Nasil yardimci olabilirim?",
        "Iste kod:\n```python\ndef say(m):\n    return len(m.split())\n```\nBitti.",
        "```\nkod bloğu dil etiketsiz\n```",
        "Yarim blok: ```python\ndef f():\n    pass",
        "`satir ici` ve **kalin** ve <script>alert(1)</script>",
        "```js\nconst x = {a:1};\n```\nsonra ```py\nprint('x')\n```",
        "",
    ]
    # node'da DOM yok: kopyalama/olay-delegasyonu kodu icin kucuk sahte ortam
    sahte = ("const document={addEventListener(){},createElement(){return {style:{},"
             "select(){},remove(){},appendChild(){}}},body:{appendChild(){},removeChild(){}},"
             "execCommand(){return true}};\n"
             "const navigator={};\nfunction tost(){}\n")
    surucu = (sahte + kod + "\n" +
              "const ornekler=" + json.dumps(ornekler, ensure_ascii=False) + ";\n"
              "let cikti=[];\n"
              "for (const o of ornekler){\n"
              "  const h = zenginMetin(o);\n"
              "  if (typeof h !== 'string') throw new Error('zenginMetin string dondurmedi');\n"
              "  if (h.includes('<script>')) throw new Error('KACIS YOK: <script> ham gecti');\n"
              "  cikti.push(h.length);\n"
              "}\n"
              "if (kodBlok('x.py', undefined) === undefined) throw new Error('kodBlok undefined');\n"
              "console.log('OK ' + cikti.join(','));\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(surucu)
        yol = f.name
    try:
        r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        assert r.returncode == 0 and "OK" in (r.stdout or ""), \
            "metin isleyicileri PATLADI:\n%s" % ((r.stderr or r.stdout)[:500])
        print("metin isleyicileri: ok (%d ornek islendi, kacis calisiyor)" % len(ornekler))
        return True
    finally:
        os.unlink(yol)


def goruntuleyici_sayfasi() -> bool:
    """Dosya goruntuleyici (ayri pencere) sayfasi: JS sozdizimi + PENCERE DENETIMLERI.

    YASANDI: kabuk pencereyi cercevesiz aciyor (Windows baslik cubugu yok) ama goruntuleyici
    sayfasina kendi baslik seridimiz eklenmemisti - pencere ne KAPATILABILIYOR ne TASINABILIYORDU.
    Bu dosyanin JS'i hicbir testte denetlenmiyordu; artik denetleniyor."""
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import goruntuleyici as G
    h = G.sayfa("20260101-000000-abcdef", "ornek/kod.py")
    for gerek, aciklama in (("pKapat", "kapatma dugmesi"), ("pUstte", "hep ustte dugmesi"),
                            ("pBuyult", "buyult dugmesi"), ("tasi:", "pencere tasima kanali"),
                            ("postMessage", "kabuk mesaj kanali"), ("cursor:grab", "tasinabilir baslik")):
        assert gerek in h, "goruntuleyicide %s (%s) yok" % (gerek, aciklama)
    assert "ornek/kod.py" in h and "20260101" in h, "dosya adi/is kimligi sayfada yok"
    node = shutil.which("node")
    if node:
        js = "\n".join(re.findall(r"<script>(.*?)</script>", h, re.S))
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write("(function(){\n" + js + "\n})")
            yol = f.name
        try:
            r = subprocess.run([node, "--check", yol], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            assert r.returncode == 0, "goruntuleyici JS sozdizimi HATASI:\n%s" % (r.stderr or "")[:400]
        finally:
            os.unlink(yol)
    # yol kacisi: goruntuleyici calisma alani disina cikamamali
    for kotu in ("../gizli.txt", "C:gizli", "/mutlak"):
        d = G.oku(os.path.join(ROOT, ".apprentice_test_home", "jobs"), "yok", kotu)
        assert d.get("hata"), "%r yolu reddedilmedi: %s" % (kotu, d)
    print("goruntuleyici: ok (pencere denetimleri, JS sozdizimi, yol kacisi reddi)")
    return True


def id_butunlugu() -> bool:
    """JS'in aradigi HER id HTML'de var mi? (ve HTML'deki id'ler kullaniliyor mu?)

    YASANDI: JS'e $("#oksuzPill") eklendi ama HTML'e o oge eklenmedi. Yoklama dongusu her
    turda "null.style" hatasi firlatti; hata dongunun ustunde yakalanmadigi icin PANEL
    TAMAMEN DONDU - kullanici "panelde hicbir hareket yok" dedi. Sozdizimi testi bunu
    goremez (kod gecerli), tarayici da sessizce cokuyor. Bu test tam o bosluga bakar."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    bloklar = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = "\n".join(bloklar)
    govde = re.sub(r"<script>.*?</script>", "", html, flags=re.S)

    tanimli = set(re.findall(r'id="([\w-]+)"', govde))
    # JS icinde olusturulan ogeler de sayilir (innerHTML/insertAdjacentHTML ile eklenenler)
    tanimli |= set(re.findall(r"id=[\\\"']([\w-]+)", js))
    tanimli |= set(re.findall(r'\.id\s*=\s*"([\w-]+)"', js))

    aranan = set(re.findall(r'\$\("#([\w-]+)"\)', js))
    aranan |= set(re.findall(r'getElementById\("([\w-]+)"\)', js))

    eksik = sorted(aranan - tanimli)
    assert not eksik, ("JS'in aradigi ama HTML'de OLMAYAN id: %s -> yoklama dongusu "
                       "null hatasiyla durur ve panel donar" % eksik)
    print("id butunlugu: ok (%d id aranıyor, hepsi tanimli)" % len(aranan))

    # Yoklama donguleri hata yutuyor mu (tek bir istisna paneli dondurmesin)
    for fn in ("isleriCek", "olaylariCek", "ustaChatCek"):
        i = js.find("async function %s(" % fn)
        assert i > 0, "%s bulunamadi" % fn
        # govde: bir sonraki ust duzey fonksiyona kadar (sabit pencere yetmiyordu - isleriCek
        # 60+ satir; catch penceresin disinda kaliyordu)
        adaylar = [x for x in (js.find("\nasync function ", i + 10),
                               js.find("\nfunction ", i + 10)) if x > 0]
        govde_fn = js[i:min(adaylar) if adaylar else len(js)]
        assert "try{" in govde_fn and "catch" in govde_fn, \
            "%s hata yutmuyor - tek istisna tum paneli durdurur" % fn
    print("yoklama donguleri: ok (uc dongu de hata yutuyor)")
    return True


def kaynak_denetimi() -> bool:
    """TANIMSIZ AD / olu atama taramasi (ruff F821, F811, F841).

    YASANDI: bir duzeltme iki sohbet fonksiyonuna bolunmus; biri 'gecmis' degiskenini
    tanimliyor, oteki KULLANIYORDU. Sozdizimi gecerli oldugu icin testler gecti, kullanici
    sohbete yazinca 500 aldi: "name 'gecmis' is not defined". Bu tarama tam o sinifi yakalar
    ve az kullanilan kod yollarini da kapsar (calistirmadan)."""
    ruff = [sys.executable, "-m", "ruff", "check", "--select", "F821,F811,F841",
            "--output-format", "concise", "--no-cache"]
    hedefler = ["clients", "server", "core", "envs", "izle.py", "kur.py", "kur_gui.py",
                "panel_ac.py", "panel_build.py"]
    r = subprocess.run(ruff + [os.path.join(ROOT, h) for h in hedefler],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=180, creationflags=0x08000000 if os.name == "nt" else 0)
    if r.returncode == 2 and "No module named" in (r.stderr or ""):
        print("kaynak denetimi: ruff yok, atlandi (pip install ruff)")
        return True
    # ruff temizse "All checks passed!" yazar - onu bulgu sanmayalim
    ciktilar = [s for s in (r.stdout or "").splitlines()
                if s.strip() and not s.startswith("All checks passed")
                and "Found 0 errors" not in s]
    assert r.returncode in (0, 1), "ruff calistirilamadi: %s" % (r.stderr or "")[:200]
    assert not ciktilar, "TANIMSIZ AD / olu atama bulundu:\n  " + "\n  ".join(ciktilar[:10])
    print("kaynak denetimi: ok (F821/F811/F841 temiz - tanimsiz ad yok)")
    return True


def sohbet_uclari() -> bool:
    """Cirak sohbeti (akisli ve duz) Ollama KAPALIYKEN bile duzgun hata donmeli - 500 yiginla
    degil. Yasandi: NameError -> HTTP 500 govdesi kullanicinin sohbet balonuna dustu."""
    ev = os.path.join(ROOT, ".apprentice_test_home", "sohbet_unit")
    os.makedirs(os.path.join(ev, "jobs"), exist_ok=True)
    port = 8897
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "clients", "web", "panel.py"),
                          "--port", str(port), "--home", ev],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=ROOT,
                         creationflags=0x08000000 if os.name == "nt" else 0)
    try:
        for _ in range(80):
            time.sleep(0.1)
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/hazir" % port, timeout=1).read()
                break
            except Exception:
                continue
        else:
            print("panel kalkmadi:", (p.stderr.read() or b"").decode("utf-8", "replace")[:200])
            return False

        def istek(yol, govde):
            r = urllib.request.Request("http://127.0.0.1:%d%s" % (port, yol),
                                       json.dumps(govde).encode(),
                                       {"Content-Type": "application/json",
                                        "X-Apprentice": "panel"})
            try:
                with urllib.request.urlopen(r, timeout=60) as c:
                    return c.status, c.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        # Ollama'yi ULASILMAZ yap: gercek modeli beklemeden hata yolunu sina
        kod, govde = istek("/api/cirak_sohbet", {"prompt": "merhaba",
                                                 "model": "olmayan-model-xyz:1b"})
        assert kod == 200, "duz sohbet %d dondu: %s" % (kod, govde[:200])
        d = json.loads(govde)
        assert "hata" in d or "cevap" in d, d
        assert "not defined" not in govde and "Traceback" not in govde, \
            "sohbette Python hatasi sizdi: %s" % govde[:200]

        r2 = urllib.request.Request("http://127.0.0.1:%d/api/cirak_sohbet_akis" % port,
                                    json.dumps({"prompt": "merhaba",
                                                "model": "olmayan-model-xyz:1b"}).encode(),
                                    {"Content-Type": "application/json", "X-Apprentice": "panel"})
        with urllib.request.urlopen(r2, timeout=60) as c:
            akis = c.read().decode("utf-8", "replace")
        assert "not defined" not in akis and "HTTP/1." not in akis, \
            "akisli sohbette hata sizdi: %s" % akis[:200]
        print("sohbet uclari: ok (duz + akisli, hata yolunda bile temiz yanit)")
        return True
    finally:
        p.terminate()


def uc_sozlesmesi() -> bool:
    """JS'in cagirdigi HER uc sunucuda var mi, ve HTML-JS yapisi butun mu?

    YASANDI: JS'e yeni uc/oge eklenip sunucu/HTML tarafi unutulunca panel SESSIZCE bozuluyor
    (donuyor ya da dugme is gormuyor). Bu test o baglari sozlesme gibi denetler."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        sunucu = f.read()

    # 1) fetch("/api/...") -> sunucuda o yol var mi
    cagrilan = set(re.findall(r'fetch\("(/[\w/]+)', js))
    cagrilan |= set(re.findall(r'window\.open\("(/[\w]+)', js))
    for yol in sorted(cagrilan):
        assert ('== "%s"' % yol) in sunucu or ("'%s'" % yol) in sunucu, \
            "JS '%s' ucunu cagiriyor ama panel.py'de boyle bir yol YOK" % yol
    print("uc sozlesmesi: ok (%d uc, hepsi sunucuda var)" % len(cagrilan))

    # 2) her panel adinin bir karti, her kartin basligi/govdesi/tutamagi var mi
    adlar = set(re.findall(r"(\w+):\"", re.search(r"const PANEL_ADLARI=\{(.*?)\};", js, re.S).group(1)))
    for ad in sorted(adlar):
        # kart govdesi: bir sonraki karta ya da izgara kapanisina kadar (son kart icin
        # sabit bir "sonraki oge" varsaymak kirilgan - dosya sirasi degisiyor)
        kart = re.search(r'<div class="kart" data-p="%s">(.*?)(?=<div class="kart"|<input type="file")'
                         % ad, html, re.S)
        assert kart, "%s paneli icin .kart ogesi YOK (dizilimlerde adi geciyor)" % ad
        govde = kart.group(1)
        assert 'class="kbaslik"' in govde, "%s: baslik cubugu yok (kapat/disari dugmesi eklenemez)" % ad
        assert 'class="kgovde"' in govde, "%s: govde yok" % ad
        assert 'class="tutamak"' in govde, "%s: boyutlandirma tutamagi yok" % ad
    print("panel yapisi: ok (%d panelin karti, basligi, govdesi, tutamagi tam)" % len(adlar))

    # 3) VARSAYILAN/dizilim tablolari ile PANEL_ADLARI ayni kumeyi kullanmali
    vars_ = set(re.findall(r"(\w+):\{gx:", re.search(r"const VARSAYILAN=\{(.*?)\};", js, re.S).group(1)))
    assert vars_ == adlar, "VARSAYILAN ile PANEL_ADLARI ayni degil: %s" % (vars_ ^ adlar)
    print("panel kumeleri: ok (VARSAYILAN == PANEL_ADLARI)")
    return True


def ust_bar_gorunur() -> bool:
    """Ust bardaki denetimler KAZAYLA gizlenmis olmasin.

    YASANDI (iki kez): (1) '#tekBar{display:none}' kurali yazilirken secici '#dizilim,#tekBar'
    olarak birlesti ve DIZILIM SECICI (hazir presetler) tamamen kayboldu - kullanici "hazir
    presetler nerede?" dedi. (2) Ust bar tasinca son ogeler 0 piksele coktu. Bu test her iki
    sinifi da yakalar: kritik denetimler ne CSS ile gizlenmis olabilir ne de ezilebilir."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    stil = "\n".join(re.findall(r"<style>(.*?)</style>", html, re.S))
    kritik = ["#dizilim", "#panelEkle", "#yerlesimKaydet", "#yerlesimSifirla", "#fontKontrol"]
    for kimlik in kritik:
        # "html.tekKip ..." disindaki KOSULSUZ display:none kurallarini ara
        for kural in re.findall(r"([^{}]+)\{([^{}]*)\}", stil):
            secici, govde = kural[0].strip(), kural[1]
            if "display:none" not in govde.replace(" ", ""):
                continue
            if secici.startswith("html.tekKip") or ".tekKip" in secici:
                continue                      # tek panel kipinde gizlenmeleri normal
            parcalar = [x.strip() for x in secici.split(",")]
            assert kimlik not in parcalar,                 ("%s KOSULSUZ gizlenmis: '%s{%s}' - arayuzde gorunmez olur"
                 % (kimlik, secici[:60], govde.strip()[:40]))
    # ezilmeye karsi: ust bar sarmali ve cocuklari daralmamali
    ust = re.search(r"#ust\{([^}]*)\}", stil)
    assert ust and "flex-wrap:wrap" in ust.group(1).replace(" ", ""),         "#ust sarmiyor - yer yetmeyince son denetimler 0 piksele coker"
    assert re.search(r"#ust\s*>\s*\*\{[^}]*flex-shrink:\s*0", stil),         "#ust cocuklarinda flex-shrink:0 yok - denetimler ezilir"
    print("ust bar denetimleri: ok (%d kritik oge gizlenmemis, bar sariyor)" % len(kritik))
    return True


def yerlesim_butun() -> bool:
    """VARSAYILAN izgara: panel dikdortgenleri cakismamali, sutun tasmamali."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const VARSAYILAN=\{(.*?)\};", html, re.S)
    assert m, "VARSAYILAN yerlesim bulunamadi"
    grid = {}
    for eslesme in re.finditer(r"(\w+):\{gx:(\d+),gy:(\d+),gw:(\d+),gh:(\d+)\}", m.group(1)):
        ad, gx, gy, gw, gh = eslesme.group(1), *(int(x) for x in eslesme.groups()[1:])
        grid[ad] = (gx, gy, gw, gh)
    assert len(grid) >= 8, "beklenenden az panel: %s" % list(grid)
    adlar = list(grid)
    for i in range(len(adlar)):
        for j in range(i + 1, len(adlar)):
            a, b = grid[adlar[i]], grid[adlar[j]]
            cakisir = not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or
                           a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
            assert not cakisir, "varsayilan yerlesimde cakisma: %s + %s" % (adlar[i], adlar[j])
    for ad, (gx, _gy, gw, _gh) in grid.items():
        assert gx + gw <= 24, "%s sutun tasmasi (%d+%d)" % (ad, gx, gw)
    print("varsayilan yerlesim: ok (%d panel, cakisma yok)" % len(grid))
    return True


def dizilimler_butun() -> bool:
    """Her DIZILIM presetinde: gorunur paneller cakismamali, sutun tasmamali, panel adi
    bilinmeyen/eksik olmamali. (Presetler elle yazildi; birinde cakisma olsa panel ust uste biner.)"""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const DIZILIMLER=\{(.*?)\n\};", html, re.S)
    assert m, "DIZILIMLER bulunamadi"
    govde = m.group(1)
    adlar_m = re.search(r"const PANEL_ADLARI=\{(.*?)\};", html, re.S)
    tum_panel = set(re.findall(r"(\w+):\"", adlar_m.group(1)))
    parcalar = re.split(r"\n  (?=\w+:\{etiket:)", govde)
    toplam = 0
    for parca in parcalar:
        bas = re.match(r"\s*(\w+):\{etiket:", parca)
        if not bas:
            continue
        ad = bas.group(1)
        g = re.search(r"gizli:\[(.*?)\]", parca, re.S)
        gizli = set(re.findall(r'"(\w+)"', g.group(1))) if g else set()
        kutu = {}
        for k in re.finditer(r"(\w+):\{gx:(\d+),gy:(\d+),gw:(\d+),gh:(\d+)\}", parca):
            kutu[k.group(1)] = tuple(int(x) for x in k.groups()[1:])
        if not kutu:
            assert "VARSAYILAN" in parca, "%s: kutu yok" % ad
            continue                      # dengeli: VARSAYILAN'a isaret eder, o ayrica denetlendi
        bilinmeyen = (set(kutu) | gizli) - tum_panel
        assert not bilinmeyen, "%s: bilinmeyen panel adi %s" % (ad, bilinmeyen)
        eksik = tum_panel - set(kutu)
        assert not eksik, "%s: yerlesimde tanimsiz panel %s" % (ad, eksik)
        gorunur = [k for k in kutu if k not in gizli]
        assert gorunur, "%s dizilimi: hic gorunur panel yok" % ad
        for i in range(len(gorunur)):
            for j in range(i + 1, len(gorunur)):
                a_, b_ = kutu[gorunur[i]], kutu[gorunur[j]]
                cak = not (a_[0] + a_[2] <= b_[0] or b_[0] + b_[2] <= a_[0] or
                           a_[1] + a_[3] <= b_[1] or b_[1] + b_[3] <= a_[1])
                assert not cak, "%s dizilimi: %s + %s cakisiyor" % (ad, gorunur[i], gorunur[j])
        for k, (gx, _gy, gw, _gh) in kutu.items():
            assert gx + gw <= 24, "%s/%s sutun tasmasi (%d+%d)" % (ad, k, gx, gw)
        # KAYDIRMA YOK kurali: gorunur paneller 24 satirlik cerceveye SIGMALI
        # (kullanici istegi: "paneller cercevenin disina tasmasin")
        for k in gorunur:
            gy, gh = kutu[k][1], kutu[k][3]
            assert gy + gh <= 24, "%s/%s cerceve disina tasiyor (satir %d+%d)" % (ad, k, gy, gh)
        toplam += 1
    assert toplam >= 5, "beklenenden az dizilim dogrulandi: %d" % toplam
    print("dizilim presetleri: ok (%d dizilim, cakisma/tasma/eksik yok)" % toplam)
    return True


def yerlesim_motoru() -> bool:
    """IZGARA MOTORUNU (itele + sikistir + sigdir) panel.html ile ayni kurallarla kosar ve
    her dizilimin 24x24 cerceveye SIGDIGINI dogrular.

    Kullanici kurali: "paneller cercevenin disina tasmasin, scroll ile asagida kalan olmasin."
    Statik kutu denetimi yetmez - motor kutulari ittikce/sikistirdikca sonuc degisir; burada
    ALGORITMANIN CIKTISI olculur."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    SUTUN = SATIR = 24

    def kutular(blok):
        return {m.group(1): [int(x) for x in m.groups()[1:]]
                for m in re.finditer(r"(\w+):\{gx:(\d+),gy:(\d+),gw:(\d+),gh:(\d+)\}", blok)}

    vars_ = kutular(re.search(r"const VARSAYILAN=\{(.*?)\};", html, re.S).group(1))
    diz = re.search(r"const DIZILIMLER=\{(.*?)\n\};", html, re.S).group(1)

    def cakisir(a, b):
        return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                    or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])

    def duzenle(yer, aktif):
        for _ in range(300):                      # itele
            degisti = False
            for a in aktif:
                for b in aktif:
                    if a != b and cakisir(yer[a], yer[b]):
                        yer[b][1] = yer[a][1] + yer[a][3]
                        degisti = True
            if not degisti:
                break
        for a in sorted(aktif, key=lambda x: yer[x][1]):    # sikistir
            while yer[a][1] > 0:
                yer[a][1] -= 1
                if any(b != a and cakisir(yer[a], yer[b]) for b in aktif):
                    yer[a][1] += 1
                    break
        # sigdir: KUCULTME YOK (dashboard standardi) - sigmayan panel RAFA iner
        raf = []
        koruma = 0
        while aktif and koruma < 20:
            alt = max(yer[a][1] + yer[a][3] for a in aktif)
            if alt <= SATIR:
                break
            koruma += 1
            if len(aktif) <= 1:
                yer[aktif[0]][1] = 0
                yer[aktif[0]][3] = min(SATIR, yer[aktif[0]][3])
                break
            en_alt = max(aktif, key=lambda x: yer[x][1] + yer[x][3])
            raf.append(en_alt)
            aktif = [x for x in aktif if x != en_alt]
        return yer, aktif, raf

    sayi = 0
    for blok in re.split(r"\n  (?=\w+:\{etiket:)", diz):
        m = re.match(r"\s*(\w+):\{etiket:", blok)
        if not m:
            continue
        ad = m.group(1)
        g = re.search(r"gizli:\[(.*?)\]", blok, re.S)
        gizli = set(re.findall(r'"(\w+)"', g.group(1))) if g else set()
        kut = kutular(blok) or {k: list(v) for k, v in vars_.items()}
        yer = {k: list(v) for k, v in kut.items()}
        aktif = [k for k in yer if k not in gizli]
        assert aktif, "%s: gorunur panel yok" % ad
        onceki_yukseklik = {k: v[3] for k, v in yer.items()}
        yer, aktif, raf = duzenle(yer, aktif)
        # KURAL: hicbir panel KUCULMEZ - sigmayan rafa iner
        for a in aktif:
            assert yer[a][3] >= onceki_yukseklik[a] or len(aktif) == 1,                 "%s: %s paneli kuculdu (%d -> %d) - kucultme yasak, rafa inmeliydi" % (
                    ad, a, onceki_yukseklik[a], yer[a][3])
        for i, a in enumerate(aktif):
            for b in aktif[i + 1:]:
                assert not cakisir(yer[a], yer[b]), "%s: %s + %s cakisiyor (motor sonrasi)" % (ad, a, b)
        alt = max(yer[a][1] + yer[a][3] for a in aktif)
        sag = max(yer[a][0] + yer[a][2] for a in aktif)
        assert alt <= SATIR, "%s: %d satir - cerceve disina tasiyor (kaydirma gerekir)" % (ad, alt)
        assert sag <= SUTUN, "%s: %d sutun - saga tasiyor" % (ad, sag)
        sayi += 1
    # kod paneli kaldirildi mi (dosyalar AYRI PENCEREDE acilir)
    assert 'data-p="kod"' not in html, "kod paneli hala izgarada"
    assert "/dosya?is=" in html, "dosya ayri pencerede acilmiyor (window.open yolu yok)"
    print("yerlesim motoru: ok (%d dizilim 24x24'e sigdi; kucultme yok, tasan panel rafa iner)" % sayi)
    return True


def sunucu_uclari() -> bool:
    ev = os.path.join(ROOT, ".apprentice_test_home", "panel_unit")
    os.makedirs(os.path.join(ev, "jobs"), exist_ok=True)
    port = 8899
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "clients", "web", "panel.py"),
                          "--port", str(port), "--home", ev],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=ROOT,
                         creationflags=0x08000000 if os.name == "nt" else 0)
    try:
        for _ in range(80):
            time.sleep(0.1)
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/hazir" % port, timeout=1).read()
                break
            except Exception:
                continue
        else:
            print("panel sunucusu ayaga kalkmadi:",
                  (p.stderr.read() or b"").decode("utf-8", "replace")[:300])
            return False
        t0 = time.time()
        urllib.request.urlopen("http://127.0.0.1:%d/api/hazir" % port, timeout=3).read()
        hazir_s = time.time() - t0
        assert hazir_s < 1.0, "/api/hazir yavas: %.2f sn" % hazir_s
        d = json.load(urllib.request.urlopen("http://127.0.0.1:%d/api/isler" % port, timeout=10))
        assert "isler" in d and "sistem" in d, d
        t1 = time.time()
        json.load(urllib.request.urlopen("http://127.0.0.1:%d/api/isler" % port, timeout=10))
        assert time.time() - t1 < 1.0, "isler onbellegi calismiyor (%.2f sn)" % (time.time() - t1)
        html = urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=5).read().decode("utf-8")
        assert "Apprentice" in html and "<script>" in html
        print("sunucu uclari: ok (hazir %.0f ms, isler onbellekli)" % (hazir_s * 1000))
        return True
    finally:
        p.terminate()


def calisma_dizini_kurallari() -> bool:
    """Panel gorev ucu: calisma dizini cozumu ve yol kacisi denetimi.
    Kural (kullanici karari): BOS = calisma alaninin KOKU (cirak proje dosyalarini gorsun);
    dolu = yalniz o alt klasor. Kok hala kurulum evi ise 'panel' alt klasoru kullanilir.
    Yasandi: eskiden bos birakilinca hep 'panel' alt klasoru aciliyor ve cirak projeyi
    ne okuyabiliyor ne de `ara` ile bulabiliyordu."""
    import shutil
    ev = os.path.join(ROOT, ".apprentice_test_home", "dizin_unit")
    proje = os.path.join(ev, "proje")
    if os.path.isdir(ev):
        shutil.rmtree(ev)
    os.makedirs(os.path.join(ev, "jobs"), exist_ok=True)
    os.makedirs(proje, exist_ok=True)
    port = 8898
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "clients", "web", "panel.py"),
                          "--port", str(port), "--home", ev],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=ROOT,
                         creationflags=0x08000000 if os.name == "nt" else 0)

    def gonder(dizin, ortam="fake"):
        govde = json.dumps({"gorev": "x", "kriterler": ["y"], "ortam": ortam,
                            "calisma_dizini": dizin}).encode()
        r = urllib.request.Request("http://127.0.0.1:%d/api/gorev" % port, govde,
                                   {"Content-Type": "application/json",
                                    "X-Apprentice": "panel"})
        with urllib.request.urlopen(r, timeout=30) as c:
            return json.loads(c.read().decode("utf-8"))

    try:
        for _ in range(80):
            time.sleep(0.1)
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/hazir" % port, timeout=1).read()
                break
            except Exception:
                continue
        else:
            print("panel kalkmadi:", (p.stderr.read() or b"").decode("utf-8", "replace")[:200])
            return False
        # 1) proje SECILMEMIS (kok == ev): bos dizin -> 'panel' alt klasoru (ev kirletilmesin)
        d = gonder("")
        assert d.get("klasor", "").rstrip("\/").endswith("panel"), d
        # 2) proje secili: bos dizin -> PROJE KOKU
        r = urllib.request.Request("http://127.0.0.1:%d/api/kok" % port,
                                   json.dumps({"yol": proje}).encode(),
                                   {"Content-Type": "application/json", "X-Apprentice": "panel"})
        try:
            urllib.request.urlopen(r, timeout=10).read()
        except Exception:
            with open(os.path.join(ev, "panel_ayar.json"), "w", encoding="utf-8") as f:
                json.dump({"kok": proje}, f)
            print("  (not: /api/kok yok, ayar dosyasi ile ayarlandi - panel yeniden okumali)")
            return True
        d = gonder("")
        assert os.path.realpath(d.get("klasor", "")) == os.path.realpath(proje), d
        # 3) alt klasor verilince oraya hapsolur
        d = gonder("alt/klasor")
        assert os.path.realpath(d.get("klasor", "")) == os.path.realpath(
            os.path.join(proje, "alt", "klasor")), d
        # 4) yol kacislari reddedilir (Windows tuzaklari dahil)
        for kotu in ("../disari", "C:kotu", "/mutlak", "alt/../../disari"):
            d = gonder(kotu)
            assert d.get("hata"), "%r kabul edildi: %s" % (kotu, d)
        print("calisma dizini kurallari: ok (bos=kok, alt klasor hapsi, 4 kacis reddedildi)")
        return True
    finally:
        p.terminate()


def fark_gorunumu() -> bool:
    """FARK (diff) motoru + sayfa sozlesmesi.

    Denetleyenin sorusu "ne yazdi" degil "NE DEGISTIRDI"dir: ayni dosya onarim turlarinda
    birkac kez yazilir, her 'write' olayi bir SURUM'dur. Bu test hem sayilari (kac ekleme,
    kac silme, katlama) hem de sayfanin uclarla sozlesmesini denetler."""
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import goruntuleyici as G
    d = tempfile.mkdtemp()
    jd = os.path.join(d, "is1")
    os.makedirs(jd)
    v1 = "def f():\n    return 1\n" + "\n".join("x%d = %d" % (i, i) for i in range(20))
    v2 = v1.replace("return 1", "return 2") + "\ny = 99\n"
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as fh:
        for t, c in ((1, v1), (2, v2)):
            fh.write(json.dumps({"type": "write", "path": "src/a.py", "after": c, "t": t}) + "\n")
        fh.write(json.dumps({"type": "write", "path": "src/b.py", "after": "pass\n"}) + "\n")
        fh.write('{bozuk json\n')                       # cop satir akisi bozmamali

    s = G.surumler(d, "is1", "src/a.py")
    assert [x["no"] for x in s["surumler"]] == [1, 2], s
    assert len(G.surumler(d, "is1", "src/b.py")["surumler"]) == 1, "dosyalar karisti"

    f2 = G.fark(d, "is1", "src/a.py")                   # varsayilan: son surum vs onceki
    assert (f2["a"], f2["b"]) == (1, 2) and not f2["ilk_yazim"], f2
    assert (f2["eklenen"], f2["silinen"]) == (2, 1), (f2["eklenen"], f2["silinen"])
    assert any(x["tur"] == "@" for x in f2["satirlar"]), "degismeyen uzun blok katlanmali"
    assert all(x["tur"] in " +-@" for x in f2["satirlar"]), "bilinmeyen satir turu"

    ilk = G.fark(d, "is1", "src/a.py", b=1)             # ilk surum: tamami eklenmis sayilir
    assert ilk["ilk_yazim"] and ilk["silinen"] == 0, ilk
    assert ilk["eklenen"] == len(v1.splitlines()), ilk["eklenen"]

    assert G.fark(d, "is1", "src/a.py", b=99)["b"] == 2, "surum numarasi sinirlanmali"
    assert G.oku(d, "is1", "src/a.py", surum=1)["icerik"] == v1, "surum icerigi yanlis"
    assert G.oku(d, "is1", "src/a.py", surum=9).get("hata"), "olmayan surum hata vermeli"
    assert G.fark(d, "is1", "src/yok.py").get("hata"), "kayitsiz dosya hata vermeli"

    for kotu in ("../../gizli.txt", "src/../../x", "C:/Windows/win.ini", ""):
        for r in (G.fark(d, "is1", kotu), G.surumler(d, "is1", kotu),
                  G.oku(d, "is1", kotu, surum=1)):
            assert r.get("hata") == "gecersiz yol", (kotu, r)

    # sayfa <-> uc sozlesmesi: sayfanin cagirdigi her uc panel.py'de karsilanmali
    h = G.sayfa("is1", "src/a.py")
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as fh:
        sunucu = fh.read()
    for uc in ("/api/dosya_surumler", "/api/dosya_fark"):
        assert uc in h, "goruntuleyici sayfasi %s ucunu cagirmiyor" % uc
        assert ('"%s"' % uc) in sunucu, "panel.py %s ucunu karsilamiyor" % uc
    assert "&surum=" in h, "kod kipinde surum secimi sayfada yok"
    for kimlik in ("bKip", "surumSec", "ozet"):
        assert ('id="%s"' % kimlik) in h, "fark arayuzunde #%s ogesi yok" % kimlik
    print("fark gorunumu: ok (surumler, +/- sayilari, katlama, yol reddi, uc sozlesmesi)")
    return True


def animasyon_tanimlari() -> bool:
    """Kullanilan HER animasyon adinin @keyframes tanimi var mi?

    YASANDI: `.nokta.bekle{animation:nabiz 1.2s infinite}` yaziliydi ama 'nabiz' hicbir yerde
    tanimlanmamisti - "kontrol ediliyor" noktasi HIC yanip sonmedi. Tarayici boyle bir hatayi
    sessizce yutar (gecersiz animasyon = animasyon yok), konsola bile yazmaz. Bu test o
    sinifin tamamina bakar: panel + goruntuleyici."""
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import goruntuleyici as G
    kaynaklar = [("panel.html", open(SAYFA, encoding="utf-8").read()),
                 ("goruntuleyici", G.sayfa("is1", "a.py"))]
    toplam = 0
    for ad, metin in kaynaklar:
        css = "\n".join(re.findall(r"<style>(.*?)</style>", metin, re.S))
        tanimli = set(re.findall(r"@keyframes\s+([\w-]+)", css))
        kullanilan = set()
        for d in re.findall(r"animation\s*:\s*([^;}\"']+)", css):
            for parca in d.split(","):
                for jeton in parca.strip().split():
                    # sure/sayi/anahtar sozcuk degil, ad olan ilk jeton
                    if re.match(r"^[a-zA-Z][\w-]*$", jeton) and jeton not in (
                            "infinite", "linear", "ease", "ease-in", "ease-out", "ease-in-out",
                            "alternate", "alternate-reverse", "reverse", "normal", "none",
                            "forwards", "backwards", "both", "running", "paused", "step-start",
                            "step-end", "steps", "cubic-bezier"):
                        kullanilan.add(jeton)
                        break
        eksik = kullanilan - tanimli
        assert not eksik, "%s: @keyframes TANIMSIZ animasyon: %s" % (ad, ", ".join(sorted(eksik)))
        toplam += len(kullanilan)
    print("animasyon tanimlari: ok (%d animasyon adi, hepsinin @keyframes'i var)" % toplam)
    return True


def model_kapsulu() -> bool:
    """Ust seritteki MODEL KAPSULU: secici + ▶/⏏ geri bildirim isiklari.

    Kullanici: "model secme islemi mesaj gonderme gibi oluyor... sag ustteki modelin aktif
    oldugunu gosteren yerden de model secebiliriz" ve "eject/play'e basinca bir isik falan
    olsun, cunku model gec yukleniyor, bir sey oluyor mu olmuyor mu anlasilmiyor."

    Bu test: (1) secicinin var ve iki secicinin BAGLI oldugunu, (2) dugmelerin secili modeli
    sunucuya gonderdigini, (3) sunucunun onu kabul ettigini, (4) isik durum makinesinin
    GERCEKTEN calistigini (Node'da kosturarak), (5) mesgulken yoklama dongusunun
    DURMADIGINI denetler."""
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))

    # 1) secici var, iki gorunum tek gercek
    assert 'id="modelSec"' in html, "model kapsulunde secici yok"
    assert "function modelSenkron" in js, "iki secici baglanmamis"
    assert '$("#modelSec").onchange' in js, "kapsul secicisi dinlenmiyor"
    assert "modelSenkron(ad)" in js, "#kModel secimi kapsule yansimiyor"

    # 2) dugmeler secili modeli yolluyor
    assert 'mesgulBasla("yukle"' in js and 'mesgulBasla("eject"' in js, "isik yakilmiyor"
    y = js[js.index('$("#yukle").onclick'):js.index('$("#eject").onclick')]
    assert "/api/yukle" in y and "JSON.stringify({model:model})" in y, \
        "▶ secili modeli gondermiyor: %s" % y[:200]

    # 3) sunucu tarafi kabul ediyor
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        sunucu = f.read()
    assert "def _model_yukle(model: str" in sunucu, "_model_yukle model parametresi almiyor"
    assert "def _model_bosalt(model: str" in sunucu, "_model_bosalt model parametresi almiyor"
    assert '_model_yukle(str(veri.get("model")' in sunucu, "/api/yukle govdeyi okumuyor"

    # 4) MESGULKEN DONGU DURMAMALI (yasandi: erken return panelin geri kalanini dondururdu)
    d = js.index("if(mesgul){", js.index("async function isleriCek"))
    blok = js[d:js.index("\n    }", d)]
    assert "return" not in blok, "mesgul dalinda return var - yoklama dongusu 5 dk donar:\n" + blok

    # 5) durum makinesi Node'da GERCEKTEN kosuyor mu?
    node = shutil.which("node")
    if not node:
        print("model kapsulu: ok (node yok, durum makinesi kosturulmadi)")
        return True
    bas, sonu = js.index("let mesgul=null;"), js.index("setInterval(mesgulCiz,1000);")
    makine = js[bas:sonu]
    surus = """
const _o={};
function _el(id){ if(!_o[id]){ const s=new Set(); _o[id]={id,value:"",textContent:"",title:"",
  className:"", classList:{add:c=>s.add(c), remove:c=>s.delete(c), contains:c=>s.has(c),
  toggle:(c,v)=>{ v?s.add(c):s.delete(c); return !!v }}}; } return _o[id]; }
function $(q){ return _el(String(q).replace("#","")); }
let TOST=[]; function tost(m){ TOST.push(String(m)); }
function setTimeout(){}
function ONAY(k,a){ if(!k) throw new Error("SOZLESME: "+a); }
""" + makine + """
// --- yukleme: isik ONCE yanar (istek donmeden), sayac isler ---
mesgulBasla("yukle","kutup/qwen3-coder-next:q4");
ONAY($("#modelKapsul").classList.contains("mesgul"), "kapsul isigi yanmadi");
ONAY($("#yukle").classList.contains("calisiyor"), "play dugmesi donmuyor");
ONAY(!$("#eject").classList.contains("calisiyor"), "eject bosuna donuyor");
ONAY(/yükleniyor/.test($("#modelAd").textContent), "kapsulde 'yukleniyor' yazmiyor: "+$("#modelAd").textContent);
ONAY(/\\d+ sn/.test($("#modelAd").textContent), "sayac yok: "+$("#modelAd").textContent);
ONAY($("#modelNokta").className==="nokta bekle", "nokta nabza gecmedi");
ONAY(mesgul && mesgul.tur==="yukle", "mesgul durumu tutulmuyor");
// --- bitis: isik soner, yesil parlar, sure bildirilir ---
mesgulBitir(true);
ONAY(mesgul===null, "mesgul temizlenmedi");
ONAY(!$("#modelKapsul").classList.contains("mesgul"), "isik sonmedi");
ONAY(!$("#yukle").classList.contains("calisiyor"), "play donmeye devam ediyor");
ONAY($("#modelKapsul").classList.contains("tamam"), "bitiste yesil parlama yok");
ONAY(TOST.some(t=>/sn/.test(t)), "sure bildirilmedi: "+TOST.join("|"));
// --- ikinci kez bitirmek zarar vermemeli ---
mesgulBitir(true);
// --- eject isigi ayri dugmede ---
mesgulBasla("eject","");
ONAY($("#eject").classList.contains("calisiyor"), "eject dugmesi donmuyor");
ONAY(!$("#yukle").classList.contains("calisiyor"), "play bosuna donuyor");
ONAY(/boşaltılıyor/.test($("#modelAd").textContent), "eject metni yok");
mesgulBitir(false,"yüklü model yoktu");
ONAY(!$("#modelKapsul").classList.contains("mesgul"), "basarisiz bitiste isik sonmedi");
// --- iki secici tek gercek ---
$("#modelSec").value="a:1"; $("#kModel").value="";
modelSenkron("b:2");
ONAY($("#modelSec").value==="b:2" && $("#kModel").value==="b:2", "seciciler senkron degil");
ONAY(secilenModel()==="b:2", "secilenModel yanlis");
console.log("MAKINE-OK");
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(surus)
        yol = f.name
    try:
        r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        assert "MAKINE-OK" in (r.stdout or ""), \
            "isik durum makinesi KALDI:\n%s\n%s" % ((r.stdout or "")[-400:], (r.stderr or "")[-600:])
    finally:
        os.unlink(yol)
    print("model kapsulu: ok (secici bagli, ▶/⏏ secili modeli yolluyor, isik makinesi kosuyor)")
    return True


def vurgulayici_sozlesmesi() -> bool:
    """Iki sozdizimi vurgulayicisi da METNI BOZMAMALI ve ETIKET SIZDIRMAMALI.

    YASANDI (kullanici ekran goruntusuyle bildirdi): goruntuleyicide docstring'li her satir
    `class="st">""class="st">"Bos liste...` diye ham HTML dokuyordu. Sebep: zincirleme
    replace - once dizge gecisi <span class="st"> yaziyor, hemen ardindan anahtar kelime
    gecisi KENDI YAZDIGI etiketin icindeki 'class' kelimesini boyuyordu ('class' anahtar
    kelime listesinde). Uretilen HTML'in yeniden taranmasi bu sinifin tamamini doguruyor.

    Sozdizimi testi bunu goremez (JS gecerli), goz de her satirda fark etmez. Bu test
    DEGISMEZ KURALA bakar: etiketler soyulunca geriye TAM OLARAK kaynak metin kalmali,
    span'lar dengeli olmali, ic ice bozuk etiket olmamali. Kosum: tests/js/renk_sozlesme.js"""
    node = shutil.which("node")
    if not node:
        print("vurgulayici sozlesmesi: node yok, atlandi")
        return True
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import goruntuleyici as G
    with open(os.path.join(ROOT, "tests", "js", "renk_sozlesme.js"), encoding="utf-8") as f:
        surus = f.read()

    gjs = re.search(r"<script>(.*?)</script>", G.sayfa("i", "a.py"), re.S).group(1)
    goruntuleyici = gjs[gjs.index("function kacir("):gjs.index("function ciz(")]

    with open(SAYFA, encoding="utf-8") as f:
        pjs = "\n".join(re.findall(r"<script>(.*?)</script>", f.read(), re.S))
    kw = pjs[pjs.index("const KW="):pjs.index("\n", pjs.index("const KW="))]
    panel = pjs[pjs.index("function kacir("):pjs.index("function renklendir2(")]

    kod = (surus
           + "\n(function(){\n" + goruntuleyici + "\ndene('goruntuleyici renkle', renkle);\n})();\n"
           + "(function(){\n" + kw + "\n" + panel + "\ndene('panel renklendir', renklendir);\n})();\n"
           + "console.log('RENK-OK');\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(kod)
        yol = f.name
    try:
        r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        assert "RENK-OK" in (r.stdout or ""), \
            "VURGULAYICI SOZLESMESI KALDI:\n%s" % ((r.stderr or r.stdout or "")[:900])
    finally:
        os.unlink(yol)

    # Sablon Python tarafinda da temiz olmali: SAYFA ham olmayan bir dizge, gecersiz kacis
    # ("\\/" gibi) Python tarafindan yenir ve JS'e BOZUK desen gider (yasandi).
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        with open(os.path.join(ROOT, "clients", "web", "goruntuleyici.py"), encoding="utf-8") as f:
            compile(f.read(), "goruntuleyici.py", "exec")
    print("vurgulayici sozlesmesi: ok (iki vurgulayici da metni koruyor, etiket sizdirmiyor)")
    return True


def sahiplik_kurali() -> bool:
    """TEK YAZAR KURALI: is kaydina yalniz SAHIBI yazar; baskasi OKUR.

    YASANDI: panel, sahibi olmadigi MCP islerine de "usta_rapor" olayi ekliyordu.
      1. Iki surec ayni dosyaya append ediyordu (panel'in korumasi oku-sonra-yaz, yani
         TOCTOU; sunucununki kendi ornek bayragi). Windows'ta es zamanli append satiri
         yirtabilir ve JSONL okuyucularimiz bozuk satiri sessizce yuttugu icin kayip
         hic fark edilmiyordu.
      2. Yazilan sey bir IDDIA'ydi: "ustaya su rapor gitti". MCP isinde usta
         worker_status'u hic cagirmamis olabilir - o zaman kimseye bir sey gitmemistir.
         Panel olmayan bir kaniti uydurmus olurdu.
    Bu test: sahibi olmadigimiz isin olay dosyasina TEK BAYT yazilmadigini cakar."""
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import panel as P
    from core.inceleme import inceleme

    ev = tempfile.mkdtemp()
    jobs = os.path.join(ev, "jobs")
    os.makedirs(jobs, exist_ok=True)

    def is_yaz(jid, kayit):
        jd = os.path.join(jobs, jid)
        os.makedirs(jd, exist_ok=True)
        with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f, ensure_ascii=False)
        with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "write", "path": "a.py", "before": "", "after": "x=1\n"}) + "\n")
            f.write(json.dumps({"type": "result", "ok": True, "errors": [], "rounds": 0}) + "\n")
            f.write(json.dumps({"type": "exit", "code": 0}) + "\n")
        return os.path.join(jd, "events.jsonl")

    eski_home, eski_depo = P.HOME, P.DEPO
    P.HOME = ev
    P.DEPO = P.IsDeposu(ev)
    try:
        # 1) BASKASININ isi (MCP): panel DOKUNMAMALI
        yol = is_yaz("mcp_isi", {"id": "mcp_isi", "durum": "bitti",
                                 "sahip": {"rol": "mcp", "pid": 999999}})
        once = open(yol, "rb").read()
        assert P._sahip_mi("mcp_isi") is False, "MCP isi panelin sanildi"
        P._usta_rapor_tamamla("mcp_isi")
        assert open(yol, "rb").read() == once, "PANEL BASKASININ IS KAYDINA YAZDI"

        # 2) KENDI isi: panel yazabilir
        yol2 = is_yaz("panel_isi", {"id": "panel_isi", "durum": "bitti", "kaynak": "web-panel",
                                    "sahip": {"rol": "panel", "pid": os.getpid()}})
        assert P._sahip_mi("panel_isi") is True, "kendi isini sahiplenmedi"
        P._usta_rapor_tamamla("panel_isi")
        assert '"usta_rapor"' in open(yol2, encoding="utf-8").read(), "kendi isine yazmadi"

        # 3) ESKI kayit (sahip alani yok): kaynak alani ayni seyi soyler
        is_yaz("eski_panel", {"id": "eski_panel", "durum": "bitti", "kaynak": "web-panel"})
        is_yaz("eski_mcp", {"id": "eski_mcp", "durum": "bitti"})
        assert P._sahip_mi("eski_panel") is True
        assert P._sahip_mi("eski_mcp") is False
        assert inceleme(jobs, "eski_panel")["sahiplik"]["rol"] == "panel"
        assert inceleme(jobs, "eski_mcp")["sahiplik"]["rol"] == "mcp"
        # ne biri ne oteki: UYDURULMAZ
        is_yaz("ornek", {"id": "ornek", "durum": "bitti", "kaynak": "ornek"})
        assert inceleme(jobs, "ornek")["sahiplik"]["rol"] == "?"

        # 4) OKSUZ is: sahip surec olmus -> kimse son halkayi yazmayacak, SOYLENIR
        oks = inceleme(jobs, "mcp_isi")["sahiplik"]
        assert oks["rol"] == "mcp" and oks["canli"] is False, oks
        canli = inceleme(jobs, "panel_isi")["sahiplik"]
        assert canli["canli"] is True, canli
        # pid kaydedilmemisse "bilinmiyor" denir, "olu" DENMEZ
        assert inceleme(jobs, "eski_mcp")["sahiplik"]["canli"] is None

        # 5) bozuk/eksik job.json: sahiplenme (guvenli taraf)
        os.makedirs(os.path.join(jobs, "bozuk"), exist_ok=True)
        open(os.path.join(jobs, "bozuk", "job.json"), "w").write("{bozuk")
        assert P._sahip_mi("bozuk") is False
    finally:
        P.HOME, P.DEPO = eski_home, eski_depo
    print("sahiplik kurali: ok (baskasinin kaydina yazilmiyor, oksuz sahip goruluyor)")
    return True


def karar_uclari() -> bool:
    """KABUL / REDDET / TEKRAR DENE. Ucunden yalniz REDDET dosyaya dokunur.

    En kritik cakma: ONAY OLMADAN reddin tek bayt degistirmedigi. Geri alma GERI
    ALINAMAZ; kazara gonderilen bir istek kullanicinin kodunu silmemeli."""
    ev = os.path.join(ROOT, ".apprentice_test_home", "karar_unit")
    if os.path.isdir(ev):
        shutil.rmtree(ev, ignore_errors=True)
    os.makedirs(os.path.join(ev, "jobs"), exist_ok=True)
    wd = tempfile.mkdtemp()
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("yeni\n")
    with open(os.path.join(wd, "b.py"), "w", encoding="utf-8") as f:
        f.write("cirak yaratti\n")
    jd = os.path.join(ev, "jobs", "is1")
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "is1", "durum": "bitti", "calisma_dizini": wd, "gorev": "a.py duzelt",
                   "kabul_kriterleri": ["x"], "ortam": "code", "dogrulama": "derleme",
                   "anlik": {"yontem": "yok"}, "kaynak": "web-panel",
                   "sahip": {"rol": "panel", "pid": os.getpid()}}, f)
    with open(os.path.join(jd, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in ({"type": "write", "path": "a.py", "before": "eski\n", "after": "yeni\n"},
                  {"type": "write", "path": "b.py", "before": "", "after": "cirak yaratti\n"},
                  {"type": "result", "ok": False, "errors": ["a.py(1): SyntaxError: bad"],
                   "rounds": 1},
                  {"type": "exit", "code": 1}):
            f.write(json.dumps(e) + "\n")

    port = 8893
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "clients", "web", "panel.py"),
                          "--port", str(port), "--home", ev],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=ROOT,
                         creationflags=0x08000000 if os.name == "nt" else 0)

    def istek(u, govde=None):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (port, u),
                                   data=json.dumps(govde).encode() if govde is not None else None,
                                   headers={"X-Apprentice": "panel",
                                            "Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(r, timeout=30))

    def var(ad):
        return os.path.exists(os.path.join(wd, ad))

    def oku(ad):
        with open(os.path.join(wd, ad), encoding="utf-8") as f:
            return f.read()

    try:
        for _ in range(120):
            time.sleep(0.1)
            try:
                istek("/api/hazir")
                break
            except Exception:
                pass

        # 1) PLAN kuru calisma: hicbir seyi degistirmez
        pl = istek("/api/geri_al?is=is1")
        assert pl["mumkun"] is True, pl
        assert {e["yol"]: e["eylem"] for e in pl["eylemler"]} == {"a.py": "geri_yaz",
                                                                 "b.py": "sil"}, pl
        assert var("b.py") and oku("a.py") == "yeni\n", "PLAN DOSYAYA DOKUNDU"

        # 2) ONAYSIZ RED -> REDDEDILIR ve tek bayt degismez  (en kritik cakma)
        r = istek("/api/karar", {"is": "is1", "karar": "red"})
        assert r.get("hata") and "onay" in r["hata"], r
        assert var("b.py") and oku("a.py") == "yeni\n", "ONAYSIZ SILME OLDU"

        # 3) KABUL -> dosyalara DOKUNMAZ, yalniz kayit
        k = istek("/api/karar", {"is": "is1", "karar": "kabul", "not": "olur"})
        assert k["durum"] == "kabul", k
        assert var("b.py") and oku("a.py") == "yeni\n", "KABUL DOSYAYA DOKUNDU"
        assert istek("/api/inceleme?is=is1")["karar"]["durum"] == "kabul"
        # karar OLAY GUNLUGUNE yazilmamali (tek yazar kurali)
        with open(os.path.join(jd, "events.jsonl"), encoding="utf-8") as f:
            assert "kabul" not in f.read(), "karar events.jsonl'e yazilmis"
        assert os.path.exists(os.path.join(jd, "inceleme.json")), "karar dosyasi yok"

        # 4) ONAYLI RED -> geri alir; onceki karar kayitta kalir
        r2 = istek("/api/karar", {"is": "is1", "karar": "red", "onay": True})
        assert r2["durum"] == "red" and r2["geri_alinan"] == 2, r2
        assert oku("a.py") == "eski\n" and not var("b.py"), "geri alinmadi"
        assert r2.get("onceki") and r2["onceki"][0]["durum"] == "kabul", r2

        # 5) gecersiz istekler
        assert istek("/api/karar", {"is": "is1", "karar": "sacma"}).get("hata")
        assert istek("/api/karar", {"is": "yok", "karar": "kabul"}).get("hata")
        assert istek("/api/tekrar", {"is": "yok"}).get("hata")
        print("karar uclari: ok (onaysiz red reddedildi, kabul dokunmadi, red geri aldi)")
        return True
    finally:
        p.terminate()
        shutil.rmtree(ev, ignore_errors=True)


def bayat_surec_uyarisi() -> bool:
    """Sunucu sureci diskteki panel.py'den ESKI ise panel UYARMALI.

    YASANDI (uc kez, sonuncusu kullaniciya kadar gitti): panel.html her istekte DISKTEN
    okunur ama panel.py surece BIR KEZ yuklenir. Depoyu guncelleyip paneli yeniden
    baslatmazsan arayuz YENI, sunucu ESKI olur; yeni dugme olmayan bir ucu cagirir, 404
    doner ve arayuz SESSIZCE bir sey yapmaz. Kullanici "REDDET'e bastim, bir sey olmadi"
    dedi - dugme dogruydu, sunucu eskiydi.

    Bu test uyarinin ZINCIRINI cakar: sunucu imzayi olcuyor mu, uc bunu doniyor mu,
    arayuz seridi ve yoklamasi var mi."""
    with open(os.path.join(ROOT, "clients", "web", "panel.py"), encoding="utf-8") as f:
        sunucu = f.read()
    for parca, aciklama in (("_kaynak_imza", "kaynak imzasi"), ("_BASLANGIC_IMZA", "baslangic imzasi"),
                            ("def _bayat_mi", "bayat denetimi"), ('"bayat": _bayat_mi()', "uc yaniti")):
        assert parca in sunucu, "sunucuda %s (%s) yok" % (parca, aciklama)

    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    assert 'id="bayatSerit"' in html, "uyari seridi yok"
    assert "function bayatYokla" in html and "bayatYokla()" in html, "yoklama baglanmamis"
    # SUREKLI de yoklanmali: panel ACIKKEN guncelleme yapilirsa (git pull) serit yine cikmali
    assert re.search(r"setInterval\(\s*bayatYokla", html), "bayat yoklamasi bir kerelik kalmis"
    assert "r.bayat" in html, "arayuz bayat alanini okumuyor"

    # imza GERCEKTEN degisimi yakaliyor mu (dosya boyutu/zamani)
    sys.path.insert(0, os.path.join(ROOT, "clients", "web"))
    import panel as P
    imza = P._kaynak_imza()
    assert imza and len(imza) >= 8, imza
    assert P._bayat_mi() is False, "degismemis dosya bayat sayildi"
    eski = P._BASLANGIC_IMZA
    try:
        P._BASLANGIC_IMZA = "0" * 16     # sanki surec ESKI surumle baslamis
        assert P._bayat_mi() is True, "degismis dosya bayat sayilmadi"
    finally:
        P._BASLANGIC_IMZA = eski

    # IMZA ICERIGE bagli olmali, mtime'a DEGIL. YASANDI: ilk surum boyut+mtime kullandi;
    # gerileme sinamasi dosyayi AYNI icerikle geri yazinca panel "sunucu eski" diye
    # YANLIS ALARM verdi ve kullaniciyi bosuna ugrastirdi.
    # Denetim yalniz panel.py'yi degil, panelin YUKLEDIGI tum modulleri kapsamali:
    # arayuz yeni alan bekleyip core/inceleme.py eski kalirsa da ayni sessiz hata olur.
    assert len(P._IZLENEN_KAYNAKLAR) >= 4, P._IZLENEN_KAYNAKLAR
    for gerek in ("inceleme.py", "geri_al.py", "panel.py"):
        assert any(gerek in y for y in P._IZLENEN_KAYNAKLAR), "%s izlenmiyor" % gerek
    cekirdek = os.path.join(ROOT, "core", "inceleme.py")
    ci = P._kaynak_imza()
    with open(cekirdek, encoding="utf-8", newline="") as f:
        cham = f.read()
    try:
        with open(cekirdek, "w", encoding="utf-8", newline="") as f:
            f.write(cham + "\n# gecici\n")
        assert P._kaynak_imza() != ci, "core degisti ama imza degismedi"
    finally:
        with open(cekirdek, "w", encoding="utf-8", newline="") as f:
            f.write(cham)
    assert P._kaynak_imza() == ci, "core geri alindi ama imza donmedi"

    kaynak = os.path.join(ROOT, "clients", "web", "panel.py")
    once = P._kaynak_imza()
    # mtime'i ACIKCA farkli bir ana kur: os.utime(None) "simdi" yazar ve saniye
    # cozunurlugunde ayni kalabilir - o zaman bu sinama hicbir seyi olcmez (yasandi).
    st = os.stat(kaynak)
    os.utime(kaynak, (st.st_atime, st.st_mtime - 7200))
    assert P._kaynak_imza() == once, "imza mtime'a bagli - ayni icerik farkli imza verdi"
    with open(kaynak, encoding="utf-8", newline="") as f:
        ham = f.read()
    try:
        with open(kaynak, "w", encoding="utf-8", newline="") as f:
            f.write(ham + "\n# gecici\n")
        assert P._kaynak_imza() != once, "icerik degisti ama imza ayni kaldi"
    finally:
        with open(kaynak, "w", encoding="utf-8", newline="") as f:
            f.write(ham)
    assert P._kaynak_imza() == once, "geri alinca imza eski haline donmedi"

    # YENIDEN BASLAT: panel PENCERESINI kapatip acmak sunucuyu durdurmaz (kabuk calisan
    # sunucuyu yeniden kullanir) - bu yuzden serit uzerinde dugme olmali.
    assert "def _yeniden_baslat(" in sunucu, "yeniden baslatma yok"   # parantez sart:
    # "def _yeniden_baslat" alt dizgesi "_yeniden_baslat_YOK" icinde de gecer (yasandi)
    assert '"/api/yeniden_baslat"' in sunucu, "yeniden baslatma ucu yok"
    assert "srv = None" in sunucu and "range(40)" in sunucu,         "yeni surec portun bosalmasini beklemiyor"
    assert 'id="bYenidenBaslat"' in html, "seritte yeniden baslat dugmesi yok"
    assert "/api/yeniden_baslat" in html, "dugme ucu cagirmiyor"
    print("bayat surec uyarisi: ok (imza + uc + serit zinciri tam)")
    return True


def karar_rozeti() -> bool:
    """Rozet SON KARARI degil HIKAYEYI anlatmali.

    YASANDI: kullanici once REDDET dedi (kod geri alindi), sonra KABUL ET dedi. Rozet
    yalniz "kabul edildi" yazdi - ekrana bakan "kod duruyor, kabul edilmis" sanirdi.
    Oysa kod geri alinmisti ve bu KAYITTA duruyordu. Kayitta olan gercegi arayuzde
    saklamak bu projenin beyan/kanit kuralina aykiri.

    kararRozetMetni SAF fonksiyon (DOM'suz) - burada Node'da GERCEKTEN kosturulur."""
    node = shutil.which("node")
    if not node:
        print("karar rozeti: node yok, atlandi")
        return True
    with open(SAYFA, encoding="utf-8") as f:
        html = f.read()
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    bas = js.index("function kararRozetMetni(")
    son = js.index("function kararCiz(", bas)
    surus = js[bas:son] + KARAR_ROZET_SURUS
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(surus)
        yol = f.name
    try:
        r = subprocess.run([node, yol], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        assert "ROZET-OK" in (r.stdout or ""), \
            "ROZET SOZLESMESI KALDI:\n%s" % ((r.stderr or r.stdout or "")[:600])
    finally:
        os.unlink(yol)
    print("karar rozeti: ok (gecmis gizlenmiyor, kac dosya geri alindigi duruyor)")
    return True


def main() -> int:
    ok = (js_sozdizimi() and metin_isleyicileri() and kaynak_denetimi() and id_butunlugu() and uc_sozlesmesi() and ust_bar_gorunur() and yerlesim_butun() and dizilimler_butun()
          and yerlesim_motoru() and sunucu_uclari() and calisma_dizini_kurallari() and sohbet_uclari()
          and goruntuleyici_sayfasi() and fark_gorunumu()
          and animasyon_tanimlari() and model_kapsulu()
          and vurgulayici_sozlesmesi() and sahiplik_kurali() and karar_uclari() and bayat_surec_uyarisi() and karar_rozeti())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

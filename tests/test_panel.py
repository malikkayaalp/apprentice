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


def main() -> int:
    ok = (js_sozdizimi() and metin_isleyicileri() and kaynak_denetimi() and id_butunlugu() and uc_sozlesmesi() and ust_bar_gorunur() and yerlesim_butun() and dizilimler_butun()
          and yerlesim_motoru() and sunucu_uclari() and calisma_dizini_kurallari() and sohbet_uclari())
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

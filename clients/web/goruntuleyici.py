"""Dosya goruntuleyici: AYRI PENCERE (panel alanini kaplamasin).

Kullanici istegi: "oluşturulan dosyalara tıklayınca içeriği panel içinde açılmasın, ayrı bir
arayüz gibi dışarıda açılsın ki alan kaplamasın." Panel yalnizca DOSYA LISTESI tutar;
tiklayinca burasi acilir (WebView2 kabugunda gercek ikinci pencere, tarayicida yeni pencere).

Icerik 2 saniyede bir tazelenir: model dosyayi yeniden yazarsa degisen satirlar parlar.
"""
from __future__ import annotations
import json, os

SAYFA = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>{ad} - Apprentice</title>
<style>
:root{{color-scheme:dark;--zemin:#141210;--panel:#1c1a17;--cizgi:#332f2a;--metin:#f1ede6;--soluk:#8f8880;
 --vurgu:#d97757;--yesil:#6fc28a;--mavi:#7fb2e5;--sari:#e9b85c;--mor:#b99cd8;
 --mono:'JetBrains Mono','Cascadia Code',Consolas,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--zemin);color:var(--metin);font:13px/1.55 var(--mono);
 display:flex;flex-direction:column;height:100vh}}
header{{display:flex;align-items:center;gap:12px;padding:9px 14px;background:var(--panel);
 border-bottom:1px solid var(--cizgi);flex-shrink:0;cursor:grab;user-select:none}}
header:active{{cursor:grabbing}}
.pdug{{cursor:pointer;padding:2px 9px;border-radius:6px;color:var(--soluk);font-size:13px;
 line-height:1.2}}
.pdug:hover{{background:rgba(255,255,255,.08);color:var(--metin)}}
.pdug.etkin{{color:var(--vurgu);background:rgba(217,119,87,.16)}}
.pdug.kapat:hover{{background:rgba(224,108,95,.28);color:#fff}}
header b{{color:var(--vurgu)}}
header .k{{color:var(--soluk);font-size:11px}}
header .sag{{margin-left:auto;display:flex;gap:8px;align-items:center}}
button{{background:transparent;border:1px solid var(--cizgi);color:var(--soluk);
 border-radius:7px;padding:4px 10px;cursor:pointer;font:11px var(--mono)}}
button:hover{{color:var(--metin);border-color:var(--vurgu)}}
#kod{{flex:1;overflow:auto;padding:12px 14px}}
table{{border-collapse:collapse;width:100%}}
td.n{{color:#5a544d;text-align:right;padding-right:14px;user-select:none;width:1%;
 white-space:nowrap;vertical-align:top}}
td.s{{white-space:pre;padding-right:18px}}
tr:hover td.s{{background:rgba(217,119,87,.07)}}
.kw{{color:var(--mor)}} .st{{color:var(--sari)}} .cm{{color:#6b645c;font-style:italic}}
.nu{{color:var(--mavi)}} .fn{{color:var(--yesil)}}
td.s.ek{{background:rgba(111,194,138,.13)}}
td.s.sil{{background:rgba(224,108,95,.13)}}
td.n.ek{{color:var(--yesil)}} td.n.sil{{color:#e06c5f}}
td.s.atla{{color:var(--soluk);font-style:italic;background:rgba(255,255,255,.03)}}
.im{{display:inline-block;width:1.2ch;color:#5a544d}}
.im.ek{{color:var(--yesil)}} .im.sil{{color:#e06c5f}}
#ozet .art{{color:var(--yesil)}} #ozet .eks{{color:#e06c5f}}
button.etkin{{color:var(--vurgu);border-color:var(--vurgu)}}
select{{background:var(--panel);border:1px solid var(--cizgi);color:var(--soluk);
 border-radius:7px;padding:3px 6px;font:11px var(--mono);max-width:200px;cursor:pointer}}
select:hover{{color:var(--metin);border-color:var(--vurgu)}}
.degisti{{animation:parla 1.4s ease}}
@keyframes parla{{from{{background:rgba(111,194,138,.28)}}to{{background:transparent}}}}
</style></head><body>
<header>
  <b>{ad}</b><span class="k">{bilgi}</span>
  <span class="sag"><span class="k" id="ozet"></span>
    <button id="bKip" title="kod / fark görünümü">± fark</button>
    <select id="surumSec" title="sürüm seç"></select>
    <span class="k" id="durum">yükleniyor…</span>
    <button id="kopyala">kopyala</button><button id="yenile">yenile</button>
    <label class="k"><input type="checkbox" id="oto" checked> otomatik</label>
    <span class="pdug" id="pUstte" title="hep üstte kalsın">📌</span>
    <span class="pdug" id="pBuyult" title="büyüt / geri al">▢</span>
    <span class="pdug kapat" id="pKapat" title="kapat">✕</span></span>
</header>
<div id="kod"></div>
<script>
const IS={is_json}, YOL={yol_json};
/* TEK GECISLI TARAYICI. YASANDI: eskiden zincirleme replace vardi - once dizge gecisi
   <span class="st"> yaziyor, hemen ardindan anahtar kelime gecisi KENDI YAZDIGI etiketin
   icindeki 'class' kelimesini boyuyordu ('class' KW listesinde!). HTML parcalaniyor,
   ekrana ham `class="st">` dokuluyordu (kullanici ekran goruntusuyle bildirdi).
   Cozum: once BELIRTEC bulunur, sonra kacirilip etiketlenir - uretilen HTML bir daha
   taranmaz. Yan fayda: dizgenin ICINDEKI kelimeler artik anahtar kelime sanilmiyor. */
function kacir(s){{return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}}
const KW_KUME=new Set(("def class if elif else for while return import from raise try except "+
 "finally with as in not and or is None True False lambda pass break continue yield self "+
 "public private protected static void var new using namespace int float string bool "+
 "foreach null this override virtual async await const let function").split(" "));
const BELIRTEC=/(#[^\\n]*|\\/\\/[^\\n]*)|("(?:\\\\.|[^"\\\\])*"?|'(?:\\\\.|[^'\\\\])*'?)|(\\d+(?:\\.\\d+)?)|([A-Za-z_]\\w*)/g;
function renkle(s){{
  s=String(s==null?"":s);
  let cikti="", i=0, m;
  BELIRTEC.lastIndex=0;
  while((m=BELIRTEC.exec(s))!==null){{
    cikti+=kacir(s.slice(i,m.index));
    if(m[1])      cikti+='<span class="cm">'+kacir(m[1])+'</span>';
    else if(m[2]) cikti+='<span class="st">'+kacir(m[2])+'</span>';
    else if(m[3]) cikti+='<span class="nu">'+kacir(m[3])+'</span>';
    else{{
      const k=m[4];
      if(KW_KUME.has(k))                   cikti+='<span class="kw">'+k+'</span>';
      else if(s[BELIRTEC.lastIndex]==="(") cikti+='<span class="fn">'+k+'</span>';
      else                                 cikti+=kacir(k);
    }}
    i=BELIRTEC.lastIndex;
  }}
  return cikti+kacir(s.slice(i));
}}
function ciz(metin, eski){{
  const s=metin.split("\\n"), e=(eski||"").split("\\n");
  let h='<table>';
  for(let i=0;i<s.length;i++){{
    const yeni = eski!==undefined && e[i]!==s[i];
    h+='<tr><td class="n">'+(i+1)+'</td><td class="s'+(yeni?' degisti':'')+'">'+
       (renkle(s[i])||"&nbsp;")+'</td></tr>';
  }}
  return h+'</table>';
}}
/* FARK GORUNUMU: denetleyenin asil sorusu "ne yazdi" degil "NE DEGISTIRDI"dir. Ayni dosya
   onarim turlarinda birkac kez yazilir; her 'write' olayi bir SURUMDUR. Kod kipinde eski bir
   surumun tam hali, fark kipinde iki surum arasi degisiklik gosterilir. */
let son=null, pano="", kip="kod", surumler=[], secim=0, cizilenSel="", farkImza="";
function el(k){{return document.getElementById(k)}}
function selYaz(){{
  const s=el("surumSec"), n=surumler.length, imza=kip+":"+n;
  if(imza===cizilenSel) return;                 // her yoklamada listeyi bozma (secim ucar)
  cizilenSel=imza;
  let h="";
  if(!n){{ s.style.display="none"; s.innerHTML=""; return; }}
  s.style.display="";
  if(kip==="kod") h='<option value="0">güncel (diskten)</option>';
  for(let i=n;i>=1;i--){{
    const k=surumler[i-1];
    const et = kip==="kod" ? ("sürüm "+i+" · "+k.satir+" satır")
                           : (i>1 ? ("sürüm "+(i-1)+" → "+i) : "sürüm 1 (ilk yazım)");
    h+='<option value="'+i+'">'+et+'</option>';
  }}
  s.innerHTML=h;
  s.value=String(secim);
  if(s.selectedIndex<0) s.selectedIndex=0;
}}
async function surumleriCek(){{
  try{{
    const r=await(await fetch("/api/dosya_surumler?is="+encodeURIComponent(IS)+
                              "&yol="+encodeURIComponent(YOL))).json();
    surumler = (r && r.surumler) || [];
  }}catch(e){{ surumler=[]; }}
  if(kip==="fark" && (!secim || secim>surumler.length)) secim=surumler.length;
  selYaz();
}}
function farkCiz(r){{
  let h='<table>', duz=[];
  (r.satirlar||[]).forEach(s=>{{
    if(s.tur==="@"){{
      h+='<tr><td class="n">⋯</td><td class="s atla">'+kacir(s.metin)+'</td></tr>';
      duz.push("  "+s.metin); return;
    }}
    const c = s.tur==="+" ? "ek" : (s.tur==="-" ? "sil" : "");
    const im = s.tur==="+" ? "+" : (s.tur==="-" ? "−" : " ");
    const no = s.tur==="-" ? s.a : s.b;
    h+='<tr><td class="n '+c+'">'+(no||"")+'</td><td class="s '+c+'"><span class="im '+c+'">'+
       im+'</span>'+(renkle(s.metin)||"&nbsp;")+'</td></tr>';
    duz.push(im+" "+s.metin);
  }});
  pano=duz.join("\\n");
  return h+'</table>';
}}
async function farkCek(d){{
  try{{
    const b=secim||surumler.length||1;
    const r=await(await fetch("/api/dosya_fark?is="+encodeURIComponent(IS)+
                              "&yol="+encodeURIComponent(YOL)+"&b="+b)).json();
    if(r.hata){{ d.textContent="fark yok: "+r.hata; el("kod").innerHTML=""; el("ozet").textContent=""; return; }}
    const imza=r.a+"/"+r.b+"/"+r.eklenen+"/"+r.silinen+"/"+(r.satirlar||[]).length;
    if(imza!==farkImza){{ farkImza=imza; el("kod").innerHTML=farkCiz(r); }}
    el("ozet").innerHTML='<span class="art">+'+r.eklenen+'</span> <span class="eks">−'+r.silinen+'</span>';
    d.textContent = r.ilk_yazim ? ("ilk yazım · sürüm "+r.b+"/"+r.toplam_surum)
                                : ("sürüm "+r.a+" → "+r.b+" · "+r.toplam_surum+" sürüm");
  }}catch(e){{ d.textContent="bağlantı yok"; }}
}}
async function cek(){{
  const d=el("durum");
  await surumleriCek();
  if(kip==="fark") return farkCek(d);
  try{{
    const u="/api/dosya?is="+encodeURIComponent(IS)+"&yol="+encodeURIComponent(YOL)+
            (secim?"&surum="+secim:"");
    const r=await(await fetch(u)).json();
    if(r.hata){{d.textContent="hata: "+r.hata; return}}
    if(r.icerik!==son){{
      const eski=son;
      el("kod").innerHTML=ciz(r.icerik, eski===null?undefined:eski);
      son=r.icerik; pano=r.icerik; el("ozet").textContent="";
      d.textContent=(r.satir||0)+" satır · "+(r.bayt||0)+" bayt"+
        (r.kaynak?" · "+r.kaynak:"")+(eski!==null?" · güncellendi":"");
    }}
  }}catch(e){{d.textContent="bağlantı yok"}}
}}
function sifirla(){{ son=null; farkImza=""; el("kod").innerHTML=""; cek(); }}
/* PENCERE DENETIMI: kabuk bu pencereyi CERCEVESIZ acar (Windows baslik cubugu yok), bu
   yuzden tasima/kapatma/ustte-tutma BURADAN yonetilir. Yasandi: goruntuleyiciye bu serit
   eklenmemisti - pencere ne kapatilabiliyor ne tasinabiliyordu. */
const KABUK = !!(window.chrome && window.chrome.webview);
const yolla = m => {{ try{{ window.chrome.webview.postMessage(m); }}catch(e){{}} }};
(function(){{
  const bar=document.querySelector("header");
  let sx=0, sy=0, tut=false;
  bar.addEventListener("pointerdown", e=>{{
    if(e.target.closest(".pdug")||e.target.closest("button")||e.target.closest("label")||
        e.target.closest("select")) return;
    tut=true; sx=e.screenX; sy=e.screenY; bar.setPointerCapture(e.pointerId);
  }});
  bar.addEventListener("pointermove", e=>{{
    if(!tut) return;
    const dx=e.screenX-sx, dy=e.screenY-sy;
    if(dx||dy){{ sx=e.screenX; sy=e.screenY; if(KABUK) yolla("tasi:"+dx+","+dy); }}
  }});
  const birak=e=>{{ if(!tut)return; tut=false;
    try{{bar.releasePointerCapture(e.pointerId)}}catch(_){{}} }};
  bar.addEventListener("pointerup", birak);
  bar.addEventListener("pointercancel", birak);
  bar.addEventListener("dblclick", e=>{{ if(!e.target.closest(".pdug")&&KABUK) yolla("buyult"); }});
  let ustte=false;
  document.getElementById("pUstte").onclick=()=>{{
    ustte=!ustte;
    document.getElementById("pUstte").classList.toggle("etkin",ustte);
    if(KABUK) yolla("ustte:"+(ustte?"1":"0"));
  }};
  document.getElementById("pBuyult").onclick=()=>{{ if(KABUK) yolla("buyult"); }};
  document.getElementById("pKapat").onclick=()=>{{ if(KABUK) yolla("kapat"); else window.close(); }};
  if(!KABUK) document.getElementById("pBuyult").style.display="none";
}})();
document.getElementById("yenile").onclick=cek;
document.getElementById("kopyala").onclick=()=>navigator.clipboard.writeText(pano||son||"");
el("bKip").onclick=()=>{{
  kip = kip==="kod" ? "fark" : "kod";
  const b=el("bKip");
  b.textContent = kip==="kod" ? "± fark" : "📄 kod";
  b.classList.toggle("etkin", kip==="fark");
  secim = kip==="fark" ? (surumler.length||0) : 0;
  cizilenSel=""; selYaz(); sifirla();
}};
el("surumSec").onchange=e=>{{ secim=parseInt(e.target.value||"0",10)||0; sifirla(); }};
setInterval(()=>{{if(document.getElementById("oto").checked)cek()}},2000);
cek();
</script></body></html>"""


def sayfa(jid: str, yol: str) -> str:
    ad = os.path.basename(yol) or "dosya"
    kacir = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return SAYFA.format(ad=kacir(ad), bilgi=kacir("%s · %s" % (yol, jid[:15])),
                        is_json=json.dumps(jid), yol_json=json.dumps(yol))


def _yol_gecerli(yol: str) -> str:
    """Calisma alani disina cikan yollari reddet; temizlenmis yolu doner ('' = gecersiz)."""
    yol = (yol or "").replace("\\", "/").strip("/")
    if not yol or ".." in yol.split("/") or os.path.isabs(yol) or os.path.splitdrive(yol)[0]:
        return ""
    return yol


def surumler(jobs_dir: str, jid: str, yol: str) -> dict:
    """Bir dosyanin O ISTEKI TUM SURUMLERI: her 'write' olayi bir surumdur.

    Neden: denetleyenin sorusu "ne yazdi" degil "NE DEGISTIRDI"dir. Onarim turlarinda ayni
    dosya birkac kez yazilir; hangi turda neyin degistigini gormek dogrulamanin kendisidir.
    Icerikler burada DONMEZ (buyuk olabilir) - yalniz kunye; icerik /api/dosya?surum=N ile."""
    yol = _yol_gecerli(yol)
    if not yol:
        return {"hata": "gecersiz yol"}
    out = []
    try:
        with open(os.path.join(jobs_dir, jid, "events.jsonl"), encoding="utf-8",
                  errors="replace") as f:
            for satir in f:
                if '"write"' not in satir:
                    continue
                try:
                    e = json.loads(satir)
                except Exception:
                    continue
                if e.get("type") != "write" or (e.get("path") or "").replace("\\", "/") != yol:
                    continue
                icerik = e.get("after") or ""
                out.append({"t": e.get("t") or 0, "satir": icerik.count("\n") + 1,
                            "bayt": len(icerik.encode("utf-8"))})
    except OSError:
        return {"hata": "olay dosyasi yok"}
    for i, s in enumerate(out):
        s["no"] = i + 1
    return {"surumler": out}


def _surum_icerik(jobs_dir: str, jid: str, yol: str, no: int) -> str | None:
    """no. surumun (1'den baslar) tam icerigi; yoksa None."""
    bulunan, sayac = None, 0
    try:
        with open(os.path.join(jobs_dir, jid, "events.jsonl"), encoding="utf-8",
                  errors="replace") as f:
            for satir in f:
                if '"write"' not in satir:
                    continue
                try:
                    e = json.loads(satir)
                except Exception:
                    continue
                if e.get("type") != "write" or (e.get("path") or "").replace("\\", "/") != yol:
                    continue
                sayac += 1
                if sayac == no:
                    bulunan = e.get("after") or ""
                    break
    except OSError:
        return None
    return bulunan


def fark(jobs_dir: str, jid: str, yol: str, a: int = 0, b: int = 0) -> dict:
    """Iki surum arasindaki FARK (stdlib difflib; ek bagimlilik yok).

    a=0 ise 'b'nin bir oncesi, b=0 ise SON surum kullanilir. Ilk surumun farki, dosyanin
    sifirdan yazilmis hali olarak gosterilir (tumu eklenmis gorunur - dogrusu budur).
    Doner: satir listesi [{tur: ' '|'+'|'-'|'@', metin, a_no, b_no}] + ozet sayilar."""
    import difflib
    yol = _yol_gecerli(yol)
    if not yol:
        return {"hata": "gecersiz yol"}
    kunye = surumler(jobs_dir, jid, yol)
    if kunye.get("hata"):
        return kunye
    n = len(kunye["surumler"])
    if n == 0:
        return {"hata": "bu dosyanin yazim kaydi yok"}
    b = b or n
    b = max(1, min(n, b))
    a = a or (b - 1)
    a = max(0, min(n, a))
    yeni = _surum_icerik(jobs_dir, jid, yol, b) or ""
    eski = (_surum_icerik(jobs_dir, jid, yol, a) or "") if a >= 1 else ""
    es, ys = eski.splitlines(), yeni.splitlines()
    satirlar, eklenen, silinen = [], 0, 0
    esles = difflib.SequenceMatcher(None, es, ys, autojunk=False)
    for etiket, i1, i2, j1, j2 in esles.get_opcodes():
        if etiket == "equal":
            # Baglam: degisikligin cevresinde 3 satir goster, aradaki uzun bloklari KATLA
            blok = list(range(i1, i2))
            if len(blok) <= 7:
                for k in blok:
                    satirlar.append({"tur": " ", "metin": es[k], "a": k + 1, "b": j1 + (k - i1) + 1})
            else:
                for k in blok[:3]:
                    satirlar.append({"tur": " ", "metin": es[k], "a": k + 1, "b": j1 + (k - i1) + 1})
                satirlar.append({"tur": "@", "metin": "… %d satır değişmedi" % (len(blok) - 6),
                                 "a": 0, "b": 0})
                for k in blok[-3:]:
                    satirlar.append({"tur": " ", "metin": es[k], "a": k + 1, "b": j1 + (k - i1) + 1})
        else:
            for k in range(i1, i2):
                satirlar.append({"tur": "-", "metin": es[k], "a": k + 1, "b": 0})
                silinen += 1
            for k in range(j1, j2):
                satirlar.append({"tur": "+", "metin": ys[k], "a": 0, "b": k + 1})
                eklenen += 1
    return {"satirlar": satirlar[:4000], "eklenen": eklenen, "silinen": silinen,
            "a": a, "b": b, "toplam_surum": n,
            "ilk_yazim": a == 0,
            "kunye": kunye["surumler"]}


def oku(jobs_dir: str, jid: str, yol: str, surum: int = 0) -> dict:
    """Dosyanin GUNCEL icerigi: once diskten (model sonradan degistirmis olabilir),
    bulunamazsa olay akisindaki son 'write' kaydindan.
    surum>0 verilirse O SURUMUN icerigi (fark gorunumunden secilebilsin diye)."""
    if surum:
        temiz = _yol_gecerli(yol)
        if not temiz:
            return {"hata": "gecersiz yol"}
        ic = _surum_icerik(jobs_dir, jid, temiz, surum)
        if ic is None:
            return {"hata": "surum yok"}
        return {"icerik": ic, "satir": ic.count(chr(10)) + 1,
                "bayt": len(ic.encode("utf-8")), "kaynak": "surum %d" % surum}
    yol = (yol or "").replace("\\", "/").strip("/")
    if not yol or ".." in yol.split("/") or os.path.isabs(yol) or os.path.splitdrive(yol)[0]:
        return {"hata": "gecersiz yol"}
    try:
        with open(os.path.join(jobs_dir, jid, "job.json"), encoding="utf-8") as f:
            kayit = json.load(f)
    except Exception:
        return {"hata": "is bulunamadi"}
    kok = kayit.get("calisma_dizini") or ""
    if kok:
        tam = os.path.realpath(os.path.join(kok, yol))
        kok_ger = os.path.realpath(kok)
        if tam.startswith(kok_ger + os.sep) and os.path.isfile(tam):
            try:
                with open(tam, encoding="utf-8", errors="replace") as f:
                    icerik = f.read()[:400000]
                return {"icerik": icerik, "satir": icerik.count("\n") + 1,
                        "bayt": os.path.getsize(tam), "kaynak": "disk"}
            except OSError:
                pass
    son = None
    try:
        with open(os.path.join(jobs_dir, jid, "events.jsonl"), encoding="utf-8",
                  errors="replace") as f:
            for satir in f:
                if '"write"' not in satir:
                    continue
                try:
                    e = json.loads(satir)
                except Exception:
                    continue
                if e.get("type") == "write" and (e.get("path") or "").replace("\\", "/") == yol:
                    son = e.get("after")
    except OSError:
        pass
    if son is None:
        return {"hata": "dosya bulunamadi"}
    return {"icerik": son, "satir": son.count("\n") + 1,
            "bayt": len(son.encode("utf-8")), "kaynak": "olay"}

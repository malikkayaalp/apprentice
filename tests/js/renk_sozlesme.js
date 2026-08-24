/* Bu dosya testin icine gomulur: iki vurgulayici da (panel `renklendir`, goruntuleyici
   `renkle`) ayni SOZLESMEYE uyar.
     1) Cizilen metin kaynagin AYNISI olmali (etiketler soyulup varliklar cozulunce).
     2) Etiket kacagi olmamali - ham `class="st">` ekrana dokulmemeli.
     3) Kaynaktaki < > & KACIRILMIS olmali; kendi <span>'larimiz disinda ham etiket kalmamali.
     4) Acilan/kapanan span sayisi esit, ic ice bozuk etiket ("<span <span") yok.

   YASANDI: dizge gecisi <span class="st"> yaziyor, ardindan anahtar kelime gecisi KENDI
   yazdigi etiketin icindeki 'class' kelimesini boyuyordu ('class' anahtar kelime listesinde)
   -> HTML parcalandi, ekrana `class="st">""class="st">"Bos liste...` dokuldu. */
const ORNEKLER = [
  '    """Bos liste 0.0 doner - ZeroDivisionError yerine."""',
  '    raise ValueError("not ve agirlik sayisi ayni olmali")',
  '    return "FF"',
  "    ad = 'AA'",
  '    # yorum "tirnakli" ve class kelimeli',
  '    print("class def return if")',
  '    if a < b and c > d: pass',
  '    if x < y and "a>b" or z & 1: pass',
  '    html = "<span class=\\"st\\">"',
  '    yorum = "<!-- & -->"',
  '    x = {"a": 1, "b": 2.5}',
  '    bos = ""',
  '',
  '    def f(x): return x',
];
function dene(ad, fn){
  for(const o of ORNEKLER){
    const c = String(fn(o));
    // KENDI etiketlerimizi soy - geriye ham etiket kalmamali
    const cip = c.replace(/<span class="[a-z-]+">/g, "").replace(/<\/span>/g, "");
    if(/[<>]/.test(cip))
      throw new Error(ad+": HAM < veya > kacirilmamis (bozuk isaretleme / XSS riski)"+
                      "\n  kaynak: "+JSON.stringify(o)+"\n  ham   : "+JSON.stringify(c));
    if(/class="/.test(cip))
      throw new Error(ad+": ETIKET KACAGI - ham class= ekrana dokuluyor"+
                      "\n  ham   : "+JSON.stringify(c));
    if(/<span\s+<span/.test(c))
      throw new Error(ad+": IC ICE BOZUK ETIKET\n  ham   : "+JSON.stringify(c));
    const ac = (c.match(/<span /g)||[]).length, kap = (c.match(/<\/span>/g)||[]).length;
    if(ac !== kap)
      throw new Error(ad+": span dengesiz ("+ac+" acilis, "+kap+" kapanis)"+
                      "\n  ham   : "+JSON.stringify(c));
    // varliklari coz - sonuc kaynagin TAM AYNISI olmali
    const geri = cip.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
                    .replace(/&#39;/g, "'").replace(/&amp;/g, "&");
    if(geri !== o)
      throw new Error(ad+": METIN BOZULDU\n  kaynak: "+JSON.stringify(o)+
                      "\n  geri  : "+JSON.stringify(geri)+"\n  ham   : "+JSON.stringify(c));
  }
}

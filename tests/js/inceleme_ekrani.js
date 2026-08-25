/* INCELEME EKRANI cizim sozlesmesi. Testin icine gomulur.

   incelemeCiz kullanicinin isten sonra GORDUGU tek ekran. Sozdizimi testi "gecerli JS mi"
   der, id testi "aranan oge var mi" der - ama ikisi de bu fonksiyonun DOGRU SEYI cizdigini
   soylemez. Burada gercekten kosturulup ciktisi denetlenir.

   En kritik madde 4: dosya yollari MODELDEN gelir. Kacirilmazsa cirak yazdigi dosyanin
   adiyla panele kod sokabilir. */
function ONAY(k, a) { if (!k) throw new Error("SOZLESME: " + a); }

const OZET = {
  sema: 1, is_id: "is1", durum: "bitti",
  baslik: "Login token yenileme hatasini duzelt",
  calisma_dizini: "C:\\Projeler\\MyGame",
  yazma_kapsami: { liste: ["auth/"], sinirli: true, aciklama: "yalniz bu yollar" },
  zemin: { git: true, dal: "feature/login", basta_kirli: 2 },
  degisen_dosyalar: [
    { yol: "auth/token.py", eklenen: 18, silinen: 4, surum: 3, yeni: false, kapsam_disi: false },
    { yol: "kayit/gunluk.py", eklenen: 9, silinen: 0, surum: 1, yeni: true, kapsam_disi: true },
  ],
  dogrulama: [
    { ad: "derleme", durum: "gecti", kanit: "hata yok" },
    { ad: "ruff", durum: "kaldi", kanit: "1 uyari" },
    { ad: "yazma kapsami", durum: "kaldi", kanit: "1 dosya kapsam disi" },
  ],
  onarim_turu: 2, sure: 118,
  duraganlik: { var: true, imza_sayisi: 1, tur: 2 },
  devir_onerisi: {
    var: true, sebep: "duraganlik",
    kanit: ["ayni hata imzasi 2 tur ust uste (imza: 1)", "onarim turunda ilerleme yok"],
    son_hata: "test_login_refresh\nExpected: ACTIVE\nActual: EXPIRED",
  },
  uyarilar: ["a.py:3:1: F401 os imported but unused"],
  kullanim: { prompt_tokens: 8421 },
  geri_alinabilir: { mumkun: true, yontem: "git", sebep: "butun degisiklikler kayitli",
                     eylem_sayisi: 2, atlanan: [] },
  karar: {},
};

function ciz(ozet) { incelemeCiz(ozet); return _o["ozetKutu"].innerHTML; }

// 1) DEVIR ONERISI VARSA: baslik uyariya doner ve KANIT gorunur
let h = ciz(OZET);
ONAY(/USTA ÖNERİLİYOR/.test(h), "devir onerisi varken baslik uyarmiyor");
ONAY(/duraganlik/.test(h), "devir SEBEBI yok");
ONAY(/ayni hata imzasi 2 tur/.test(h), "devir KANITI yok");
ONAY(/EXPIRED/.test(h), "son hata gosterilmiyor");
// devir kutusu DOSYA listesinden ONCE gelmeli (onem sirasi)
ONAY(h.indexOf("duraganlik") < h.indexOf("auth/token.py"), "devir kutusu dosyalardan sonra");

// 2) DOSYALAR: net fark, yeni/kapsam disi rozetleri
ONAY(/\+18/.test(h) && /−4/.test(h), "net fark sayilari yok");
ONAY(/3 sürüm/.test(h), "surum sayisi yok");
ONAY(/yeni/.test(h), "'yeni' rozeti yok");
ONAY(/kapsam dışı/.test(h), "'kapsam disi' rozeti yok");

// 3) DOGRULAMA: gecen ve KALAN ayirt edilmeli, kalanin kaniti EKRANDA
ONAY(/incDog gecti/.test(h), "gecen kontrol isaretlenmemis");
ONAY(/incDog kaldi/.test(h), "kalan kontrol isaretlenmemis");
ONAY(/1 dosya kapsam disi/.test(h), "kalan kontrolun kaniti ekranda degil");

// 4) ZEMIN + KAPSAM
ONAY(/feature\/login/.test(h), "dal gosterilmiyor");
ONAY(/auth\//.test(h), "yazma kapsami gosterilmiyor");
ONAY(/2 onarım turu/.test(h), "onarim turu yok");
ONAY(/geri alınabilir/.test(h), "geri alinabilirlik yok");

// 5) SINIRSIZ KAPSAM: "gecti" gibi YESIL degil, UYARI olarak gosterilmeli
let h2 = ciz(Object.assign({}, OZET, {
  yazma_kapsami: { liste: [], sinirli: false, aciklama: "calisma alaninin tamami" } }));
ONAY(/incSari/.test(h2), "sinirsiz kapsam uyari olarak gosterilmiyor");
ONAY(/sınır yok/.test(h2), "sinirsiz kapsam metni yok");

// 6) CALISIYOR: bitmemis iste devir/geri alma HUKMU verilmemeli
let h3 = ciz(Object.assign({}, OZET, { durum: "calisiyor" }));
ONAY(/ÇALIŞIYOR/.test(h3), "calisan is 'calisiyor' demiyor");
ONAY(!/geri alınabilir/.test(h3), "bitmemis iste geri alma hukmu verildi");

// 7) DEVIR YOKSA sade baslik
let h4 = ciz(Object.assign({}, OZET, { devir_onerisi: { var: false, kanit: [] } }));
ONAY(/İŞ TAMAMLANDI/.test(h4), "devirsiz iste baslik yanlis");
ONAY(!/USTA ÖNERİLİYOR/.test(h4), "devir yokken uyari cikti");

// 8) BOS/HATALI sozlesme: patlamamali
incelemeCiz(null);
incelemeCiz({ hata: "is bulunamadi" });
ONAY(/bulunamadi/.test(_o["ozetKutu"].innerHTML), "hata mesaji gosterilmiyor");
incelemeCiz(Object.assign({}, OZET, { degisen_dosyalar: [], dogrulama: [], uyarilar: [] }));

// 9) KACIS - EN KRITIK. Dosya yolu MODELDEN gelir; kacirilmazsa panele kod sokulur.
const KOTU = '<img src=x onerror=alert(1)>"\'</div>';
let h5 = ciz(Object.assign({}, OZET, {
  degisen_dosyalar: [{ yol: KOTU, eklenen: 1, silinen: 0, surum: 1, yeni: false,
                       kapsam_disi: false }],
  calisma_dizini: KOTU,
  devir_onerisi: { var: true, sebep: KOTU, kanit: [KOTU], son_hata: KOTU },
}));
// Dogru kural: girdideki "<" KACIRILMIS olmali. "onerror=" metninin ciktida METIN
// olarak gorunmesi zararsizdir - etiket acilamadigi surece calismaz. Ilk yazdigim
// beklenti bunu ayirt etmiyordu ve YANLIS ALARM verdi.
ONAY(!/<img /.test(h5), "DOSYA YOLU KACIRILMAMIS - panele etiket sokulabiliyor");
ONAY(!h5.includes(KOTU), "ham girdi dizgesi ciktida AYNEN duruyor");
ONAY(/&lt;img/.test(h5), "kacirilmis hali bulunamadi");
// data-yol ozniteligi: icinde HAM tirnak olmamali, yoksa oznitelikten cikilir
const oznitelikler = [...h5.matchAll(/data-yol="([^"]*)"/g)].map(m => m[1]);
ONAY(oznitelikler.length > 0, "data-yol ozniteligi hic uretilmemis");
for (const d of oznitelikler) {
  ONAY(!d.includes('"') && !d.includes("<"), "oznitelik icinde ham tirnak/etiket: " + d);
}

console.log("INCELEME-EKRANI-OK");

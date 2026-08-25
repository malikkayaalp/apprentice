# STATE.md — iş devri (en yeni üstte; kendi OpenMemory kuralımızın bu depoya uygulanması)

## 2026-08-25 (3): DIS DENETIM - 14 madde, alti faz, hepsi kapandi

Kullanicidan 14 maddelik ikinci bir denetim listesi geldi. Once DOGRULANDI (kod okunarak,
iddiaya guvenilmeden): **13'u gercek, 1'i kismen**. Hicbiri asilsiz degildi. Sonra kullanici
onayiyla alti faza bolunup uygulandi.

### Sirayi kullanici belirledi, bir noktada BEN degistirdim
Madde 13'u (gizlilik) ikinci gruptan alip EN BASA cektim: diger 12 madde POTANSIYEL zarar,
bu madde o an GERCEKLESIYORDU - v0.4.0 bir saat once yayinlanmisti ve README "kodunuz
makineden cikmaz" diyordu. Kullanici kabul etti ve ONEMLI BIR DUZELTME yapti:
**"diff de kaynak koddur"** - tam dosya yerine fark gondermek iddiayi DOGRU YAPMAZ.
Bu yuzden hem miktar kisildi hem ifade duzeltildi; ikisi tek is olarak yapildi.
Ayrica 7'yi 6'dan once yaptim: guvenilir iptal olmadan guvenli yeniden baslatma yazilamaz.

### FAZ 1 - madde 13 (gizlilik)
`report()` her yazilan dosyanin TAM son icerigini (<=12000 karakter) ustaya gonderiyordu.
`core/gizlilik.py`: varsayilan yalnizca SINIRLI + MASKELI fark; tam icerik acikca acilir
(`gizlilik.tam_icerik`). Maskeleme DAR tutuldu - genis desen normal kodu maskeleyip
DENETCIYI KOR EDER. Denetci kurali (kur.py) da `fark` okuyacak sekilde degisti; README ve
server/README kosulsuz iddiayi biraktı. Panel USTA panosunda GERCEK ayari gosteriyor.

### FAZ 2 - maddeler 1, 2 (ek guvenligi, geri alma)
Ekler proje klasorune adiyla yaziliyor ve ayni adli dosyayi SESSIZCE eziyordu; ustelik
anlik goruntuden ONCE oldugu icin geri alma da kurtaramiyordu (uc kat zarar). Artik
`<HOME>/jobs/<id>/ekler/` - calisma agacinin DISI. Hapse DAR bir OKUMA izni eklendi
(`Jail.oku_yolu`); yazma hapsi HIC degismedi.
Geri almada DORT ayri kusur: kayitli baslangic HEAD'i HIC OKUNMUYORDU · `git checkout`
indeksten geri yaziyordu · bitis ani `usta_rapor` yuzunden ILERI kayiyordu · porcelain
ayristirmasi Unicode/yeniden adlandirmayi bozuyordu (`-z` ile duzeldi).
**Denenip birakildi:** `git show <head>:<yol>` + ham bayt yazma. `git show` BLOB verir,
satir sonu suzgeclerini uygulamaz - dosya hala "degismis" gorunuyor ve ikinci geri alma
onu tekrar yakaliyordu. MEVCUT senaryo testi yakaladi. Dogrusu `git checkout <bas_head>`.

### FAZ 3 - maddeler 7, 6 (iptal, yeniden baslatma)
`kill()` taskkill'in DONUS KODUNU okumadan kosulsuz `return` ediyordu. Artik sonuc doner
(surec_yok | zaten_bitmis | durduruldu | DURMADI), taskkill basarisizsa proc.kill()'e
dusulur ve olum SINIRLI BEKLEMEYLE DOGRULANIR.
Yeniden baslatma `os._exit(0)` cagiriyordu: isci alt surecleri olmuyordu, yeni kuyruk eski
isi "yarim" sayip sıradakini baslatiyordu - IKI YAZAN, TEK PROJE. Artik once durdurulur,
durdugu dogrulanir; durduramazsa YENIDEN BASLATMAZ. Cokme kurtarma uc hali ayirir:
bitmis / HALA CALISIYOR (sahipsiz, kuyruk yeni is baslatmaz) / gercekten yarim.
`JOBS` sozlugu sinirsiz buyuyordu - budandi (BITMEMIS is asla dusurulmez).

### FAZ 4 - madde 3 (dogrulanmamis basari)
`degerlendir()` yalnizca "kaldi"ya bakiyordu; `_kabul_satiri` denetlenmemis kritere "yok"
yazar - yani is TEMIZ sayiliyordu. Telemetride duzelttigimiz "%100 vs gercek %81,6" yalani
POLITIKA KAPISINDAN geri giriyordu. Artik DORT DEGERLI: temiz | kaldi | dogrulanmadi |
bilinmiyor. "temiz" POZITIF KANIT ister.
Iki hata daha: `_kuyruk_bitti_mi` BULUNAMAYAN isi BITMIS sayiyordu (`durum` alani yok ->
"" != "calisiyor"); kuyruk politika istisnasini yutup devam ediyordu.

### FAZ 5 - maddeler 4, 5, 10
`sampling.*` ve `prompt.ek_talimat` sablonda vardi, HIC OKUNMUYORDU. `core/ayarlar.py`
eklendi: deger + KAYNAK + uyari + tip/sinir denetimi. Guvenli varsayilanlar KORUNDU
(kullanici karari), riskli deger ENGELLENMEZ ama UYARILIR. Kampanyalar KILITLI olcum
profiliyle kosuyor.
Baglam kesilmesi `client.py`'de uretiliyor ama HIC OKUNMUYORDU; canli/XML yolunda tespit
HIC YOKTU. Ikisi de kapatildi; toplam istem ile TEK ISTEKTEKI en buyuk istem AYRILDI.
Kuyruk yazma hatasi yutuluyordu ("eklendi" deniyordu); bozuk dosya sessizce BOS kuyruga
donuyordu. Ikisi de gorunur; bozuk icerik `.bozuk-<zaman>` olarak KORUNUYOR.

### FAZ 6 - maddeler 8, 9, 11, 12, 14
Canli rapor turlari TOPLUYORDU, disk raporu NET hesapliyordu: ayni dosya uc kez yazilip
basa donunce "+2 -2" vs "+0 -0". Ikisi NET farka esitlendi (`yazma` alani kac kez
yazildigini ayrica soyler).
Zaman cizgisi son aractan sonrasini HEP "dogrulama" sayiyordu; ARACSIZ iste surenin TAMAMI
dogrulama gorunuyordu (60 sn uretim -> 60 sn "dogrulama"). `assistant` olayi artik
dogrulamanin BASLANGIC SINIRI; yoksa "bilinmiyor" denir, uydurma yapilmaz. Gosterim siniri
ACIKCA bildiriliyor.
Sohbet kilidi model cagrisi boyunca birakiliyordu - alisveris artik BOLUNMEZ; sifirlama
icin NESIL sayaci (ucustaki cevap yeni gecmise EKLENMEZ).
`--tek`: `SadeceSunucu` sonuc dondurmuyordu, basarisizlikta bile pencere aciliyordu. Artik
`Task<bool>`, kismen baslatilmis surec temizleniyor, pencere ACILMIYOR.
server/README calisma kokunun UC yolunu da anlatiyor (iddia edilen "sessiz geri donus"
zaten giderilmisti - madde 14 KISMEN dogruydu).

### EN ONEMLI DERS: kendi testlerim UC KEZ guvensiz davranisi SOZLESME diye cakmisti
  - "bilinmiyor durumda kuyruk devam etsin"      (test_politika)
  - "patlayan politika kuyrugu durdurmasin"      (test_kuyruk)
  - "tam dosya icerigi ustaya gitsin"            (test_server)
O fazlarda YESIL TEST KANIT DEGILDI - duzeltilecek seyin parcasiydi. Bu yuzden her madde
icin ayrica GERILEME KANITI alindi: duzeltme kapatilinca ilgili test GERCEKTEN dusuyor mu.

### DENENIP KALDIRILAN TEST (durustluk notu)
TDZ ("ayni islevde tanimdan once kullanim") icin statik tarayici yazildi, YANLIS ALARM
verdi (JS blok kapsamini ve ic ice islevleri gormuyor) ve KALDIRILDI. Yanlis alarm veren
test testsizlikten kotudur.
**ACIK RISK:** `node --check` TDZ hatasini YAKALAMAZ. Bu oturumda gercek ornek yasandi:
kesilme uyarisindaki `ks` adi ayni islevde daha asagida tanimli `const ks` ile cakisti;
sozdizimi testi YESIL kaldi, ekran ise kesilme yasayan HER iste cizilmezdi. Tarayicida
gercek veriyle yakalandi. Dogru cozum DOM'lu bir cizim testi - AYRI IS.

### Durum
Batarya 17 -> 22 dosya. Yeni: test_gizlilik, test_ekler, test_durdurma, test_ayarlar,
test_tutarlilik. Tam batarya 22/22, 0 KARARSIZ.
Yeni cekirdek modul: `core/gizlilik.py`, `core/ekler.py`, `core/ayarlar.py`.
Yeni ayar bolumleri: `gizlilik`, `politika`, ve gercekten okunan `sampling`/`prompt`.

**Bekleyenler:** yol haritasi 8-9 (kullanici DURDURDU, esik dolmadi: 115/130 KB) ·
16 kucuk modeller (kapsam disi) · panel "ev" gecisi (kullanici istemedi) ·
DOM'lu cizim testi (TDZ boslugu).

---

## 2026-08-25 (2): YOL HARITASI 10-15 + denetim bulgulari

**Denetim bulgulari (8+2) KAPANDI.** Ikisi kritikti:

- `run_shell` calisma alani DISINA yazip okuyabiliyordu (OLCULDU, kacis kanitlandi).
  `kabuk_guvenli()` eklendi. DURUST SINIR: bu bir KORUMA, kum havuzu DEGIL - calisma
  aninda yol ureten yorumlayici asabilir. Kabuk araclari varsayilan KAPALI.
  Ilk surum FAZLA GENISTI: `sys.executable` mutlak oldugu icin HARNESS'IN KENDISINI
  engelledi (kendi testimiz yakaladi). Simdi komut parcasinin ILK belirteci (calistirilacak
  PROGRAM) muaf, ikinci belirtec degil - oradaki mutlak yol VERI'dir ve reddedilir.
- Geri alma KULLANICININ emegini siliyordu: git yolu "kim degistirdiginden bagimsiz"
  calisiyordu, yani is bittikten SONRA yapilan duzenlemeyi de kapsiyordu. Cirak a.py yazar,
  kullanici elle duzeltir, GERI AL -> `git checkout` sessizce siler. Is sonrasi olusturulan
  YENI dosya da '??' gorunup silinirdi. Iki olcut (icerik + mtime) + yikici adimin hemen
  oncesinde SON KONTROL (bayat plan uygulanmaz).

Digerleri: kampanya cikis kodu (uc degerli sozlesme), AGENTS.md ezme, Ollama adresi,
`--tek` argumanlari, JSONC yorum kaybi, README. #5 zaten kapaliymis (panel makine.num_ctx
okuyor - denetim bayat koda bakmis), #6 daha once giderilmisti.

**Yol haritasi 10-15 BITTI.** 16 (kucuk modeller) kullanici karariyla disarida; 8-9
(panel.html bolme) kullanici karariyla DURDURULDU - esik zaten dolmamisti (115 KB / 130 KB).

- **10 KUYRUK** (`core/kuyruk.py`): SERI, es zamanlilik 1 - tek GPU, num_batch olcumu
  VRAM'in sinir kaynak oldugunu gosterdi; iki is ayni anda model yuklerse toplam is AZALIR.
  Yarida kalan is SESSIZCE YENIDEN KOSTURULMAZ ("yarim" isaretlenir): o is calisma alanina
  dosya YAZMIS olabilir, tekrar kosturmak ayni dosyayi ikinci kez ezmektir. Kendi dosyasinda
  (kuyruk.json, atomik yazim) - tek yazar kurali korunur, events.jsonl'a dokunmaz.
  Arayuz: ISLER panelinin ustune serit. Dokuzuncu YUZEN panel YAPILMADI - 24x24 izgarayi ve
  yedi dizilimi yeniden dengelemek, kullanicinin kayitli duzenini bozmak demekti.
- **13 POLITIKA** (`core/politika.py`): kuyruk tek basina tehlikeli - asil risk "bir is
  kaldi" degil "bir is kaldi ve kimse durmadi". Karari MODEL VERMEZ, dogrulayicinin ciktisi
  verir (modelin "her sey harika" beyani karari degistirmez - test bunu cakiyor). Uc sinyal:
  dogrulama satirlari, yazma kapsami ihlali, DURAGANLIK. `otomatik_kabul` VARSAYILAN KAPALI -
  otomatik kabul denetciyi devreden cikarmak demek. "bilinmiyor" MESRU sonuc.
- **11 ZAMAN CIZGISI**: olaylarda zaman YOKTU (yalnizca tool_result.sure ve result.wall).
  "Bu is 55 sn surdu" biliniyordu ama "45'i model uretimi, 14'u dogrulama" bilinmiyordu.
  Emitter'a `t` eklendi - GERIYE DONUK UYUMLU: eski kayitta var=False, UYDURMA YOK.
  PROJEKSIYONDA hesaplanir, panelde degil (yoksa 'tool'/'tool_result' eslesmesini arayuze
  ogretmis olurduk ve sema degisince panel kirilirdi). Uc dilim: uretim / arac / dogrulama.
- **14 BENCHMARK UI**: `/api/olcum` + METRIKLER panelinde tablo. Yalnizca OKUR, olcum
  BASLATMAZ (olcum 20 dk surer ve GPU ister; panelden tetiklemek kullanicinin farkinda
  olmadan is baslatmasi demek). Bu sirada ARSIV OZETINDE HATA bulundu: butun turlar
  TOPLANIYORDU, iki turda cozulen gorev "4/12 + 12/12 = 16/24" gorunuyordu - kampanyanin
  kendi raporuyla CELISIYORDU. `gizli_ilk` (ilk deneme) ve `gizli` (nihai) ayrildi.
- **15 SSE**: BILDIRIM kanali, VERI kanali DEGIL. Sebep: olay akisinin istemci tarafinda
  kazanilmis yaris duzeltmeleri var (ucusta is degisirse cevabi at, imlec, dibe kilit);
  veriyi SSE'ye tasimak onlari bastan yazmak demekti. Yoklama KALDIRILMADI, SEYRELTILDI:
  bagliyken 8/12 sn, koparsa 2/4 sn. Yeniden baglanma EventSource'a birakildi (elle close()
  ussel geri cekilmeyi kaybettirir). OLCULDU: 0.40 sn bildirim (eskiden 2 sn'ye kadar).
- **12 BASIT/UZMAN**: GORUNURLUK meselesi, DAVRANIS degil - gizlenen denetimlerin degerleri
  gorev govdesine girer, basit kipte baslatilan is uzman kiptekiyle AYNI isi yapar.
  Varsayilan UZMAN: mevcut kullanicinin ekrani kendiliginden degismesin.

**Olcum sirasinda bulunan ARIZA:** Qwen3 zorluk kosusu 12 dk GPU yakti, butun gorevleri
bitirdi ve EN SON adimda `ImportError` ile coktu - o kosunun arsivi hic yazilmadi, veri
yalnizca ham gunlukte kaldi. Iki sebep: (1) arsiv importu fonksiyon icindeydi, yani en
pahali isten SONRA cozuluyordu; (2) `kaydet()` korumasizdi ve butun kosuyu goturuyordu.
Ikisi de duzeltildi - kirilacaksa BASTA kirilsin, is yanmadan.

**MODEL KIYASI (2026-08-25, tek kosu - SAMPIYON DEGISTIRILMEDI):**

| model | code (36 kontrol) | zorluk (51 kontrol) | zorluk sure |
|---|---|---|---|
| Qwen3-Coder-Next 80B (56 GB) | ilk 35/36, son 36/36 | son **50/51** (dama 11/12, iki turda da) | 760 s |
| Muse-Glimmer 30B dflash (20 GB) | ilk **36/36** | son **51/51** (dama 4/12 -> 12/12) | 1969 s |

Muse KALITEDE esit/ustun, zor gorevlerde HIZDA 2.6x yavas. Sampiyon degisikligi icin
ornek YETERSIZ (11 gorev, tek kosu). Qwen3'un dama'da DURAGANLIK imzasi var (11/12 ->
11/12, ayni hata, 2600 -> 6050 token) - politika modulu artik tam bu zinciri kesiyor.

**Testler:** 17 dosya, 17 gecti, 0 kaldi, 0 KARARSIZ. Yeni: `test_kuyruk` (7 sozlesme),
`test_politika` (6), test_panel'e kuyruk uclari + canli akis + basit/uzman,
test_inceleme'ye zaman cizgisi, test_code_env'e kabuk hapsi, test_geri_al'a kullanici
emegi + bayat plan. Kritik iki duzeltmenin testleri DUZELTME KAPALIYKEN dusuyor -
"yazdim, gecti" degil "hatayi yakaliyor" seviyesi.

**BULUNAN TUZAK:** `server/apprentice_server.py` ev dizinini ICE AKTARMA ANINDA okuyor
(modul duzeyi) - ilk import KIM yaparsa ev dizinini O belirliyor. Paneldeki sekiz cagri
yeri bu yuzden import'tan hemen once ortam degiskenini kuruyordu; kuyruk kurucusu atlayinca
isler YANLIS klasore yazildi ve tekrar-dene testi dustu. `_srv()` yardimcisi eklendi.

**Bekleyenler:** yol haritasi 8-9 (kullanici DURDURDU), 16 kucuk modeller (disarida),
panel "ev" gecisi (iki port acmak zorunda kalmamak), ~8 yerel islem PUSH EDILMEDI.

---

## 2026-08-25: INCELEME KATMANI (yol haritasi 1-7)

Panel artik yalniz gostermiyor, KARAR aldiriyor. Kod: `core/inceleme.py`, `core/geri_al.py`,
`core/telemetri.py`, panelde IS OZETI-SONUC panosu.

**Mimari karar:** panel olay semasini BILMEZ. Araya `inceleme()` projeksiyonu kondu
(`SEMA=1`). Bugun events.jsonl'den uretiliyor, yarin dugum tabanli orkestratorden
uretilecek - panel degismeyecek. Timeline<->orkestrator carpismasi bu sayede ERTELEME
yerine COZULDU.

**TEK YAZAR KURALI:** is kaydina yalniz SAHIBI yazar (`job.json` -> `sahip: {rol, pid}`).
Panel, sahibi olmadigi MCP islerine `usta_rapor` ekliyordu: iki surec ayni dosyaya append
(Windows'ta satir yirtilabilir) + yazilan sey UYDURMA kanitti ("ustaya rapor gitti" - usta
hic bakmamis olabilir). Inceleyenin karari AYRI dosyada: `inceleme.json`.

**GERI ALMA uc yontemli:** git (is baslarken HEAD + kirli liste; `run_shell`'in gunluge
girmeden yaptigi degisiklik de kapsanir) -> gunluk (kabuk kosmadiysa) -> yok (sebebi
yazilir). Kullanicinin KENDI degisikligine ve is bittikten SONRA degismis dosyaya
DOKUNULMAZ. `git reset --hard`/`git clean` KULLANILMAZ. Once PLAN, sonra onay, sonra uygula.

**TELEMETRI:** `python -m core.telemetri`. Deterministik hata taksonomisi (regex, MODEL YOK);
"bilinmeyen" mesru bir siniftir ve orani %25'i asarsa uyarir. Sahte veri elenir
(`kaynak="ornek"`, `ortam="fake"`). ILK OLCUM: 9 gercek is, hepsi ilk turda gecmis -
**elde basarisizlik verisi YOK**, taksonomi sahada sinanmadi.

**Denenip ELENENLER (kutuphane):** portalocker (sahiplik kilitle degil KAYITLA cozuldu),
msgspec (SEMA + sozlesme testi var), pluggy (`envs/<ad>/env.json` zaten var), tree-sitter
(harita'nin kazandirdigi olculmedi), RapidFuzz (duraganlik TAM imza esitligi kullaniyor).
ALINAN: Hypothesis (gelistirme bagimliligi). Bagimlilik yerine ucuz yol: pathspec ->
`git check-ignore`, junitparser -> `--junitxml` + stdlib `xml.etree`.

**Bu katmanda bulunan GERCEK hatalar** (hepsi test tarafindan, kullaniciya gitmeden):
- `os.kill(pid, 0)` CREATE_NO_WINDOW altinda `WinError 87` veriyor -> canlilik denetimi
  uretimde HER isi oksuz gosterirdi. ctypes/OpenProcess'e cevrildi.
- `ntpath.join("D:/ws", "a/C:") == "C:"` -> goruntuleyici yol korumasinda kacis (Hypothesis
  400 uretilmis girdide buldu).
- Olay satiri `null` ise `.get()` cokuyordu; `kullanim` dizge ise telemetri cokuyordu.
- Panel sureci BAYATLIYOR: panel.html diskten taze, panel.py surece bir kez yuklu. Artik
  alti kaynagin ICERIK ozeti karsilastirilir, seritte "SUNUCUYU YENIDEN BASLAT" dugmesi var.

**Bekleyenler:** yol haritasi 8+ (testleri HTML'den bagimsizlastir -> panel.html'i bol ->
kuyruk -> timeline -> preset -> policy -> benchmark UI -> SSE -> kucuk modeller).
8-9 ERTELENDI, tetikleyici: dosya ~130 KB'i gecerse ya da CSS cakismasindan ikinci hata
cikarsa. README bu katmani ANLATMIYOR - guncellenmeli.

## 2026-08-24 (gece 4): WebView2 native kabuk + panel cerceveye sigiyor

**Kabuk (urunlesme adim 1):** shell/ApprenticePanel - C#/WinForms + WebView2. panel.html
DEGISMEDI; yalniz kabuk. Kendi ikonu (assets/apprentice.ico, bagimliliksiz uretildi), kendi
gorev cubugu kimligi, adres cubugu yok, pencere boyutu/konumu hatirlanir, kapaninca KENDI
baslattigi sunucuyu durdurur (baskasininkine dokunmaz). Yabanci baglantilar varsayilan
tarayiciya gider - kabuk tarayici degildir.
OLCUM: sicak acilis **0.6 sn** (Edge --app: ~8 sn ilk acilis), soguk 5.9 sn (tek dosya acilimi
+ profil); bellek 569 MB (kabuk 152 + webview 386 + sunucu 31) - Edge --app 378 MB idi, yani
~190 MB fazla; karsiliginda gercek uygulama kimligi. Exe 52 MB self-contained (kullanicida
.NET GEREKMEZ; tek on kosul Windows'ta zaten bulunan WebView2). dotnet yoksa panel_build.py
uyarir, sistem Edge --app yoluna duser (panel_ac.py sirasi: kabuk -> --app -> tarayici).
Kisayol artik dogrudan kabugu gosterir; kur_build payload'a katar (Setup 12 -> 56 MB).

**Panel cerceveye sigiyor (kullanici istegi):** "#alan" artik DIKEY KAYDIRILMAZ; yeni sigdir()
gorunur panelleri 24 satira oranlayarak sokar, surukleme/boyutlandirma cerceve disina cikamaz.
Yedi dizilim de yeniden yazildi ve 24x24'e sigacak sekilde dogrulandi.

**Dosya goruntuleyici AYRI PENCERE:** izgaradaki "kod" paneli KALDIRILDI. Dosyaya tiklayinca
/dosya?is=..&yol=.. sayfasi ayri pencerede acilir (native kabukta gercek ikinci uygulama
penceresi - NewWindowRequested ile AltPencere). Icerik 2 sn'de bir tazelenir, DEGISEN SATIRLAR
PARLAR; once diskten okunur (model sonradan degistirmis olabilir), yoksa son 'write' olayindan.
Olay akisinda artik kod govdesi YOK - yalnizca "N satir - DOSYALAR panelinden ac" ozeti
(kullanici: "akista kodu gormeye gerek yok, dosyalara tiklayarak gorebiliyoruz").

**Test:** tests/test_panel.py'ye "yerlesim motoru" bolumu - itele/sikistir/sigdir algoritmasi
Python'da birebir kosulup her dizilimin 24x24'e sigdigi ve cakismadigi dogrulanir (statik kutu
denetimi yetmiyordu: motor kutulari degistiriyor). Ayrica kod panelinin kalkigi ve dosyanin
ayri pencerede acildigi de sinaniyor.

## 2026-08-24 (gece 3): cirak calisma dizini = PROJE KOKU

**Karar (kullanici onayladi):** panelden verilen isin calisma dizini artik varsayilan olarak
CALISMA ALANININ KOKU (ust bardaki 📁). Eskiden bos birakilinca "panel" alt klasoru aciliyordu;
hapis kokii is dizini oldugu icin cirak projenin KENDI dosyalarini ne read_file ile okuyabiliyor
ne de `ara` (RAG) ile bulabiliyordu - "projeye bagladim ama model projeyi gormuyor" hali.

- Bos alan  -> proje koku (cirak mevcut kodu okur, RAG projeyi indeksler)
- Dolu alan -> yalniz o ALT KLASOR (hapis daralir; "sadece src/oyun'da calis" senaryosu)
- Kok hala kurulum evi ise (proje SECILMEMIS) evi kirletmemek icin yine "panel" alt klasoru
- Yanit artik `klasor` doner; panel tostu isin NEREYE yazdigini gosterir, reddedilen ekleri de
  bildirir (eskiden ek sessizce dusuyordu)

**Yol denetimi (Windows tuzaklari):** "../disari", "C:kotu" (surucu-goreli), "/mutlak",
"alt/../../disari" reddedilir. NOT: Python 3.13'te ntpath.isabs("/x") artik **False** donuyor -
bastaki egik cizgi ACIKCA denetlenmeli (yoksa sessizce koke goreli sayilir). Ayrica realpath
kapsama kontrolu ikinci katman olarak duruyor.

**Kanit (canli):** ProjectTest kokunde onceden duran mevcut_modul.py -> cirak onu read_file ile
OKUDU, kdv_ekle'yi kullanan fis.py yazdi, fis_toplami([{tutar:100}]) == 118.0 dogru cikti ve
mevcut dosyaya dokunmadi. tests/test_panel.py "calisma dizini kurallari" bolumu bunu korur.

## 2026-08-24 (gece 2): derin denetim + dizilim presetleri

**Yapilan:** dort paralel denetci (kurulum / panel arka uc / panel on uc / cekirdek) tum yapiyi
okudu; bulunan hatalarin agir olanlari duzeltildi ve CANLI dogrulandi. Panele "dizilim"
(preset) sistemi eklendi: 7 hazir yerlesim + kullanicinin 💾 duzeni, elle tasiyinca secici
"ozel"e duser. tests/test_panel.py presetleri de denetler (cakisma/tasma/eksik panel).

**Kapatilan agir kusurlar (hepsi olculu/dogrulanmis):**
- GUVENLIK: panel uclari CSRF'ye acikti - tarayicidaki herhangi bir site 127.0.0.1'e "basit
  istek" atip /api/usta uzerinden KEYFI KOMUT calistirabiliyordu. Cozum: Origin/Referer
  dogrulamasi + zorunlu "X-Apprentice: panel" basligi (capraz kokenden preflight'siz
  gonderilemez). Dogrulandi: basliksiz 403, yabanci Origin 403, panel 200.
- GUVENLIK: calisma_dizini "C:kotu" gibi SURUCU-GORELI yolla calisma alanindan cikabiliyordu
  (ntpath.isabs False der ama join kokeni yok sayar). splitdrive + realpath kontrolu eklendi.
- Kurulum: tek yorum satirli (JSONC) bir IDE ayar dosyasi TUM kurulumu "EKSIK" yapiyordu
  (ide adimi False -> ozet penceresi hic acilmiyordu). Yorum soyucu + "okunamazsa DOKUNMA,
  kurulumu dusurme" kurali.
- Panel on uc: 500 olaydan sonra GOREV/PROMPT/SISTEM kartlari kalici siliniyordu (budama
  akisin ilk cocugunu, yani giris kabini yiyordu).
- Panel on uc: is degistirince ucustaki cevap ESKI isin olaylarini yeni akisa basip imleci
  ileri aliyordu -> yeni isin olaylari kalici kayip. Istek kimligi dogrulanarak cozuldu.
- Panel on uc: tek "takip" bayragi hem "akisi dibe kilitle" hem "en yeni isi sec" demekti;
  akisi kaydirinca panel kullanicinin baktigi isi caliyordu. Iki ayri bayrak (otoSec/dibeKilit).
- Panel on uc: "Claude'a giris yap" dugmesi 2.5 sn sonra sohbet yeniden cizilince siliniyordu
  (fiilen tiklanamaz). Uyari artik durumda yasar, olay delegasyonu ile baglanir.
- Panel on uc: usta sohbeti her yoklamada TAMAMLANMIS her cevap icin ayri HTTP istegi atiyordu
  (30 mesaj = tur basina 30 istek). Onbellek eklendi.
- Panel on uc: is ozetinde kacis yoktu (baslik/ortam/durum ham innerHTML) - "<b" iceren baslik
  paneli bozardi. Ayrica sohbet kipinde cift gonderim korumasi yoktu.
- Izgara: dikey kaydirma cubugu belirince ic genislik daraliyor, en sag sutun ~6 px tasip
  overflow-x:hidden ile ERISILEMEZ oluyordu (boyutlandirma tutamagi dahil). hucre() artik
  clientWidth/Height okur + scrollbar-gutter:stable + tek seferlik yeniden yerlestirme.
- Sunucu: Windows'ta proc.kill() torun surecleri (pytest/run_shell/ruff) OLDURMUYORDU - is
  "bitti" gorunurken calisma dizinine yazmaya devam edebiliyordu. taskkill /T + iptalde
  gercek olume kadar sinirli bekleme (exit olayi eksik kalmiyor).
- Izleyici: events.jsonl artimli okumada YARIM SATIR "bozuk JSON" diye atlanip ofset
  ilerletiliyordu -> 20 KB'lik bir olay bir daha hic okunmuyordu (MCP raporu dogru, izleyici
  eksik). Artik yalniz tam satirlar islenir.
- core/client.py: OLLAMA adresi SABITTI; ollama.url ayari yalniz rag/precheck tarafindan
  okundugu icin uzak sunucu tanimlayan kullanicida on kontrol "model var" derken isci
  localhost'a gidip dusuyordu. Artik ayardan okunur.
- canli kipte BOS CEVAP korumasi yoktu (native yolda EMPTY_NUDGE var): is bos halde
  "basarili" bitebiliyordu. Iki kip artik ayni sozlesmeyi verir.
- panel.py: --home ile verilen ev, ortamda APPRENTICE_HOME varsa EZILMIYORDU (setdefault) ->
  isler baska eve yazilip listede hic gorunmuyordu.
- panel.py: model karti ctx kiyaslamasi olmayan bir ayar anahtarini (ollama.num_ctx) okuyordu;
  dogrusu makine.num_ctx.
- kur.py: kisayol_yaz her kosulda True donuyordu (kisayol yokken adim "[ok]"); masaustu
  OneDrive yonlendirmesinde bulunamiyordu; PowerShell tirnak kacisi yoktu. model_uygula()
  hic cagrilmayan olu koddu - artik model dogrulaninca kart bazli ayar yaziyor.
- panel_ac.py: 8788'i tutan YABANCI uygulama "bizim panel" sanilabiliyordu (herhangi bir 200);
  sunucu kalkmazsa sessizce olu URL aciliyordu. Uc kimligi dogrulaniyor, hata penceresi cikiyor.

**Denetimde gorulup DUZELTILMEYENLER (bilincli, sirada):** rapor_diskten ile report()
sozlesme farki (olcumler/kriterler eksik); XML arac ayristiricisinin icerikte </parameter>
gecerse kesmesi; yazilabilir kilidinin run_shell ile delinebilmesi; apprentice.config.json
sampling/prompt bloklarinin hic okunmamasi; RAG gomme parmak izi olmamasi; canli.txt'nin
atomik olmayan yazimi; usta_istekler klasorunun sinirsiz buyumesi.

## 2026-08-24 gece: Web Panel büyük iterasyonu (v3) — devir

**Ne yapıldı:** `clients/web/panel.py` + `panel.html` — çift sohbetli dashboard:
USTA (Claude CLI, başsız `claude -p`, model/effort/özel-CLI seçimli, 📎 dosya+resim ekli, balonlu)
ve ÇIRAK (⚙ görev kipi = worker_run boru hattı + 💬 sohbet kipi = akışlı düz konuşma).
Akıllı ızgara yerleşimi (snap + itme + sıkıştırma, 💾 kalıcı profil), boru hattı filtresi,
kaynak rozetleri (ÇIRAK/USTA→/→USTA/SİSTEM/HARNESS), DOSYA GÖRÜNTÜLEYİCİ, çalışma alanı
seçici (yerel klasör diyaloğu → `panel_ayar.json`), model kartı/ısıt/⏏eject, İLK BAĞLAM metriği.

**Koddan görünmeyen kritik kararlar:**
- Usta prompt'u `claude`ya **STDIN'den** gider. Sebep (yaşandı): `shell=True` + çok satırlı
  prompt argümanında cmd.exe satır sonunu komut ayracı sayar — yalnız İLK satır ulaşır.
  Ek yolları ve `canli:true` notunun sessiz düşmesinin kökü buydu. Bayraklar tek satır kalmalı.
- `canli.txt` **tam metin** yazılır (kayan pencere yasak: ön-ek değişince izleyiciler "yeni tur"
  sanıp daktiloyu baştan oynatır — Kalman sonsuz-tekrar görünümü) ve iş sonunda **silinmez**
  (son üretim panelde kalır); tur sonu yazımı kısma atlar (`zorla`).
- MCP/usta işlerinde `canli` varsayılanı KAPALI; panel, araç izinli usta isteğine
  "worker_run'da canli:true kullan" notunu otomatik ekler.
- Panel işlerinde `usta_rapor` olayını MCP yolu yazmaz → panel `_usta_rapor_tamamla` ile
  iş bitince kendisi işler. `worker_status`'a disk yedeği eklendi (başka sürecin işi görünür).
- Panelden iş → `panel_bekleyen.json` → MCP sunucusu ustanın SONRAKİ her araç sonucuna
  `panel_bildirimi` iliştirir (MCP'de push yok; bu en dürüst kanal).
- Sahipsiz usta isteği: 700 sn üstü "çalışıyor" → "hata" (panel yeniden başlarsa iş parçacığı ölür).
- Yerleşim anahtarı `apprentice_yerlesim_v4`te SABİTLENDİ — göçler yerinde yapılır, anahtar
  bir daha değişmez (v3→v4 kullanıcının düzenini sıfırladı, tekrarlanmayacak).

**Denenip ELENENLER:** reranker (ölçüm: bge-m3 top-1 5/6 yeterli — torch yığını kurulmadı);
token-daktilo native tool kanalında (Ollama argümanları akıtmıyor, ölçüldü: 44 s tek chunk —
çözüm XML-içerik protokolü `canli=true`, ölçüldü: aynı kalite, prompt −%31);
ızgarasız serbest sürükleme (üst üste binme şikâyeti — gridstack-mini'ye geçildi).

**Bekleyenler:** panel testleri yok (test_panel.py yazılmadı — davranışlar tarayıcı içi
programatik sınamayla doğrulandı); usta sohbeti oturum-sürekliliği (`--continue`) bilinçli
kapalı; Unity açılınca: api_ara canlı sınavı + capability-pack A/B.

## 2026-08-24 (daha erken): ölçüm + yardımcı katman devri
Ayrıntı `APPRENTICE_RAPOR.md`'de (lab deposu): dur sinyali, determinizm, ara=adreslenebilirlik,
ruff/harita/reranker/128k kararları, STATE/AGENTS entegrasyonu, izleyici v1-v4.

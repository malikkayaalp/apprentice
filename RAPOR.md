# RAPOR — Apprentice MCP sunucusu, aşama 1 (2026-08-22 gece, otonom oturum)

## Ne yapıldı

| # | istek | durum | nerede |
|---|---|---|---|
| 1 | `server/apprentice_server.py`: tek araç `worker_run(gorev, kabul_kriterleri, ortam)` | **bitti** | `server/apprentice_server.py` |
| 2 | `server/README.md`: sözleşme, örnek, Cursor/Claude Code bağlantısı | **bitti** | `server/README.md`, `.mcp.json` |
| 3 | Unity'siz duman testi (fake_unity_server) + `tests/test_server.py` | **bitti, GEÇTİ** | `envs/fake/fake_runner.py`, `tests/test_server.py` |
| 4 | Gerçek test: Suru görevi, `play_observe` ile sayıyla rapor | **bitti, 1. turda GEÇTİ** | `tests/suru_kabul.py`, `tests/suru_kabul.son.json` |
| 5 | Hata düzelt, tekrar (≤5 tur) | 2 altyapı hatası bulundu/düzeltildi; görev 1 turda geçtiği için onarım turu gerekmedi | aşağıda |
| 6 | Yerel commit (push yok) | **bitti**: `02ee981` (ilk sürüm), `35b6618` (bu çalışma) | `git log` |
| 7 | RAPOR.md | bu dosya | |
| 8 | `envs/code/` taslak + kendi deposunda küçük görev | **bitti, GEÇTİ** (27 s, 3 test) | `envs/code/code_runner.py`, `tests/test_code_env.py` |

Unity paneline (`clients/unity/`) dokunulmadı. Unity edit modunda bırakıldı (doğrulandı: `isPlaying=false`).

## Sözleşme (uygulanan)

```
worker_run(gorev, kabul_kriterleri[], ortam="unity"|"code"|"fake", calisma_dizini?, oturum?, play?, onarim?, zaman_asimi_s?)
  -> { yazilan_dosyalar[{yol, yeni, eklendi, silindi, satir}], derleme_durumu, hatalar[],
       tur_sayisi, sure, ozet, olcumler[{arac, sonuc, sure_s}], araclar[], play, oturum, is_id }
derleme_durumu ∈ { derlendi, derleme_hatasi, calistirilamadi, zaman_asimi }
```

- Kabul kriterleri göreve "KABUL KRİTERLERİ (denetçi yazdı)" bloğu olarak eklenir + kural: "ölç, ham raporla, ölçüm-düzeltme döngüsüne girme".
- `derlendi` yalnızca derleyici/doğrulayıcı onayı; kriter kararı denetçide, `olcumler` ham.
- İşçi ayrık süreç (`envs/<ortam>/*_runner.py`), olaylar `~/.apprentice/jobs/<id>/events.jsonl`; sunucu bunları rapora çevirir. Zaman aşımı varsayılan 1800 s (bir tur 60–300 s ölçüldü; Suru 286 s).

## Testler

### 3) Duman testi — `python tests/test_server.py` → **GEÇTİ**
Gerçek stdio istemcisi gibi konuşur: initialize/ping/tools/list, 4 hata yolu, fake ortamla 4 senaryo
(başarı → `derlendi`, `HATA_URET` → `derleme_hatasi` tur 2, `COK` → `calistirilamadi` + "sonuç yazmadan çıktı",
`YAVAS` → `zaman_asimi`). Fake koşucu `mcpbridge/fake_unity_server.py`'ye stdio ile gerçekten bağlanıp
`read_console` çağırır (köprü katmanı da testte). Şema alanları ve tipleri her senaryoda kontrol edilir.

### 4) Gerçek test — `python tests/suru_kabul.py` → **GEÇTİ (1 tur)**

Görev: "Suru altındaki 8 küre XZ düzleminde rastgele hareket etsin." Kriterler: çiftler ≥ 2 birim, |x|,|z| ≤ 5,
15 sn doğrula, script `SuruYoneticisi.cs` + `add_component`.

| ölçüm | değer |
|---|---|
| Başlangıç (script yokken, 5 sn) | 4 örnek, min mesafe 2.000, hareket **yok** |
| İşçi | 286 s, 1 tur, derlendi, 11 araç çağrısı (scene_objects, inspect_object×2, hierarchy, list_scripts, write_script×2, add_component, read_script, play_observe×2), dosya +156/−10 |
| **Denetçi bağımsız ölçümü (15 sn)** | **10 örnek**, en küçük çift mesafesi **2.003**, max \|x\| **4.986**, max \|z\| **4.709**, hareket var |
| K1 (≥2) ihlal | **0/10** |
| K2 (≤5) ihlal | **0/10** |
| K3 (15 sn, hareketli) | sağlandı |

İşçi beyanı ("tüm ölçümlerde TUM KRITERLER SAGLANDI") bağımsız ölçümle uyuştu. Yazdığı kod, önceki deneyde
sonradan öğrettiğimiz deseni bu kez kendiliğinden kurdu: yeni konumu önce dene, 2 birimden yakın düşüyorsa adımı atla
(sert kısıt), sınırlarda `Clamp`. Fark: kriterler **baştan, somut ve ölçülebilir** verildi — denetçinin işi tam olarak bu.

Not: 15 sn'de 10 örnek (0.5 sn hedefin altında) — her örnek bir MCP `execute_code` gidiş-dönüşü (~1 s). Kriter
değerlendirmesi için yeterli; daha sık örnek istenirse ölçüm kodu Unity tarafında biriktirilmeli.

Denetçi döngüsü (ölçüm özeti → aynı `oturum` ile düzeltme, ≤5 tur) betikte hazır ama bu koşuda tetiklenmedi.

### 8) Code ortamı — `python tests/test_code_env.py --live` → **GEÇTİ**
Modelsiz: hapis (`../` reddi), dosya araçları, `compile()` doğrulayıcı, unittest doğrulayıcı (bozuk → hata, düzeltince temiz), shell.
Canlı (sunucu üzerinden, `.apprentice_test_home/code_task/`): "toplam(a,b) + en az 3 test" → 27 s, 1 tur, 4 araç
(list_files, write_file×2, run_tests), `derlendi`; denetçi testleri kendisi koştu: **Ran 3 tests, OK**.

## Bulunan ve düzeltilen hatalar

1. **Çocuk süreç takılması (Windows)** — sunucu içinden başlatılan işçi ilk satırını bile yazmadan duruyordu; tek başına
   sorunsuzdu. Sebep: çocuk sunucunun stdin'ini (MCP borusu) miras alıyordu. Düzeltme: `stdin=DEVNULL` (stdout zaten DEVNULL).
2. **Bayat `.pyc`** (code ortamı) — aynı saniyede aynı boyutta yeniden yazılan test dosyası için Python eski bytecode'u
   kullandı (mtime+boyut aynı), düzeltilmiş test eski haliyle koştu. Düzeltme: doğrulayıcı `py_compile` yerine
   `compile()` (pyc yazmaz), test/shell koşuları `-B` + `PYTHONDONTWRITEBYTECODE=1`.
3. Zaman aşımı senaryosu fake işçi 0.5 sn'den hızlı bittiği için test edilemiyordu → `YAVAS` anahtarı.
4. Test çıktısı cp1252 konsolda Türkçe karakterde çöktü → `stdout.reconfigure(utf-8)`.
5. Önceki oturumdan: Python `open(...,'w')` Windows'ta CRLF yazıyor, diff tüm dosya oluyordu → `newline="\n"`.

## Kararlar ve gerekçeleri

- **Tek araç.** İlk sürümdeki `worker_status`/`worker_env` kaldırıldı; ön koşul kontrolü (Ollama, model, köprü)
  `worker_run` içine alındı ve sebep `hatalar`da döner. Denetçi tek şeyi öğrenir.
- **İşçi ayrık süreç, olay dosyası üzerinden.** Unity paneliyle aynı koşucu (`panel_runner.py`) — iki istemci tek
  işçi yolu. Çökme/zaman aşımı sunucuyu düşürmez.
- **pytest kurulmadı.** Hiçbir yorumlayıcıda yoktu; kurmak depo dışına yazmak olurdu (yasak) ve "ek paket yok"
  ilkesine ters. Doğrulayıcı pytest varsa onu, yoksa stdlib `unittest discover` kullanır; model hangisinin
  aktif olduğunu sistem isteminden bilir.
- **Silme aracı yok** (code ortamında da) — Unity'deki kazanın dersi.
- **Ölçüm ham döner, yorum denetçide.** Sunucu "kriter tuttu" demez; yalnızca derleyici sonucunu ve ham ölçümü verir.
- Unity zaten açıktı (23:09); yanlışlıkla ikinci örnek açtım, "proje zaten açık" hatasıyla kapattım; mevcut
  örnekle devam edildi.

## Sırada ne var

1. Denetçi olarak **gerçek IDE**: Claude Code'u `.mcp.json` ile bağlayıp Suru görevini sohbetten verdirmek (kriterleri
   Claude yazsın). Cursor'da aynı. Ölçüm: Cursor kendi ajanı vs Cursor→XL (aşama 2'nin ölçüm sorusu).
2. `envs/code` taslağını büyütmek: git (diff/status, commit yok), çok dosyalı görevlerde `64k + prefix cache` için
   araç bloğunu sabit tutma, büyük dosya okuma kırpması (şu an 60k karakter).
3. `play_observe` örnekleme sıklığı: Unity tarafında biriktirip tek seferde almak (15 sn → 30 örnek).
4. Denetçi düzeltme döngüsünü tetikleyen bir vaka (bilerek zayıf kriterle) ile `oturum` sürekliliğini canlı test etmek.
5. İlk çalıştırmada `num_batch` ölçümü ve UPM paket yerleşimi (kullanıcı hedefi: GitHub'dan indiren rahat kursun).

# Apprentice MCP sunucusu

**A local model does the work, a frontier model supervises.**

`server/apprentice_server.py` bağımlılıksız (stdlib) bir stdio MCP sunucusudur. Denetçi
(IDE'nizdeki Claude / GPT / Gemini ya da Claude Code) buna bağlanır ve iş aracını çağırır
(`worker_run`; yardımcı: `worker_status`);
işi Ollama'daki yerel model yapar, sonucu derleyici/doğrulayıcı onaylar.

## Sözleşme

```
worker_run(gorev, kabul_kriterleri, ortam="unity", calisma_dizini?, oturum?, play?, onarim?, araclar_kapali?, zaman_asimi_s?)
```

| girdi | tip | anlam |
|---|---|---|
| `gorev` | string | ne yapılacak, düz dille; dosya/obje adlarını ver |
| `kabul_kriterleri` | string[] | **denetçi yazar**, somut ve ölçülebilir; göreve metin olarak eklenir |
| `ortam` | `unity` \| `code` \| `fake` | araç seti + doğrulayıcı. `code` = genel kod (taslak), `fake` = Unity/Ollama'sız duman testi |
| `calisma_dizini` | string | `code` için zorunlu: işçinin hapsedildiği klasör (dışına okuyamaz/yazamaz, silemez) |
| `oturum` | string | önceki çağrının `oturum`u verilirse işçi aynı bağlamla devam eder |
| `play` | bool | unity: derlemeden sonra play moda girip çalışma zamanı hatası ara (vars. false) |
| `onarim` | int | azami derleme onarım turu (vars. 3) |
| `araclar_kapali` | string[] | bu turda işçiden saklanacak araçlar, ör. `["play_observe"]` — ölçümü denetçi yapar, işçi ölçüm-düzeltme döngüsüne giremez (ölçüldü: talimatla söylenince işçi iki turda yine ölçtü, ~400 s/tur) |
| `zaman_asimi_s` | number | üst sınır (vars. 1800); aşılırsa işçi durdurulur |
| `bekle` | bool | `false`: hemen `is_id` ile dön, `worker_status(is_id)` ile yokla. **Cursor için gerekli** (ölçüldü: Cursor'ın araç zaman aşımı ~2.5 dk, bir Unity turu 2–8 dk) |

Dönüş:

```json
{
  "yazilan_dosyalar": [{"yol": "Assets/Scripts/X.cs", "yeni": true, "eklendi": 41, "silindi": 0, "satir": 41}],
  "derleme_durumu": "derlendi | derleme_hatasi | calistirilamadi | zaman_asimi",
  "hatalar": ["...derleyici / çalışma zamanı / altyapı..."],
  "tur_sayisi": 1,
  "sure": 73.4,
  "ozet": "işçinin kendi anlatımı — beyan, kanıt değil",
  "olcumler": [{"arac": "play_observe", "sonuc": "HAM çıktı", "sure_s": 8.2}],
  "araclar": ["read_script Assets/Scripts/X.cs", "write_script Assets/Scripts/X.cs", "..."],
  "play": {"dogrulandi": true, "hatalar": []},
  "oturum": "20260822-231500-a1b2c3",
  "is_id": "...", "is_klasoru": "~/.apprentice/jobs/<id>"
}
```

Kurallar:

- `ozet` boşsa `hatalar`a "işçi nihai özet yazmadı" düşer (adım sınırı dolmuş demektir; sessiz başarı sanma).
- `derleme_durumu == "derlendi"` yalnızca **derleyicinin** onayıdır. Kabul kriterlerinin
  sağlanıp sağlanmadığına `olcumler`e bakarak **denetçi** karar verir.
- Ölçümler ham gelir. Ölçülen: işçi kendi ölçümünü yorumlayıp düzeltmeye kalkınca
  yakınsamadı (en küçük mesafe 1.15 → 0.01); aynı ölçüm özetlenip "sert kısıt gerek"
  diye verilince 2 turda çözdü. Bu yüzden denetçi özetler, aynı `oturum` ile yeni
  `worker_run` çağırır.
- Bir tur 60–300 s sürer; `play` ile daha uzun. İstemcinin araç zaman aşımını buna göre
  ayarla (Claude Code: `MCP_TOOL_TIMEOUT` ms cinsinden, ör. `1800000`). Ayarlanamıyorsa (Cursor)
  `bekle=false` + `worker_status`. İstemci çağrıyı iptal ederse (`notifications/cancelled`) sunucu
  işçiyi öldürür — ölçüldü: iptal dinlenmeyince işçi zombi olarak devam edip ikinci çağrıyla aynı
  dosyaya paralel yazdı.
- İş dosyaları: `~/.apprentice/jobs/<id>/` → `prompt.txt` (işçinin gördüğü tam metin),
  `events.jsonl` (ham olay akışı), `stderr.txt`, `job.json`. Sohbet bağlamı
  `~/.apprentice/sessions/<ortam>/<oturum>.json`. Ev `APPRENTICE_HOME` ile değişir.

## Örnek çağrı

```json
{
  "name": "worker_run",
  "arguments": {
    "gorev": "Suru altındaki 8 küre XZ düzleminde rastgele hareket etsin.",
    "kabul_kriterleri": [
      "Hiçbir anda hiçbir küre çifti birbirine 2 birimden yakın olmasın.",
      "Her kürenin |x| ve |z| değeri 5'i aşmasın.",
      "play_observe ile 15 saniye boyunca doğrula ve ölçümü ham raporla."
    ],
    "ortam": "unity",
    "play": true
  }
}
```

## Bağlanma

**Claude Code** — depo kökündeki `.mcp.json` otomatik görülür; `claude` bu klasörde
açılınca "apprentice" sunucusunu onaylaması istenir. Başka bir projeden:

```bash
claude mcp add apprentice -- python C:/yol/Apprentice/server/apprentice_server.py
```

**Cursor** — `.cursor/mcp.json` (proje) ya da `~/.cursor/mcp.json` (genel):

```json
{ "mcpServers": { "apprentice": { "command": "python",
    "args": ["C:/yol/Apprentice/server/apprentice_server.py"],
    "env": { "PYTHONIOENCODING": "utf-8" } } } }
```

**VS Code (Copilot)** — `.vscode/mcp.json`, aynı `command`/`args` ile `"servers"` altında.

Ortam değişkenleri: `APPRENTICE_HOME`, `APPRENTICE_TIMEOUT_S`, `APPRENTICE_PYTHON`
(işçi için ayrı yorumlayıcı), `UNITY_CODE_MODEL`, `UNITY_MCP_URL`. Diğer ayarlar
`apprentice.config.json` (şablon: `apprentice.config.template.json`; öncelik env >
dosya > şablon > kod).

## Ortamlar

| ortam | araçlar | doğrulayıcı | koşucu |
|---|---|---|---|
| `unity` | read/write_script, list_scripts, scene_objects, inspect_object, hierarchy, add_component, set_field, play_observe… | Unity derleyicisi (+ play, play_observe) | `envs/unity/panel_runner.py` |
| `code` | read_file, write_file, list_files, run_shell, run_tests | `compile()` + pytest (yoksa stdlib unittest) | `envs/code/code_runner.py` |

`code` ortamında silme aracı yoktur; `run_shell` içinde `git push` ve özyinelemeli silme komutları reddedilir. Git okuma/commit `run_shell` üzerinden serbesttir.
| `fake` | — | — | `envs/fake/fake_runner.py` (olay şemasını taklit eder) |

## İzleme

`python clients/web/monitor.py [--port 8765] [--home ~/.apprentice]` — sunucuya bağlanmaz, iş
klasörünü okur; hangi istemci başlatmış olursa olsun (Claude Code, Cursor, panel, test betiği)
her iş listede: durum, derleme, dosyalar, araç akışı (argüman + sonuç), ölçümler, işçinin özeti.
`/api/jobs` aynı veriyi JSON verir.

## Ölçüm kampanyası

`python tests/code_kampanya.py` — 6 kod görevi; denetçi (betik) kriter yazar, işçi yazar, denetçi
**işçiye verilmeyen gizli kontrolleri** koşar, tutmayanları somut geri bildirime çevirip aynı
`oturum` ile 2. tur ister. Sonuç `tests/code_kampanya.son.json` (tur-1 / tur-2 gizli başarı, süre).

## Test

```bash
python tests/test_server.py          # Unity/Ollama gerekmez: el sıkışma, şema, hata yolları,
                                     # fake ortamla 4 senaryo (başarı / derleme hatası / çökme / zaman aşımı)
python tests/test_server.py --live   # + gerçek Unity turu (Ollama + MCP for Unity açık)
python tests/test_code_env.py [--live]   # code ortamı: hapis/araçlar/doğrulayıcı; --live gerçek görev
python tests/suru_kabul.py           # denetçi-işçi kabul testi: Suru görevi, bağımsız 15 sn ölçüm
```

Ön koşullar `worker_run` içinde kontrol edilir: Ollama kapalıysa, model yüklü değilse
ya da Unity köprüsü yoksa işçi hiç başlatılmaz, `derleme_durumu: calistirilamadi` ve
sebep `hatalar`da döner.

## Tasarım notları

- İşçi **ayrık süreç** (`envs/<ortam>/panel_runner.py`): tur dakikalar sürer, Unity domain
  reload yapar, işçi çökse sunucu ayakta kalır. Prompt komut satırından değil dosyadan
  geçer (kaçış kazaları).
- Çocuğun stdin/stdout'u `DEVNULL`: ikisi de MCP kanalı. Ölçülen: stdin miras alınınca
  çocuk Windows'ta ilk satırını bile yazmadan takıldı.
- `tools/call` ayrı iş parçacığında; `ping` uzun tur sırasında da cevaplanır.
- Q3CNFU Unity paneli aynı koşucuyu kullanır; sunucu panelin IDE-bağımsız karşılığıdır.

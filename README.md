# Apprentice

**A local model does the work, a frontier model supervises.**

A local coding model (Ollama, Qwen3-Coder-Next) does the work: it writes files, calls tools, runs
tests and repairs its own errors. A frontier model — the one already in your IDE (Cursor, Claude
Code, VS Code) — supervises: it writes the task and the **acceptance criteria**, reads the raw
measurements that come back, and decides when the work is done. Your code never leaves the machine
and the worker burns no API tokens; the supervisor only ever sees summaries and measurements.

*Apprentice* is **Çırak** in Turkish. The master watches, the apprentice works.

## Why this split (measured, not assumed)

- Same worker, same task: asked to interpret its **own** raw measurement and fix itself, it never
  converged (closest distance 1.15 → 0.01). Given the same measurement **summarised** — "this rule
  does not hold, you need a hard constraint" — it solved it in two rounds.
- Six-task code campaign with hidden supervisor checks (never shown to the worker): **34/36** on
  round one, 36/36 after concrete supervisor feedback. One task that generic feedback ("the tests
  fail") could not fix in 2×1000 s was fixed in **130 s** by a concrete one-paragraph diagnosis.
- When the criteria are numbers from the start, the worker writes on its own the pattern that
  otherwise has to be taught to it afterwards.

Evidence and every experiment live in [apprentice-lab](https://github.com/malikkayaalp/apprentice-lab).

## Install

**Windows — no Python required.** Download `Apprentice-Setup.exe` from
[Releases](https://github.com/malikkayaalp/apprentice/releases) and run it from anywhere. You pick
the install folder; the setup then checks and completes, step by step: Python (downloads an embedded
runtime if missing) → Ollama (starts it, or points you to the download) → the model (~20 GB, with a
progress bar) → an `apprentice` MCP entry for every installed IDE (Cursor, VS Code, Windsurf; other
entries are left untouched) → a self-test.

![Apprentice Setup](docs/setup.png)

**macOS / Linux / manual:** Python 3.10+ and `python kur.py` (same engine, no third-party packages).

## Use

Add the supervisor rule to your project (`python kur.py --kural <project>`), then simply describe the
task in your IDE chat. The frontier model writes concrete criteria, calls `worker_run`, the local
model writes and tests the code, and the frontier model verifies the result against the raw
measurements. You never type a path: the worker is confined to the workspace root your IDE reports
over MCP `roots`.

Tools, return schema and rules: [server/README.md](server/README.md).
Unity support is a separate, optional repo: [apprentice-unity](https://github.com/malikkayaalp/apprentice-unity).

---

# Türkçe

Yerel bir kodlama modeli (Ollama, Qwen3-Coder-Next) işi yapar: dosya yazar, araç çağırır,
test koşar, hatayı düzeltir. Büyük bir model (IDE'nizdeki Claude/GPT/Gemini ya da Claude Code)
denetler: görevi kabul kriterleriyle verir, dönen ölçümü yorumlar, ne zaman durulacağına karar
verir. Kod dışarı çıkmaz, kota yoktur; denetçiye yalnızca özetler ve ölçümler gider.

Türkçede *Çırak*. Usta bakar, çırak yapar.

## Neden bu bölünme (ölçüldü)

- Aynı işçi, aynı görev: ham ölçümü kendisi yorumlayıp düzeltmeye kalkınca yakınsamadı; ölçüm
  **özetlenip** "şu kural tutmuyor" diye verilince 2 turda çözdü.
- 6 görevlik kod kampanyası (gizli denetçi kontrolleri): tur-1 34/36 → denetçinin somut geri
  bildirimiyle 36/36. Genel geri bildirim ("test tutmuyor") 2×1000 sn'de çözemediğini, somut özet
  130 sn'de çözdü.
- Kriterler baştan sayıyla verilince işçi sonradan öğretilmesi gereken deseni kendiliğinden kurdu.

Kanıtlar ve bütün deneyler [apprentice-lab](https://github.com/malikkayaalp/apprentice-lab) deposunda.

## Yapı

```
server/          MCP sunucusu: worker_run(görev, kabul_kriterleri, ortam) — bkz. server/README.md
kur.py           kurulum motoru (Windows'ta Apprentice-Setup.exe olarak paketlenir)
core/            Ollama istemcisi, şema koruması, ayar yükleyici, ilk-çalıştırma ölçümü
mcpbridge/       MCP taşıma (stdio + Streamable HTTP), bağımlılıksız; test için fake_server
envs/code/       kod ortamı: dosya oku/yaz, shell, test; workspace'e hapis; compile()+unittest/pytest doğrulayıcı
envs/fake/       duman testi ortamı (model gerektirmez)
envs/<eklenti>/  eklentiler buraya klonlanır ve otomatik keşfedilir (örn. apprentice-unity)
clients/web/     canlı izleme sayfası: python clients/web/monitor.py → http://127.0.0.1:8765
tests/           sözleşme testleri, kod ortamı testi, ölçüm kampanyası
```

## Gereksinimler

- [Ollama](https://ollama.com) (kurulum betiği modeli kendisi indirir; elle: `ollama pull hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_XL`, ~20 GB)
- Python 3.10+ — Windows'ta gerekmez (kurulum gömülü Python indirir); ek paket yok

## Kurulum

**Windows (Python gerekmez):** [Releases](https://github.com/malikkayaalp/apprentice/releases) sayfasından
**`Apprentice-Setup.exe`**'yi indir ve çalıştır — her yerden çalışır, depoyu ayrıca indirmen gerekmez
(dosyalar exe'nin içinde; kurulum klasörünü sen seçersin, varsayılan `%LOCALAPPDATA%\Apprentice`).

![Apprentice Setup](docs/setup.png)

Adım adım: Python (yoksa gömülü Python'u indirir) → Ollama (yoksa yönlendirir, kapalıysa başlatır) → model
(yoksa ilerleme yüzdesiyle indirir, ~20 GB) → kurulu IDE'lerin MCP ayarına `apprentice` girdisi
(Cursor, VS Code, Windsurf; diğer girdilere dokunmaz) → öz-test.

**macOS / Linux / elle:** Python 3.10+ ile aynı betik:

```bash
python kur.py            # kurulum
python kur.py --kontrol  # yalnızca durum
python kur.py --ide cursor,vscode,windsurf,claude-desktop
python kur.py --olc      # + makineye özel num_batch ölçümü (2–3 dk; ölçüldü: 512 → 4096 arası +%342 prefill)
python kur.py --kural <proje>   # projeye denetçi kuralı (.cursor/rules/apprentice.mdc + APPRENTICE.md)
```

Claude Code: depodaki `.mcp.json` otomatik görülür. Kurulumdan sonra IDE'nin MCP listesinde `apprentice`
yeşil olmalı; araçlar `worker_run`, `worker_status`.

Kullanım: projene kural dosyasını yaz (`--kural`), sohbette görevi ver — usta model kriter yazar,
`worker_run`'ı çağırır, yerel model yazar/test eder, usta sonucu doğrular. Yol yazmana gerek yok:
işçi IDE'nin bildirdiği workspace köküne hapsedilir (MCP `roots`). Araçlar, dönüş şeması ve kurallar:
[server/README.md](server/README.md).

## Eklentiler

Ortamlar `envs/<ad>/env.json` ile keşfedilir; çekirdek yalnızca `code` içerir. Oyun motoru gibi
alanlar ayrı depolardır ve `envs/<ad>` olarak klonlanır:

- [apprentice-unity](https://github.com/malikkayaalp/apprentice-unity) — Unity araç seti + derleme/play
  doğrulaması + Q3CNFU Editor paneli. Klonlanınca `worker_run`'da `ortam="unity"` belirir.

## Ölçülmüş tasarım kararları

- Başarı **doğrulayıcıyla** (derleyici, test) belirlenir, modelin beyanıyla değil; `ozet` beyandır.
- Ölçüm ham döner, yorum denetçide; işçi ölçüm-düzeltme döngüsüne sokulmaz (`araclar_kapali`).
- Silme aracı yok; `run_shell`'de silme ve `git push` reddedilir.
- İşçi ayrık süreç; istemci iptal ederse öldürülür (Cursor'ın ~150 sn zaman aşımı ölçüldü →
  `bekle=false` + `worker_status`).
- Araç bloğu küçük ve sabit tutulur: her turda yeniden gönderilir, kullanılmayan araç kalıcı vergidir.

## Test

```bash
python tests/test_server.py        # model gerekmez
python tests/test_code_env.py      # kod ortamı; --live ile gerçek görev
python tests/code_kampanya.py      # 6 görevlik ölçüm kampanyası (Ollama gerekir)
```

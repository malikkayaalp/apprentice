# Apprentice

**A local model does the work, a frontier model supervises.**

Yerel bir kodlama modeli (Ollama, Qwen3-Coder-Next) işi yapar: dosya yazar, araç
çağırır, derler, hatayı düzeltir. Büyük bir model (IDE'nizdeki Claude/GPT/Gemini ya da
Claude Code) denetler: görevi kabul kriterleriyle verir, ölçümü özetler, ne zaman
durulacağına karar verir. Kod dışarı çıkmaz, kota yoktur; denetçiye yalnızca özetler gider.

Türkçede *Çırak*. Usta bakar, çırak yapar.

## Neden bu bölünme

Ölçümle: yerel model 8 küreli "birbirine 2 birimden fazla yaklaşmasın" görevinde kendi
ölçümüne bakarak düzeltmeye çalışınca yakınsamadı (en küçük mesafe 1.15 → 0.01). Aynı
ölçüm *özetlenip* "sert kısıt gerek" diye verilince 2 turda çözdü. Yazma ve araç kullanma
yerelde güçlü; ham veriyi yorumlama ve durma kararı büyük modelde. Kanıtlar ve bütün
deneyler [apprentice-lab](https://github.com/malikkayaalp/apprentice-lab) deposunda.

## Yapı

```
core/            Ollama istemcisi, şema koruması, araç döngüsü — ortamdan bağımsız
mcpbridge/       MCP taşıma (stdio + Streamable HTTP), bağımlılıksız
envs/unity/      (eklenti, ayrı depo: apprentice-unity) Unity araçları + Q3CNFU paneli
envs/code/       genel kod ortamı (taslak): dosya oku/yaz, shell, test; hapis + unittest/pytest doğrulayıcı
server/          MCP sunucusu: tek araç worker_run(görev, kabul_kriterleri, ortam) — bkz. server/README.md
clients/web/     canlı izleme sayfası: `python clients/web/monitor.py` → http://127.0.0.1:8765 (jobs klasörünü okur)
tests/           hapis öz-testi
```

## Gereksinimler

- Python 3.10+ (ek paket yok, stdlib)
- [Ollama](https://ollama.com) + `hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_XL` (~20 GB)
- Unity için: apprentice-unity eklentisi (aşağıda)

## Denetçi olarak bağlanmak (MCP sunucusu)

Sunucu stdio MCP konuşur, bağımlılığı yoktur. Depo kökündeki `.mcp.json` Claude Code
tarafından otomatik görülür (`claude` bu klasörde açılınca "apprentice" sunucusunu sorar).
Cursor / VS Code için aynı girdiyi kendi MCP ayarına kopyala:

```json
{ "mcpServers": { "apprentice": { "command": "python", "args": ["C:/yol/Apprentice/server/apprentice_server.py"] } } }
```

Araçlar:

| araç | ne yapar |
|---|---|
| `worker_run(gorev, kabul_kriterleri[], ortam="unity"\|"code", calisma_dizini?, oturum?, play?, onarim?, zaman_asimi_s?)` | işçiyi koşturur; `{yazilan_dosyalar, derleme_durumu, hatalar, tur_sayisi, sure, ozet, olcumler}` döner |

Sözleşme: **kabul kriterini denetçi yazar** (işçinin en zayıf yeri), `ok` yalnızca
derleyici/doğrulayıcının onayıdır, kriterlerin sağlanıp sağlanmadığına denetçi karar
verir. Ölçümler ham gelir; denetçi özetleyip aynı `oturum` ile düzeltme istetir. Bir
tur dakikalar sürer — istemcinin araç zaman aşımını (`MCP_TOOL_TIMEOUT`) buna göre ayarla. İş dosyaları `~/.apprentice/jobs/<id>/` (prompt,
olaylar, stderr), sohbet bağlamı `~/.apprentice/sessions/<ortam>/`.

Test: `python tests/test_server.py` (Unity/Ollama gerekmez), `tests/test_code_env.py`, `tests/suru_kabul.py` (kabul testi). Ayrıntı: [server/README.md](server/README.md).

## Unity (eklenti)

Unity desteği ayrı depodadır: [apprentice-unity](https://github.com/malikkayaalp/apprentice-unity)
(çırağın Unity araç seti + Q3CNFU Editor paneli). Kurulum: o depoyu `envs/unity` olarak klonla;
`worker_run`'da `ortam="unity"` belirir. Cursor/Claude Code ile yalnızca kod işi yapanlar bunu atlar.

## Ölçülmüş tasarım kararları

- Başarı **Unity derleyicisiyle** doğrulanır, modelin beyanıyla değil. Play modu derleyicinin
  göremediği hataları yakalar; `play_observe` davranışı ölçer.
- Araç bloğu küçük ve sabit (tam MCP yüzeyi 20k token, bizimki 1.1k): her turda yeniden
  gönderilir, kullanılmayan araç sürekli ödenen vergidir.
- Yazmalar birikir, tek Refresh: dosya başına ~6 sn (bir domain reload) kazanç, ara durum hatası yok.
- Silme yetkisi varsayılan kapalı; açılırsa iki katmanlı sandbox hapsi (Python + C#).
- `num_batch` / `num_ctx` makineye özel — `apprentice.config.template.json` notlarına bakın.

## Durum

Unity ortamı ve paneli çalışıyor, uçtan uca doğrulandı. MCP sunucusu (`server/`) ve genel
kod ortamı (`envs/code/`) sırada. Bu depo laboratuvardan çıkarıldı (2026-08-22); her kararın
ölçüm kanıtı orada.

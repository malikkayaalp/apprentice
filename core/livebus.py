"""Canli olay veri yolu: test kosucusu yazar, live_server okur ve telefona akitir.

Neden dosya uzerinden: test kosucusu ile sunucu AYRI sureclerdir. Dosya araya girince
sunucu cokse/yeniden baslasa bile olay kaybi olmaz, kosucu da sunucuyu beklemez.
Her satir tek bir JSON olayidir (JSONL), boylece kismi yazma en fazla son satiri bozar.
"""
from __future__ import annotations

import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "reports", "live_events.jsonl")

_ENABLED = os.environ.get("LIVE", "1") != "0"


def reset():
    """Yeni bir batarya kosusunun basinda cagrilir."""
    if not _ENABLED:
        return
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write("")


def emit(kind: str, **kw):
    """Tek olay yaz. Yazma hatasi testi ASLA durdurmaz - canli goruntu ikincil."""
    if not _ENABLED:
        return
    try:
        rec = {"t": round(time.time(), 3), "kind": kind}
        rec.update(kw)
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

"""Apprentice MCP sunucusunun stdio sozlesme testi.

    python tests/test_server.py            # initialize, tools/list, worker_env (Unity/Ollama gerekmez)
    python tests/test_server.py --live     # + gercek worker_run (Ollama + Unity koprusu acik olmali)

Sunucuyu ayrik surec olarak baslatir ve gercek bir MCP istemcisi gibi konusur; boylece
stdout'a karisan tek bir yabanci satir bile burada yakalanir.
"""
from __future__ import annotations
import json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server", "apprentice_mcp.py")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Client:
    def __init__(self):
        self.p = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
        self._id = 0

    def call(self, method, params=None, timeout=60):
        self._id += 1
        rid = self._id
        self.p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                                        "params": params or {}}) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("sunucu kapandi: " + self.p.stderr.read().decode("utf-8", "replace")[-800:])
            msg = json.loads(line.decode("utf-8"))
            assert msg.get("jsonrpc") == "2.0", "bozuk satir: %r" % line[:200]
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]
        raise TimeoutError(method)

    def notify(self, method, params=None):
        self.p.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method,
                                        "params": params or {}}) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(5)
        except Exception:
            self.p.kill()


def main() -> int:
    live = "--live" in sys.argv
    c = Client()
    ok = True
    try:
        r = c.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "test", "version": "0"}})
        print("initialize:", r["serverInfo"], r["protocolVersion"])
        c.notify("notifications/initialized")
        assert c.call("ping") == {}
        tools = c.call("tools/list")["tools"]
        names = [t["name"] for t in tools]
        print("tools:", names)
        assert names == ["worker_run", "worker_status", "worker_env"], names
        for t in tools:
            assert t["inputSchema"]["type"] == "object"

        env = c.call("tools/call", {"name": "worker_env", "arguments": {}})["structuredContent"]
        print("worker_env:", json.dumps({k: v for k, v in env.items() if k != "ortamlar"}, ensure_ascii=False)[:300])
        print("  ortamlar:", json.dumps(env["ortamlar"], ensure_ascii=False)[:400])

        # Hata yollari: bos gorev, bilinmeyen ortam, planli ortam, bilinmeyen is
        r = c.call("tools/call", {"name": "worker_run", "arguments": {"gorev": "", "kabul_kriterleri": []}})
        assert r["isError"] and "bos" in r["structuredContent"]["hata"], r
        r = c.call("tools/call", {"name": "worker_run", "arguments": {"gorev": "x", "kabul_kriterleri": [], "ortam": "yok"}})
        assert r["isError"] and "bilinmeyen ortam" in r["structuredContent"]["hata"]
        r = c.call("tools/call", {"name": "worker_run", "arguments": {"gorev": "x", "kabul_kriterleri": [], "ortam": "code"}})
        assert r["isError"] and "planli" in r["structuredContent"]["hata"]
        r = c.call("tools/call", {"name": "worker_status", "arguments": {"is_id": "yok"}})
        assert r["isError"]
        try:
            c.call("tools/call", {"name": "yok", "arguments": {}})
            raise AssertionError("bilinmeyen arac hata vermedi")
        except RuntimeError as e:
            assert "bilinmeyen arac" in str(e)
        print("hata yollari: ok")

        if live:
            if not env["ortamlar"]["unity"]["hazir"] or not env["ollama"]["acik"]:
                print("LIVE atlandi: unity koprusu/ollama hazir degil")
            else:
                args = {"gorev": "Assets/Scripts/ApprenticeSmoke.cs adinda bir MonoBehaviour yaz.",
                        "kabul_kriterleri": ["Dosya derlenir, sinif adi ApprenticeSmoke.",
                                             "Start icinde Debug.Log(\"apprentice ok\") cagrilir.",
                                             "Baska hicbir sey yapmaz, Update yok."],
                        "ortam": "unity", "bekle": False}
                r = c.call("tools/call", {"name": "worker_run", "arguments": args})["structuredContent"]
                jid = r["is_id"]
                print("live is:", jid, r["durum"])
                t0 = time.time()
                while time.time() - t0 < 600:
                    time.sleep(5)
                    r = c.call("tools/call", {"name": "worker_status", "arguments": {"is_id": jid}})["structuredContent"]
                    print("  %4.0fs %s araclar=%d" % (time.time() - t0, r["durum"], len(r["araclar"])))
                    if r["durum"] == "bitti":
                        break
                print(json.dumps({k: r[k] for k in ("ok", "derleme", "dosyalar", "ozet", "hata", "sure_s")},
                                 ensure_ascii=False, indent=1))
                ok = ok and r["ok"] is True and any(d["yol"].endswith("ApprenticeSmoke.cs") for d in r["dosyalar"])
    except Exception as e:
        ok = False
        print("HATA:", e)
    finally:
        c.close()
        err = c.p.stderr.read().decode("utf-8", "replace")
        if err.strip():
            print("--- sunucu stderr ---\n" + err[-1500:])
    print("SONUC:", "GECTI" if ok else "KALDI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

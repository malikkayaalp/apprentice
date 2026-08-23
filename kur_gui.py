"""Apprentice Setup - grafik kurulum (tkinter, ek bagimlilik yok).

Her yerden calisir: Apprentice dosyalari exe'nin icinde gomulu (payload.zip), kullanici kurulum
klasorunu secer, dosyalar oraya acilir; sonra kur.py motoru adim adim kosar:
Python (gerekirse gomulu) -> Ollama -> model (ilerleme cubugu) -> IDE ayarlari -> oz-test.

Gelistirme: python kur_gui.py  (payload yerine bu depo klasoru kopyalanir)
Paketleme: python kur_build.py  ->  dist/Apprentice-Setup.exe
"""
from __future__ import annotations
import os, sys, threading, zipfile, webbrowser, shutil, queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

BURASI = os.path.dirname(os.path.abspath(__file__))
DONMUS = getattr(sys, "frozen", False)
PAYLOAD = os.path.join(getattr(sys, "_MEIPASS", BURASI), "payload.zip")
VARSAYILAN_KOK = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Apprentice") \
    if os.name == "nt" else os.path.join(os.path.expanduser("~"), "apprentice")

ADIMLAR = [("dosyalar", "Apprentice dosyaları"), ("python", "Python"), ("ollama", "Ollama"),
           ("model", "Yerel model (Qwen3-Coder-Next, ~20 GB)"), ("ide", "IDE bağlantıları"),
           ("test", "Öz-test")]


def dosyalari_ac(kok: str, log) -> bool:
    """payload.zip'i (exe) ya da gelistirme klasorunu kuruluma kopyala."""
    os.makedirs(kok, exist_ok=True)
    if os.path.isfile(PAYLOAD):
        with zipfile.ZipFile(PAYLOAD) as z:
            z.extractall(kok)
            n = len(z.namelist())
        log("[ok]  %d dosya açıldı → %s" % (n, kok))
        return True
    # gelistirme: depo klasorunu kopyala (kendi kendine kopyalama yok)
    if os.path.abspath(kok) == os.path.abspath(BURASI):
        log("[ok]  Geliştirme kipi: depo klasörü kurulum klasörü olarak kullanılıyor")
        return True
    for ad in ("core", "mcpbridge", "server", "envs", "clients", "tests", "apprentice.config.template.json",
               ".mcp.json", "kur.py", "README.md"):
        src = os.path.join(BURASI, ad)
        dst = os.path.join(kok, ad)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "unity", ".apprentice_test_home"))
        elif os.path.isfile(src):
            shutil.copy2(src, dst)
    log("[ok]  Dosyalar kopyalandı → %s" % kok)
    return True


class Sihirbaz(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Apprentice Setup")
        self.geometry("820x560")
        self.minsize(760, 520)
        self.kuyruk = queue.Queue()
        self.durum = {k: "bekliyor" for k, _ in ADIMLAR}
        self.ollama_eksik = False
        self._kur_ui()
        self.after(100, self._kuyruk_isle)

    # ---------------------------------------------------------------- UI
    def _kur_ui(self):
        st = ttk.Style(self)
        try:
            st.theme_use("vista" if os.name == "nt" else "clam")
        except Exception:
            pass
        ust = ttk.Frame(self, padding=(16, 12))
        ust.pack(fill="x")
        ttk.Label(ust, text="Apprentice", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(ust, text="A local model does the work, a frontier model supervises.",
                  foreground="#666").pack(anchor="w")

        govde = ttk.Frame(self, padding=(16, 4))
        govde.pack(fill="both", expand=True)
        govde.columnconfigure(1, weight=1)
        govde.rowconfigure(2, weight=1)

        # sol: adimlar
        sol = ttk.LabelFrame(govde, text="Adımlar", padding=10)
        sol.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 12))
        self.adim_etiket = {}
        for k, ad in ADIMLAR:
            e = ttk.Label(sol, text="○  " + ad, font=("Segoe UI", 10))
            e.pack(anchor="w", pady=3)
            self.adim_etiket[k] = (e, ad)

        # sag ust: klasor
        kl = ttk.LabelFrame(govde, text="Kurulum klasörü", padding=10)
        kl.grid(row=0, column=1, sticky="ew")
        kl.columnconfigure(0, weight=1)
        self.kok_var = tk.StringVar(value=VARSAYILAN_KOK)
        ttk.Entry(kl, textvariable=self.kok_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(kl, text="Gözat…", command=self._gozat).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(kl, text="Dosyalar bu klasöre açılır; IDE'ler sunucuyu buradan çalıştırır. "
                           "Python yoksa gömülü Python da buraya iner.", foreground="#666",
                  wraplength=520).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # sag orta: ilerleme
        il = ttk.Frame(govde)
        il.grid(row=1, column=1, sticky="ew", pady=(10, 4))
        il.columnconfigure(0, weight=1)
        self.ilerleme_var = tk.DoubleVar(value=0)
        self.ilerleme = ttk.Progressbar(il, variable=self.ilerleme_var, maximum=100)
        self.ilerleme.grid(row=0, column=0, sticky="ew")
        self.ilerleme_metin = ttk.Label(il, text="Hazır.", foreground="#444")
        self.ilerleme_metin.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # sag alt: log
        lg = ttk.LabelFrame(govde, text="Ayrıntı", padding=6)
        lg.grid(row=2, column=1, sticky="nsew")
        lg.rowconfigure(0, weight=1); lg.columnconfigure(0, weight=1)
        self.log_kutu = tk.Text(lg, height=10, wrap="word", font=("Consolas", 9), state="disabled",
                                background="#fafafa", relief="flat")
        self.log_kutu.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lg, command=self.log_kutu.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_kutu.configure(yscrollcommand=sb.set)
        self.log_kutu.tag_configure("ok", foreground="#1a7f37")
        self.log_kutu.tag_configure("hata", foreground="#b42318")
        self.log_kutu.tag_configure("uyari", foreground="#b54708")

        # alt: dugmeler
        alt = ttk.Frame(self, padding=(16, 8))
        alt.pack(fill="x")
        self.btn_ollama = ttk.Button(alt, text="Ollama'yı indir", command=lambda: webbrowser.open("https://ollama.com/download"))
        self.btn_kural = ttk.Button(alt, text="Projeye denetçi kuralı ekle…", command=self._kural, state="disabled")
        self.btn_kural.pack(side="left")
        self.btn_kapat = ttk.Button(alt, text="Kapat", command=self.destroy)
        self.btn_kapat.pack(side="right")
        self.btn_kur = ttk.Button(alt, text="Kur", command=self._baslat)
        self.btn_kur.pack(side="right", padx=(0, 8))

    def _gozat(self):
        d = filedialog.askdirectory(initialdir=os.path.dirname(self.kok_var.get()) or os.path.expanduser("~"))
        if d:
            self.kok_var.set(os.path.join(d, "Apprentice") if os.path.basename(d).lower() != "apprentice" else d)

    # ---------------------------------------------------------------- log / durum (is parcacigindan)
    def log(self, metin: str):
        self.kuyruk.put(("log", metin))
        try:                                    # pencere kipinde stderr yok: gunluk dosyaya da
            with open(os.path.join(self.kok_var.get() or BURASI, "kurulum.log"), "a", encoding="utf-8") as f:
                f.write(metin.rstrip() + chr(10))
        except Exception:
            pass

    def ilerle(self, yuzde, metin):
        self.kuyruk.put(("ilerleme", (yuzde, metin)))

    def adim_durum(self, k: str, d: str):
        self.kuyruk.put(("adim", (k, d)))

    def _kuyruk_isle(self):
        try:
            while True:
                tur, veri = self.kuyruk.get_nowait()
                if tur == "log":
                    self._log_yaz(veri)
                elif tur == "ilerleme":
                    y, m = veri
                    if y is None:
                        self.ilerleme.configure(mode="indeterminate"); self.ilerleme.start(12)
                    else:
                        self.ilerleme.stop(); self.ilerleme.configure(mode="determinate"); self.ilerleme_var.set(y)
                    self.ilerleme_metin.configure(text=m)
                elif tur == "adim":
                    k, d = veri
                    e, ad = self.adim_etiket[k]
                    sim = {"bekliyor": "○", "calisiyor": "⟳", "ok": "✓", "hata": "✗", "uyari": "!"}[d]
                    renk = {"ok": "#1a7f37", "hata": "#b42318", "uyari": "#b54708"}.get(d, "#000")
                    e.configure(text="%s  %s" % (sim, ad), foreground=renk)
                elif tur == "bitti":
                    self._bitti(veri)
        except queue.Empty:
            pass
        self.after(100, self._kuyruk_isle)

    def _log_yaz(self, metin: str):
        self.log_kutu.configure(state="normal")
        tag = "ok" if metin.startswith("[ok]") else "hata" if metin.startswith("[X]") else "uyari" if metin.startswith("[!]") else ""
        self.log_kutu.insert("end", metin.rstrip("\n") + "\n", tag)
        self.log_kutu.see("end")
        self.log_kutu.configure(state="disabled")

    # ---------------------------------------------------------------- kurulum
    def _baslat(self):
        kok = self.kok_var.get().strip()
        if not kok:
            messagebox.showerror("Apprentice", "Kurulum klasörü boş.")
            return
        self.btn_kur.configure(state="disabled")
        threading.Thread(target=self._kur, args=(kok,), daemon=True).start()

    def _kur(self, kok: str):
        sonuc = {}
        try:
            self.adim_durum("dosyalar", "calisiyor")
            self.ilerle(None, "Dosyalar açılıyor…")
            ok = dosyalari_ac(kok, self.log)
            self.adim_durum("dosyalar", "ok" if ok else "hata")
            sonuc["dosyalar"] = ok
            if not ok:
                raise RuntimeError("dosyalar açılamadı")

            sys.path.insert(0, kok)
            import importlib
            kur = importlib.import_module("kur") if "kur" not in sys.modules else sys.modules["kur"]
            kur.set_root(kok)
            kur.log = self.log
            kur.ilerleme = self.ilerle
            kur.DEGISTIR = True

            def calistir(k, fn):
                self.adim_durum(k, "calisiyor")
                self.ilerle(None, "%s kontrol ediliyor…" % dict(ADIMLAR)[k])
                try:
                    r = bool(fn())
                except Exception as e:  # noqa: BLE001
                    self.log("[X]   %s: %s" % (k, str(e)[:300]))
                    r = False
                self.adim_durum(k, "ok" if r else "hata")
                self.ilerle(100 if r else 0, "")
                sonuc[k] = r
                return r

            calistir("python", kur.kontrol_python)
            if not calistir("ollama", kur.kontrol_ollama):
                self.ollama_eksik = True
                self.adim_durum("model", "uyari")
                sonuc["model"] = False
            else:
                calistir("model", kur.kontrol_model)
            calistir("ide", lambda: (kur.kontrol_ideler(""), kur.mcp_json_guncelle())[0])
            calistir("test", kur.oz_test)
        except Exception as e:  # noqa: BLE001
            import traceback
            self.log("[X]   %s" % e)
            self.log(traceback.format_exc())
        self.kuyruk.put(("bitti", sonuc))

    def _bitti(self, sonuc: dict):
        self._son_ok = all(sonuc.get(k) for k, _ in ADIMLAR)
        if getattr(self, "_oto", False):
            self.log("[ok]  sessiz kurulum bitti: %s" % self._son_ok)
            self.after(500, self.destroy)
            return
        self.btn_kur.configure(state="normal", text="Tekrar dene")
        self.btn_kural.configure(state="normal")
        if self.ollama_eksik:
            self.btn_ollama.pack(side="left", padx=(8, 0))
        if all(sonuc.get(k) for k, _ in ADIMLAR):
            self.ilerle(100, "Kurulum tamam. IDE'ni aç; MCP listesinde 'apprentice' yeşil olmalı.")
            messagebox.showinfo("Apprentice", "Kurulum tamamlandı.\n\nIDE'ni (Cursor / VS Code / Windsurf) aç ya da "
                                "yenile; MCP listesinde 'apprentice' görünecek.\n\nBir projede kullanmak için "
                                "'Projeye denetçi kuralı ekle' ile projeyi seç.")
        else:
            eksik = [dict(ADIMLAR)[k] for k, _ in ADIMLAR if not sonuc.get(k)]
            self.ilerle(0, "Eksik: " + ", ".join(eksik) + " — ayrıntı panelindeki [X] satırlarına bak.")

    def _kural(self):
        d = filedialog.askdirectory(title="Proje klasörü")
        if not d:
            return
        try:
            kur = sys.modules["kur"]
            kur.kural_yaz(d)
            messagebox.showinfo("Apprentice", "Kural dosyaları yazıldı:\n%s\\.cursor\\rules\\apprentice.mdc\n%s\\APPRENTICE.md" % (d, d))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Apprentice", str(e))


if __name__ == "__main__":
    app = Sihirbaz()
    oto = os.environ.get("APPRENTICE_SETUP_AUTO")       # sessiz kurulum / test: klasoru ver, kendisi kurar ve kapanir
    if oto:
        app.kok_var.set(oto)
        app._oto = True
        app.after(300, app._baslat)
    app.mainloop()
    sys.exit(0 if getattr(app, "_son_ok", False) else 1)

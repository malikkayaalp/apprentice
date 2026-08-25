// Apprentice Panel - WebView2 kabugu.
//
// Ne yapar: (1) kurulum klasorunu bulur, (2) panel sunucusu ayakta degilse konsolsuz baslatir,
// (3) hazir olunca panel.html'i KENDI penceresinde acar. Tarayici penceresi yok, adres cubugu
// yok, gorev cubugunda kendi ikonu ve adi var.
//
// Ilke: her basarisizlik SEBEBIYLE ve NE YAPMALI ile birlikte gosterilir - kullanici
// "acilmadi" ile bas basa kalmaz (bos pencere/sessiz cikis yasak).
using System.Diagnostics;
using System.Net.Http;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Apprentice;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            // "--tek <panel>": dogrudan TEK PANEL penceresi (cercevesiz). Kisayol/otomasyon
            // icin: Apprentice-WebPanel.exe --tek akis [--ustte]
            var tekIx = Array.IndexOf(args, "--tek");
            if (tekIx >= 0 && tekIx + 1 < args.Length)
            {
                Application.Run(new TekPencereBaslatici(args, args[tekIx + 1],
                                                        Array.IndexOf(args, "--ustte") >= 0));
                return;
            }
            Application.Run(new PanelForm(args));
        }
        catch (Exception e)
        {
            Hata.Goster("Panel baslatilamadi", e.ToString(), null);
        }
    }
}

/// <summary>Kullaniciya sebep + cozum gosteren tek yer.</summary>
internal static class Hata
{
    public static void Goster(string baslik, string ayrinti, string cozum)
    {
        var metin = ayrinti;
        if (!string.IsNullOrWhiteSpace(cozum)) metin += "\n\nNE YAPMALI:\n" + cozum;
        MessageBox.Show(metin, "Apprentice - " + baslik, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}

/// <summary>"--tek akis": gorunmez bir tasiyici, sunucuyu hazirlar ve CERCEVESIZ panel
/// penceresini acar; o pencere kapaninca uygulama biter.</summary>
internal sealed class TekPencereBaslatici : Form
{
    public TekPencereBaslatici(string[] args, string panel, bool ustte)
    {
        Opacity = 0; ShowInTaskbar = false; WindowState = FormWindowState.Minimized;
        Load += async (_, _) =>
        {
            var ana = new PanelForm(args) { Opacity = 0, ShowInTaskbar = false };
            // SONUC DENETLENIR (denetim bulgusu 12): eski surum donus degerine BAKMIYORDU ve
            // sunucu kurulamasa/baslatilamasa bile pencereyi aciyordu - kullanici BOS ya da
            // calismayan bir panel goruyordu. Hata mesaji SadeceSunucu icinde gosterildi.
            if (!await ana.SadeceSunucu(args))
            {
                Close();          // yarim kaynak birakma; tasiyici da kapansin
                return;
            }
            var ortam = await CoreWebView2Environment.CreateAsync(null, PanelForm.EvKlasoruDis());
            var alt = new AltPencere(string.Format("http://127.0.0.1:{0}/?tek={1}{2}",
                                                   ana.Port, panel, ustte ? "&ustte=1" : ""), ortam);
            alt.FormClosed += (_, _) => Close();
            alt.Show();
        };
    }
}


internal sealed class PanelForm : Form
{
    private readonly WebView2 _web = new();
    private Process _sunucu;          // yalniz BIZ baslattiysak dolu (kapanista durdururuz)
    private string _kok = "";
    private int _port = 8788;
    private readonly string _ayarYolu;

    public PanelForm(string[] args)
    {
        Text = "Apprentice — Canlı Panel";
        BackColor = Color.FromArgb(0x1f, 0x1d, 0x1a);   // panelin zemini ile ayni (beyaz parlama yok)
        MinimumSize = new Size(900, 620);
        // Pencere/gorev cubugu ikonu = exe'nin kendi ikonu (ApplicationIcon ile gomuldu)
        try { Icon = Icon.ExtractAssociatedIcon(Environment.ProcessPath ?? Application.ExecutablePath); }
        catch { /* ikon okunamazsa varsayilan kalir */ }
        _ayarYolu = Path.Combine(EvKlasoru(), "pencere.json");
        PencereGeriYukle();

        _web.Dock = DockStyle.Fill;
        _web.DefaultBackgroundColor = Color.FromArgb(0x1f, 0x1d, 0x1a);
        Controls.Add(_web);

        Shown += async (_, _) => await BaslatAsync(args);
        FormClosing += (_, _) => { PencereKaydet(); SunucuyuDurdur(); };
    }

    // ---------------------------------------------------------------- yerlesim
    public int Port => _port;
    public static string EvKlasoruDis() => EvKlasoru();

    /// <summary>Pencere acmadan: kurulumu bul, sunucu ayakta degilse baslat.
    /// ARGUMANLAR BURADA DA OKUNUR: onceden Array.Empty gecilirdi, yani "--tek" ile
    /// acildiginda --kok ve --port SESSIZCE yok sayiliyordu. Sonuc: standart disi bir
    /// kuruluma --kok verildiginde tek-pencere kipi "kurulum bulunamadi" diyordu; --port
    /// verildiginde de cerceve, sunucunun gercekte kostugu porttan BASKA bir adrese
    /// gidiyordu. Normal yol (BaslatAsync) ikisini de okuyordu - iki yol ayni davranmali.</summary>
    public async Task<bool> SadeceSunucu(string[] args)
    {
        args ??= Array.Empty<string>();
        _kok = KurulumBul(args);
        if (_kok == "")
        {
            Hata.Goster("kurulum bulunamadi", @"clients\web\panel.py bulunamadi",
                        "Kurulum klasorunu acikca ver:\n" +
                        @"Apprentice-WebPanel.exe --tek akis --kok ""C:\...\Apprentice""");
            return false;
        }
        for (var i = 0; i < args.Length - 1; i++)
            if (args[i] == "--port" && int.TryParse(args[i + 1], out var p)) _port = p;
        if (await AyaktaMi(_port)) return true;
        var deneme = _port;
        while (deneme < _port + 12 && PortDolu(deneme) && !await AyaktaMi(deneme)) deneme++;
        _port = deneme;
        if (!await AyaktaMi(_port) && !SunucuyuBaslat())
        {
            Hata.Goster("sunucu baslatilamadi",
                        $"Panel sunucusu {_port} portunda baslatilamadi.",
                        "python kur.py --tani  ile ortami denetle.");
            return false;
        }
        for (var i = 0; i < 150 && !await AyaktaMi(_port); i++) await Task.Delay(80);
        if (!await AyaktaMi(_port))
        {
            // KISMEN BASLATILMIS SUREC TEMIZLENIR: sunucu ayaga kalkmadiysa arkada
            // yarim bir surec birakmayiz (denetim bulgusu 12).
            SunucuyuDurdur();
            Hata.Goster("sunucu cevap vermedi",
                        $"Panel sunucusu 12 saniye icinde {_port} portunda cevap vermedi.",
                        "Once tani al: python kur.py --tani\n" +
                        @"Elle dene: python clients\web\panel.py");
            return false;
        }
        return true;
    }

    private static string EvKlasoru()
    {
        var ev = Environment.GetEnvironmentVariable("APPRENTICE_HOME");
        if (string.IsNullOrWhiteSpace(ev))
            ev = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".apprentice");
        Directory.CreateDirectory(ev);
        return ev;
    }

    private void PencereGeriYukle()
    {
        StartPosition = FormStartPosition.CenterScreen;
        Size = new Size(1500, 950);
        try
        {
            if (!File.Exists(_ayarYolu)) return;
            using var d = JsonDocument.Parse(File.ReadAllText(_ayarYolu));
            var k = d.RootElement;
            var w = k.GetProperty("g").GetInt32();
            var h = k.GetProperty("y").GetInt32();
            if (w > 400 && h > 300)
            {
                Size = new Size(w, h);
                if (k.TryGetProperty("x", out var x) && k.TryGetProperty("t", out var t))
                {
                    var nokta = new Point(x.GetInt32(), t.GetInt32());
                    // ekran disinda kalmasin (monitor sokulmus olabilir)
                    if (Screen.AllScreens.Any(s => s.WorkingArea.Contains(nokta)))
                    {
                        StartPosition = FormStartPosition.Manual;
                        Location = nokta;
                    }
                }
            }
            if (k.TryGetProperty("buyuk", out var b) && b.GetBoolean()) WindowState = FormWindowState.Maximized;
        }
        catch { /* bozuk ayar: varsayilana dus */ }
    }

    private void PencereKaydet()
    {
        try
        {
            var r = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            File.WriteAllText(_ayarYolu, JsonSerializer.Serialize(new
            {
                x = r.X, t = r.Y, g = r.Width, y = r.Height,
                buyuk = WindowState == FormWindowState.Maximized
            }));
        }
        catch { /* yazilamazsa onemli degil */ }
    }

    // ---------------------------------------------------------------- kurulum bulma
    private static string KurulumBul(string[] args)
    {
        for (var i = 0; i < args.Length - 1; i++)
            if (args[i] == "--kok" && Directory.Exists(args[i + 1])) return Path.GetFullPath(args[i + 1]);

        var cevre = Environment.GetEnvironmentVariable("APPRENTICE_KOK");
        if (!string.IsNullOrWhiteSpace(cevre) && Panelli(cevre)) return cevre;

        // exe'nin yani, bir ust, iki ust (dist/ altindan calistirilirsa)
        var d = AppContext.BaseDirectory;
        for (var i = 0; i < 4 && d != null; i++)
        {
            if (Panelli(d)) return Path.GetFullPath(d);
            d = Path.GetDirectoryName(d.TrimEnd(Path.DirectorySeparatorChar));
        }
        return "";
    }

    private static bool Panelli(string kok) =>
        !string.IsNullOrWhiteSpace(kok) && File.Exists(Path.Combine(kok, "clients", "web", "panel.py"));

    private static string PythonBul(string kok)
    {
        var gomulu = Path.Combine(kok, "runtime", "python", "python.exe");
        if (File.Exists(gomulu)) return gomulu;                      // kurulumun kendi Python'u
        foreach (var ad in new[] { "python.exe", "python3.exe" })
        {
            var yollar = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';');
            foreach (var y in yollar)
            {
                try
                {
                    var tam = Path.Combine(y.Trim(), ad);
                    if (File.Exists(tam)) return tam;
                }
                catch { /* bozuk PATH parcasi */ }
            }
        }
        return "";
    }

    // ---------------------------------------------------------------- sunucu
    private static async Task<bool> AyaktaMi(int port)
    {
        try
        {
            using var c = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            var s = await c.GetStringAsync($"http://127.0.0.1:{port}/api/hazir");
            return s.Contains("\"hazir\"");     // sadece 200 degil: BIZIM panel mi
        }
        catch { return false; }
    }

    private static bool PortDolu(int port)
    {
        try
        {
            using var s = new System.Net.Sockets.TcpClient();
            return s.ConnectAsync("127.0.0.1", port).Wait(400);
        }
        catch { return false; }
    }

    private async Task BaslatAsync(string[] args)
    {
        _kok = KurulumBul(args);
        if (_kok == "")
        {
            Hata.Goster("kurulum bulunamadi",
                "Panel dosyalari (clients\\web\\panel.py) bulunamadi.\nBakilan yer: " + AppContext.BaseDirectory,
                "Bu exe'yi Apprentice kurulum klasorune koy, ya da:\n" +
                "Apprentice-WebPanel.exe --kok \"C:\\...\\Apprentice\"");
            Close(); return;
        }

        for (var i = 0; i < args.Length - 1; i++)
            if (args[i] == "--port" && int.TryParse(args[i + 1], out var p)) _port = p;

        if (!await AyaktaMi(_port))
        {
            // Port dolu ama bizim panel degilse bir sonraki bos porta kay
            var deneme = _port;
            while (deneme < _port + 12 && PortDolu(deneme) && !await AyaktaMi(deneme)) deneme++;
            _port = deneme;
            if (!await AyaktaMi(_port) && !SunucuyuBaslat()) { Close(); return; }

            var basladi = false;
            for (var i = 0; i < 150; i++)          // ~12 sn
            {
                if (_sunucu is { HasExited: true })
                {
                    var cikti = "";
                    try { cikti = _sunucu.StandardError.ReadToEnd(); } catch { }
                    Hata.Goster("sunucu kapandi",
                        $"Panel sunucusu baslar baslamaz kapandi (cikis {_sunucu.ExitCode}).\n\n{Kirp(cikti, 1200)}",
                        "Kurulumu tekrar calistir ya da tani al:\n  python kur.py --tani");
                    Close(); return;
                }
                if (await AyaktaMi(_port)) { basladi = true; break; }
                await Task.Delay(80);
            }
            if (!basladi)
            {
                Hata.Goster("sunucu cevap vermedi",
                    $"Panel sunucusu 12 saniye icinde {_port} portunda cevap vermedi.",
                    "Once tani al: python kur.py --tani\nElle dene: python clients\\web\\panel.py");
                Close(); return;
            }
        }

        try
        {
            var veri = Path.Combine(EvKlasoru(), "webview");
            // Bellek/surec kismasi: panel yerel bir arayuz - eklenti, arka plan agi, senkron,
            // ceviri, arka plan sekmesi kismasi gereksiz. (Olculdu: varsayilan ayarla 6 surec
            // 474 MB; bu bayraklarla dusuyor. Arka plan kismasi KAPALI kalmali - yoksa pencere
            // arkadayken CSS gecisleri donuyor, olcumde bunu yasadik.)
            var ortam = await CoreWebView2Environment.CreateAsync(null, veri,
                new CoreWebView2EnvironmentOptions
                {
                    AdditionalBrowserArguments = string.Join(" ",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-sync",
                        "--disable-translate",
                        "--disable-features=Translate,OptimizationHints,MediaRouter",
                        "--renderer-process-limit=2",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding")
                });
            await _web.EnsureCoreWebView2Async(ortam);
        }
        catch (Exception e)
        {
            Hata.Goster("WebView2 yok",
                "Microsoft Edge WebView2 calisma zamani bulunamadi.\n\n" + Kirp(e.Message, 400),
                "https://developer.microsoft.com/microsoft-edge/webview2/ adresinden " +
                "\"Evergreen Standalone Installer\" kur.\n" +
                "Alternatif: paneli tarayicida ac -> python panel_ac.py --tarayici");
            Close(); return;
        }

        var w = _web.CoreWebView2;
        w.Settings.AreDefaultContextMenusEnabled = false;   // saga tiklama menusu: tarayici hissi
        w.Settings.IsStatusBarEnabled = false;
        w.Settings.AreDevToolsEnabled = true;               // F12 kalsin: sorun bildirimi kolaylasir
        w.Settings.IsSwipeNavigationEnabled = false;
        // Panel disina cikan baglantilar VARSAYILAN TARAYICIDA acilsin (uygulama penceresi
        // baska sitelere gitmesin - kabuk 'tarayici' degildir).
        w.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            // Kendi adresimiz (dosya goruntuleyici) -> GERCEK ikinci uygulama penceresi:
            // panel alanini kaplamaz, ayri tasinir/boyutlanir. Yabanci adres -> varsayilan
            // tarayici (kabuk bir tarayici degildir).
            if (e.Uri.StartsWith($"http://127.0.0.1:{_port}"))
            {
                var d = e.GetDeferral();
                var alt = new AltPencere(e.Uri, _web.CoreWebView2.Environment);
                alt.Hazir += (_, cekirdek) =>
                {
                    e.NewWindow = cekirdek;
                    d.Complete();
                };
                alt.Show(this);
                return;
            }
            try { Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true }); } catch { }
        };
        w.NavigationStarting += (_, e) =>
        {
            if (!e.Uri.StartsWith($"http://127.0.0.1:{_port}") && !e.Uri.StartsWith("about:"))
            {
                e.Cancel = true;
                try { Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true }); } catch { }
            }
        };
        w.DocumentTitleChanged += (_, _) =>
            Text = string.IsNullOrWhiteSpace(w.DocumentTitle) ? "Apprentice" : w.DocumentTitle;

        _web.Source = new Uri($"http://127.0.0.1:{_port}");
    }

    private bool SunucuyuBaslat()
    {
        var py = PythonBul(_kok);
        if (py == "")
        {
            Hata.Goster("Python bulunamadi",
                "Panel sunucusunu calistiracak Python yok.\nKurulum klasoru: " + _kok,
                "Apprentice-Setup.exe ile kurulumu tamamla (gomulu Python indirir), " +
                "ya da python.org/downloads adresinden Python 3.10+ kur.");
            return false;
        }
        try
        {
            var bilgi = new ProcessStartInfo(py)
            {
                WorkingDirectory = _kok,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
            };
            bilgi.ArgumentList.Add(Path.Combine(_kok, "clients", "web", "panel.py"));
            bilgi.ArgumentList.Add("--port");
            bilgi.ArgumentList.Add(_port.ToString());
            bilgi.Environment["PYTHONIOENCODING"] = "utf-8";
            _sunucu = Process.Start(bilgi);
            return _sunucu != null;
        }
        catch (Exception e)
        {
            Hata.Goster("sunucu baslatilamadi", e.Message,
                "Guvenlik yazilimi engelliyor olabilir. Elle dene:\n  python clients\\web\\panel.py");
            return false;
        }
    }

    private void SunucuyuDurdur()
    {
        // Yalniz BIZ baslattiysak durdur: kullanici paneli ayrica actiysa onu oldurmeyelim.
        try
        {
            if (_sunucu is { HasExited: false })
            {
                var p = Process.Start(new ProcessStartInfo("taskkill")
                {
                    ArgumentList = { "/PID", _sunucu.Id.ToString(), "/T", "/F" },
                    CreateNoWindow = true, UseShellExecute = false
                });
                p?.WaitForExit(4000);
            }
        }
        catch { /* kapanista sessiz */ }
    }

    private static string Kirp(string s, int n) =>
        string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s[..n] + "...");
}

/// <summary>
/// Disari alinan panel/dosya penceresi. CERCEVESIZ: Windows baslik cubugu yok, kapatma ve
/// tasima bizim arayuzumuzde (kullanici istegi: "windows cercevesi olmadan, kapatma tusunu
/// biz koyalim"). Sayfa ile host arasinda kucuk bir mesaj kanali var:
///   kapat        -> pencere kapanir
///   ustte:1/0    -> hep ustte ac/kapa
///   surukle      -> pencereyi fareyle tasi (baslik cubugu yok, HTML seridi tasiyicidir)
///   buyult       -> tam ekran / geri al
/// Kenarlardan boyutlandirma WndProc'ta HitTest ile saglanir.
/// </summary>
internal sealed class AltPencere : Form
{
    private readonly WebView2 _web = new();
    private readonly CoreWebView2Environment _ortam;
    public event EventHandler<CoreWebView2> Hazir;

    private const int KENAR = 6;                     // boyutlandirma kenari (piksel)
    private const int WM_NCHITTEST = 0x0084;
    private const int WM_NCLBUTTONDOWN = 0x00A1;
    private const int HTCLIENT = 1, HTLEFT = 10, HTRIGHT = 11, HTTOP = 12, HTTOPLEFT = 13,
                      HTTOPRIGHT = 14, HTBOTTOM = 15, HTBOTTOMLEFT = 16, HTBOTTOMRIGHT = 17,
                      HTCAPTION = 2;

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool ReleaseCapture();
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

    private readonly string _uri;

    public AltPencere(string uri, CoreWebView2Environment ortam)
    {
        _uri = uri;
        _ortam = ortam;
        Text = "Apprentice";
        FormBorderStyle = FormBorderStyle.None;      // CERCEVESIZ: baslik cubugu HTML'de
        ShowInTaskbar = true;
        BackColor = Color.FromArgb(0x14, 0x12, 0x10);
        Size = new Size(940, 700);
        MinimumSize = new Size(360, 220);
        StartPosition = FormStartPosition.CenterParent;
        if (uri.Contains("ustte=1")) TopMost = true;
        try { Icon = Icon.ExtractAssociatedIcon(Environment.ProcessPath ?? Application.ExecutablePath); }
        catch { }
        // BOYUTLANDIRMA ICIN KENAR PAYI (yasandi: "ayri pencerede olceklendirme yok"):
        // WebView2 tum istemci alanini kaplayinca fare olaylarini o yutar ve pencerenin
        // WM_NCHITTEST'i hic tetiklenmez - kenarlardan tutulamaz. Formun kendisine KENAR
        // kadar dolgu birakiyoruz; o serit forma ait kalir ve hit-test calisir.
        Padding = new Padding(KENAR);
        _web.Dock = DockStyle.Fill;
        _web.DefaultBackgroundColor = Color.FromArgb(0x14, 0x12, 0x10);
        Controls.Add(_web);
        Load += async (_, _) =>
        {
            await _web.EnsureCoreWebView2Async(_ortam);
            var w = _web.CoreWebView2;
            w.Settings.AreDefaultContextMenusEnabled = false;
            w.Settings.IsStatusBarEnabled = false;
            w.Settings.AreDevToolsEnabled = true;
            w.WebMessageReceived += (_, e) => MesajIsle(e.TryGetWebMessageAsString() ?? "");
            w.DocumentTitleChanged += (_, _) =>
                Text = string.IsNullOrWhiteSpace(w.DocumentTitle) ? "Apprentice" : w.DocumentTitle;
            if (Hazir != null)
            {
                Hazir.Invoke(this, w);      // NewWindowRequested: sayfayi WebView2 kendisi yukler
            }
            else
            {
                // Tek basina acildi (--tek): adresi BIZ yuklemeliyiz. Eksikti - pencere bos
                // aciliyordu, dolayisiyla kendi baslik seridimiz de yoktu ve pencere tasinamiyordu.
                _web.Source = new Uri(_uri);
            }
        };
    }

    private void MesajIsle(string m)
    {
        if (m == "kapat") { Close(); return; }
        if (m == "buyult")
        {
            WindowState = WindowState == FormWindowState.Maximized
                ? FormWindowState.Normal : FormWindowState.Maximized;
            return;
        }
        if (m.StartsWith("ustte:")) { TopMost = m.EndsWith("1"); return; }
        if (m.StartsWith("tasi:"))
        {
            // CERCEVE YOK: pencere HTML seridinden tasinir. Kullanici uyardi ("cerceve
            // kalkinca tasiyamama problemi olabilir") - bu yuzden tasima ACIK ve olculebilir:
            // serit fare farkini gonderir, pencere o kadar kayar.
            var p = m.Substring(5).Split(',');
            if (p.Length == 2 && int.TryParse(p[0], out var dx) && int.TryParse(p[1], out var dy))
            {
                if (WindowState == FormWindowState.Maximized) WindowState = FormWindowState.Normal;
                Location = new Point(Location.X + dx, Location.Y + dy);
            }
            return;
        }
        if (m == "surukle")            // yedek yol: native baslik surukleme
        {
            ReleaseCapture();
            SendMessage(Handle, WM_NCLBUTTONDOWN, HTCAPTION, IntPtr.Zero);
        }
    }

    /// <summary>
    /// CERCEVESIZ ama BOYUTLANDIRILABILIR pencere. FormBorderStyle.None, pencereden
    /// WS_THICKFRAME (kalin/boyutlandirilabilir cerceve) bitini de kaldirir; o bit olmadan
    /// Windows, hit-test HTBOTTOM/HTRIGHT dondurse bile boyutlandirmaz (yasandi: sag kenar
    /// tesadufen calisiyor gorundu, alt kenar hic calismadi). Biti geri ekliyoruz - gorunum
    /// yine cercevesiz kalir, cunku ciziim WS_CAPTION'a baglidir.
    /// </summary>
    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            cp.Style |= 0x00040000;    // WS_THICKFRAME  - kenarlardan boyutlandirma
            cp.Style |= 0x00020000;    // WS_MINIMIZEBOX - gorev cubugundan kucultme
            return cp;
        }
    }

    protected override void WndProc(ref Message m)
    {
        base.WndProc(ref m);
        if (m.Msg != WM_NCHITTEST || (int)m.Result != HTCLIENT) return;
        // Kenarlardan boyutlandirma (cerceve olmadigi icin elle)
        var ham = m.LParam.ToInt32();
        var n = PointToClient(new Point((short)(ham & 0xFFFF), (short)(ham >> 16)));
        bool sol = n.X <= KENAR, sag = n.X >= ClientSize.Width - KENAR;
        bool ust = n.Y <= KENAR, altk = n.Y >= ClientSize.Height - KENAR;
        int kod = HTCLIENT;
        if (sol && ust) kod = HTTOPLEFT;
        else if (sag && ust) kod = HTTOPRIGHT;
        else if (sol && altk) kod = HTBOTTOMLEFT;
        else if (sag && altk) kod = HTBOTTOMRIGHT;
        else if (sol) kod = HTLEFT;
        else if (sag) kod = HTRIGHT;
        else if (ust) kod = HTTOP;
        else if (altk) kod = HTBOTTOM;
        if (kod != HTCLIENT) m.Result = (IntPtr)kod;
    }
}

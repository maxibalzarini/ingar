using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace INGAR_CAN_ANALYZER;

internal static class Program
{
    private const string ResourceName = "INGAR_CAN_ANALYZER.Web.index.html";

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Any(arg => string.Equals(arg, "--self-test", StringComparison.OrdinalIgnoreCase)))
            return RunSelfTest();

        ApplicationConfiguration.Initialize();

        using var mutex = new Mutex(true, @"Local\INGAR_CAN_ANALYZER_FASE_1", out var firstInstance);
        if (!firstInstance)
        {
            MessageBox.Show(
                "INGAR CAN Analyzer ya se encuentra en ejecución.",
                "INGAR CAN Analyzer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return 0;
        }

        try
        {
            var paths = AppPaths.Create();
            ExtractEmbeddedHtml(paths.HtmlFile);
            Application.Run(new MainForm(paths));
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "No fue posible iniciar INGAR CAN Analyzer.\n\n" + ex.Message,
                "Error de inicio",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }

    private static int RunSelfTest()
    {
        var results = new Dictionary<string, object?>();
        try
        {
            var html = ReadEmbeddedHtml();
            results["html_embedded"] = html.Contains("<title>INGAR CAN Analyzer</title>", StringComparison.Ordinal);
            results["indexeddb"] = html.Contains("indexedDB.open", StringComparison.Ordinal);
            results["no_localstorage"] = !html.Contains("localStorage", StringComparison.OrdinalIgnoreCase);
            results["no_local_server"] = !html.Contains("127.0.0.1", StringComparison.OrdinalIgnoreCase)
                                         && !html.Contains("localhost", StringComparison.OrdinalIgnoreCase);
            results["html_sha256"] = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(html)));
            results["webview2_runtime"] = CoreWebView2Environment.GetAvailableBrowserVersionString();

            var paths = AppPaths.Create();
            ExtractEmbeddedHtml(paths.HtmlFile);
            results["html_extracted"] = File.Exists(paths.HtmlFile);
            results["status"] = "OK";

            File.WriteAllText(
                Path.Combine(Environment.CurrentDirectory, "fase1-selftest.json"),
                JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (Exception ex)
        {
            results["status"] = "ERROR";
            results["error"] = ex.ToString();
            File.WriteAllText(
                Path.Combine(Environment.CurrentDirectory, "fase1-selftest.json"),
                JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
            return 1;
        }
    }

    private static string ReadEmbeddedHtml()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName)
                           ?? throw new InvalidOperationException("No se encontró la interfaz HTML5 embebida.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static void ExtractEmbeddedHtml(string destination)
    {
        var html = ReadEmbeddedHtml();
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);

        if (File.Exists(destination) && File.ReadAllText(destination) == html)
            return;

        var temporary = destination + ".tmp";
        File.WriteAllText(temporary, html);
        File.Move(temporary, destination, true);
    }
}

internal sealed record AppPaths(string Root, string WebFolder, string HtmlFile, string WebViewData)
{
    public static AppPaths Create()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "INGAR",
            "CANAnalyzer");
        var webFolder = Path.Combine(root, "web");
        var webViewData = Path.Combine(root, "webview2");
        Directory.CreateDirectory(webFolder);
        Directory.CreateDirectory(webViewData);
        return new AppPaths(root, webFolder, Path.Combine(webFolder, "index.html"), webViewData);
    }
}

internal sealed class MainForm : Form
{
    private readonly AppPaths _paths;
    private readonly WebView2 _webView = new() { Dock = DockStyle.Fill };

    public MainForm(AppPaths paths)
    {
        _paths = paths;
        Text = "INGAR CAN Analyzer";
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(1100, 700);
        BackColor = Color.White;

        try
        {
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        }
        catch
        {
        }

        Controls.Add(_webView);
        Shown += async (_, _) => await InitializeWebViewAsync();
    }

    private async Task InitializeWebViewAsync()
    {
        try
        {
            var environment = await CoreWebView2Environment.CreateAsync(
                browserExecutableFolder: null,
                userDataFolder: _paths.WebViewData);

            await _webView.EnsureCoreWebView2Async(environment);

            var settings = _webView.CoreWebView2.Settings;
            settings.AreDefaultContextMenusEnabled = false;
            settings.AreDevToolsEnabled = false;
            settings.AreBrowserAcceleratorKeysEnabled = false;
            settings.IsStatusBarEnabled = false;
            settings.IsZoomControlEnabled = true;
            settings.IsWebMessageEnabled = false;

            _webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
                "app.ingar.local",
                _paths.WebFolder,
                CoreWebView2HostResourceAccessKind.Allow);

            _webView.CoreWebView2.NavigationStarting += (_, args) =>
            {
                if (!args.Uri.StartsWith("https://app.ingar.local/", StringComparison.OrdinalIgnoreCase))
                    args.Cancel = true;
            };

            _webView.Source = new Uri("https://app.ingar.local/index.html");
        }
        catch (WebView2RuntimeNotFoundException)
        {
            MessageBox.Show(
                "Microsoft Edge WebView2 Runtime no está disponible en este equipo.",
                "Componente requerido",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "No fue posible cargar la interfaz HTML5.\n\n" + ex.Message,
                "INGAR CAN Analyzer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
        }
    }
}

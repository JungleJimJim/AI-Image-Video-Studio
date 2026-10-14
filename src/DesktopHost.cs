using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Program
{
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr window, int command);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--check-runtime")
        {
            try { return String.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString()) ? 1 : 0; }
            catch { return 1; }
        }
        if (args.Length == 2 && args[0] == "--activate")
        {
            try
            {
                IntPtr handle = Process.GetProcessById(Int32.Parse(args[1])).MainWindowHandle;
                if (handle == IntPtr.Zero) return 1;
                ShowWindow(handle, 9);
                SetForegroundWindow(handle);
                return 0;
            }
            catch { return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            if (args.Length != 3) throw new ArgumentException("Start A.I. Image & Video Studio from its application shortcut.");
            Uri url = new Uri(args[0]);
            if (url.Scheme != "http" || url.Host != "127.0.0.1") throw new ArgumentException("Invalid local studio address.");
            Application.Run(new StudioWindow(url, args[1], args[2]));
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "A.I. Image & Video Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

internal sealed class StudioWindow : Form
{
    private readonly Uri studioUrl;
    private readonly string token;
    private readonly string root;
    private readonly WebView2 view;
    private readonly Label loading;
    private readonly Timer health;
    private bool forceClose;
    private bool checking;
    private int failedChecks;
    private bool fullscreen;
    private Rectangle previousBounds;
    private FormWindowState previousWindowState;

    internal StudioWindow(Uri url, string sessionToken, string installation)
    {
        studioUrl = url;
        token = sessionToken;
        root = installation;
        Text = "A.I. Image & Video Studio";
        BackColor = Color.FromArgb(11, 14, 23);
        MinimumSize = new Size(900, 640);
        Size area = Screen.PrimaryScreen.WorkingArea.Size;
        Size = new Size(Math.Min(1320, area.Width - 40), Math.Min(940, area.Height - 40));
        StartPosition = FormStartPosition.CenterScreen;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        AutoScaleMode = AutoScaleMode.Dpi;
        RestoreSize();
        loading = new Label { Text = "Opening your studio…", Dock = DockStyle.Fill,
            ForeColor = Color.FromArgb(190, 179, 255), TextAlign = ContentAlignment.MiddleCenter,
            Font = new Font("Segoe UI", 16) };
        view = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
        Controls.Add(view);
        Controls.Add(loading);
        health = new Timer { Interval = 1200 };
        health.Tick += CheckBackend;
        Shown += InitializeView;
        FormClosing += BeforeClose;
        FormClosed += delegate { health.Stop(); if (fullscreen) ToggleFullscreen(); SaveSize(); view.Dispose(); };
    }

    private async void InitializeView(object sender, EventArgs args)
    {
        try
        {
            CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(root, "desktop-profile"));
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.IsStatusBarEnabled = false;
            view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            view.CoreWebView2.Settings.AreBrowserAcceleratorKeysEnabled = false;
            view.CoreWebView2.NewWindowRequested += delegate(object s, CoreWebView2NewWindowRequestedEventArgs e)
            {
                e.Handled = true;
                if (e.IsUserInitiated) OpenModelWebsite(e.Uri);
            };
            view.CoreWebView2.NavigationStarting += delegate(object s, CoreWebView2NavigationStartingEventArgs e)
            {
                Uri target;
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out target) ||
                    (target.Scheme != "about" && target.GetLeftPart(UriPartial.Authority) != studioUrl.GetLeftPart(UriPartial.Authority)))
                {
                    e.Cancel = true;
                    if (e.IsUserInitiated) OpenModelWebsite(e.Uri);
                }
            };
            view.CoreWebView2.DownloadStarting += SaveVideoCopy;
            view.CoreWebView2.WebMessageReceived += ImportAdapterFiles;
            view.CoreWebView2.Navigate(studioUrl.AbsoluteUri);
            loading.Visible = false;
            view.BringToFront();
            health.Start();
        }
        catch (Exception error)
        {
            MessageBox.Show(this, "The desktop window could not open. Run Setup again to repair Microsoft WebView2.\n\n" + error.Message,
                Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            forceClose = true;
            Close();
        }
    }

    private void SaveVideoCopy(object sender, CoreWebView2DownloadStartingEventArgs args)
    {
        args.Handled = true;
        using (SaveFileDialog dialog = new SaveFileDialog())
        {
            bool image = Path.GetExtension(args.ResultFilePath).Equals(".png", StringComparison.OrdinalIgnoreCase);
            dialog.Title = image ? "Save an image copy" : "Save a video copy";
            dialog.Filter = image ? "PNG image (*.png)|*.png" : "MP4 video (*.mp4)|*.mp4";
            dialog.FileName = Path.GetFileName(args.ResultFilePath);
            dialog.AddExtension = true;
            if (dialog.ShowDialog(this) == DialogResult.OK) args.ResultFilePath = dialog.FileName;
            else args.Cancel = true;
        }
    }

    private Dictionary<string, object> ReadState()
    {
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(new Uri(studioUrl, "/api/state"));
        request.Headers["X-Wan-Token"] = token;
        request.Timeout = 1800;
        request.ReadWriteTimeout = 1800;
        request.Proxy = null;
        using (WebResponse response = request.GetResponse())
        using (StreamReader reader = new StreamReader(response.GetResponseStream()))
            return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
    }

    private async void ImportAdapterFiles(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (!args.Source.StartsWith(studioUrl.GetLeftPart(UriPartial.Authority) + "/")) return;
        string message;
        try { message = args.TryGetWebMessageAsString(); } catch { return; }
        if (message == "toggle-fullscreen") { ToggleFullscreen(); return; }
        if (message == "exit-fullscreen") { if (fullscreen) ToggleFullscreen(); return; }
        if (message == "open-videos")
        {
            try
            {
                Dictionary<string, object> state = await Task.Run(() => ReadState());
                Dictionary<string, object> settings = (Dictionary<string, object>)state["settings"];
                string folder = Path.GetFullPath(Convert.ToString(settings["output"]));
                Directory.CreateDirectory(folder);
                Process.Start(new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"), "\"" + folder + "\"")
                    { UseShellExecute = true, WindowStyle = ProcessWindowStyle.Normal });
            }
            catch (Exception error) { MessageBox.Show(this, error.Message, "Open video folder", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
            return;
        }
        if (message != "import-loras" && !message.StartsWith("import-loras:")) return;
        string loraModel = message == "import-loras" ? "wan13" : message.Substring("import-loras:".Length);
        if (loraModel.Length == 0 || loraModel.Length > 64) return;
        using (OpenFileDialog dialog = new OpenFileDialog())
        {
            dialog.Title = "Install LoRA files";
            dialog.Filter = "Safetensors LoRA (*.safetensors)|*.safetensors";
            dialog.Multiselect = true;
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            string body = new JavaScriptSerializer().Serialize(new Dictionary<string, object> { { "paths", dialog.FileNames }, { "model", loraModel } });
            try
            {
                await Task.Run(() => {
                    using (WebClient client = new WebClient())
                    {
                        client.Proxy = null;
                        client.Headers["X-Wan-Token"] = token;
                        client.Headers["Content-Type"] = "application/json";
                        client.UploadString(new Uri(studioUrl, "/api/loras/import"), body);
                    }
                });
            }
            catch (Exception error) { MessageBox.Show(this, error.Message, "LoRA import", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        }
    }

    private void OpenModelWebsite(string address)
    {
        Uri target;
        if (!Uri.TryCreate(address, UriKind.Absolute, out target) || target.Scheme != "https" ||
            !String.IsNullOrEmpty(target.UserInfo) || !target.IsDefaultPort) return;
        string host = target.DnsSafeHost.ToLowerInvariant();
        if (host != "civitai.com" && host != "www.civitai.com" && host != "huggingface.co" && host != "www.huggingface.co") return;
        try { Process.Start(new ProcessStartInfo(target.AbsoluteUri) { UseShellExecute = true }); }
        catch (Exception error) { MessageBox.Show(this, error.Message, "Open model website", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }

    private async void CheckBackend(object sender, EventArgs args)
    {
        if (checking || forceClose) return;
        checking = true;
        try { await Task.Run(() => ReadState()); failedChecks = 0; }
        catch
        {
            if (++failedChecks >= 15) { forceClose = true; Close(); }
        }
        finally { checking = false; }
    }

    private void BeforeClose(object sender, FormClosingEventArgs args)
    {
        if (forceClose) return;
        try
        {
            Dictionary<string, object> state = ReadState();
            if (state.ContainsKey("busy") && Convert.ToBoolean(state["busy"]) &&
                MessageBox.Show(this, "An operation is running. Cancel it and close the studio?", Text,
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                args.Cancel = true;
        }
        catch { }
    }

    private void RestoreSize()
    {
        try
        {
            Dictionary<string, int> data = new JavaScriptSerializer().Deserialize<Dictionary<string, int>>(
                File.ReadAllText(Path.Combine(root, "window.json")));
            Size area = Screen.PrimaryScreen.WorkingArea.Size;
            Size = new Size(Math.Max(900, Math.Min(data["width"], area.Width - 20)),
                            Math.Max(640, Math.Min(data["height"], area.Height - 20)));
            if (data.ContainsKey("maximized") && data["maximized"] == 1) WindowState = FormWindowState.Maximized;
        }
        catch { }
    }

    private void ToggleFullscreen()
    {
        if (!fullscreen)
        {
            previousWindowState = WindowState;
            previousBounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            WindowState = FormWindowState.Normal;
            FormBorderStyle = FormBorderStyle.None;
            Bounds = Screen.FromControl(this).Bounds;
            fullscreen = true;
        }
        else
        {
            fullscreen = false;
            FormBorderStyle = FormBorderStyle.Sizable;
            Bounds = previousBounds;
            WindowState = previousWindowState;
        }
    }

    private void SaveSize()
    {
        try
        {
            Size size = WindowState == FormWindowState.Normal ? Size : RestoreBounds.Size;
            File.WriteAllText(Path.Combine(root, "window.json"), new JavaScriptSerializer().Serialize(
                new Dictionary<string, int> { { "width", size.Width }, { "height", size.Height },
                    { "maximized", WindowState == FormWindowState.Maximized ? 1 : 0 } }));
        }
        catch { }
    }
}

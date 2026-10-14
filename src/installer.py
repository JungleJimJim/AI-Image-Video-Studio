"""Windows installer with a privileged app-copy helper and per-user studio data."""
import argparse
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from common import (APP_NAME, APP_EXE, CREATE_NO_WINDOW, VERSION, UNINSTALL_KEY, atomic_json,
                    check_install_path, check_data_path, default_install_path, default_data_path,
                    existing_parent, gpu_info, in_program_files, installed_data_path, load_json, resource)
from downloads import Cancelled, provision
from desktop import ensure_desktop_runtime
from packs import catalog as pack_catalog, install as install_packs


def desktop_folder():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            return Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
    except OSError:
        return Path.home() / "Desktop"


def shortcut(path, target, working):
    path.parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "WAN_LINK": str(path), "WAN_TARGET": str(target), "WAN_WORK": str(working)}
    script = "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($env:WAN_LINK); $s.TargetPath=$env:WAN_TARGET; $s.WorkingDirectory=$env:WAN_WORK; $s.Description='A.I. Image and Video Studio - local image and video generation'; $s.Save()"
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=environment,
                   capture_output=True, text=True, check=True, timeout=30, creationflags=CREATE_NO_WINDOW)


def register_uninstall(root, data_root):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
            UNINSTALL_KEY) as key:
        for name, value in {
            "DisplayName": APP_NAME, "DisplayVersion": VERSION, "InstallLocation": str(root),
            "DataLocation": str(data_root),
            "DisplayIcon": str(root / APP_EXE),
            "UninstallString": f'"{root / "UninstallWanVideoStudio.exe"}" --uninstall "{root}"',
        }.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)


def copy_application(root):
    root = check_install_path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Marker prevents setup from installing over or uninstalling an unrelated directory.
    atomic_json(root / "studio-install.json", {"app": APP_NAME, "version": VERSION})
    app = resource(APP_EXE)
    if not app.is_file():
        raise RuntimeError("The bundled application is missing. Use the packaged Setup executable.")
    temporary = root / (APP_EXE + '.new')
    shutil.copy2(app, temporary)
    try:
        os.replace(temporary, root / APP_EXE)
    except PermissionError:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("The studio is running. Click Exit app, then retry setup.") from None
    if getattr(sys, "frozen", False):
        target = root / "UninstallWanVideoStudio.exe"
        if Path(sys.executable).resolve() != target.resolve():
            shutil.copy2(sys.executable, target)
    return root


def elevated_application_action(root, remove=False):
    """Elevate only the binary copy/removal, retaining the calling user's profile."""
    with tempfile.TemporaryDirectory(prefix='studio-setup-') as folder:
        result_path = Path(folder) / 'result.json'
        arguments = ([] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve())])
        arguments += ['--elevated-app-remove' if remove else '--elevated-app-install', str(root), '--result-file', str(result_path)]
        environment = {**os.environ, 'STUDIO_SETUP_EXE': sys.executable,
                       'STUDIO_SETUP_ARGS': subprocess.list2cmdline(arguments)}
        script = ("$ErrorActionPreference='Stop'; try { "
                  "$p=Start-Process -FilePath $env:STUDIO_SETUP_EXE -ArgumentList $env:STUDIO_SETUP_ARGS "
                  "-Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode "
                  "} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            env=environment, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        status = load_json(result_path, {})
        if result.returncode or not status.get('ok'):
            raise RuntimeError(status.get('error') or
                'Windows administrator approval is required for this folder. Retry and approve the Windows prompt, or choose an installation folder you can write to.')


def install_application(root, desktop=True, startmenu=True, data_root=None):
    root = check_install_path(root)
    data_root = check_data_path(data_root if data_root is not None else default_data_path(root))
    if in_program_files(root):
        elevated_application_action(root)
    else:
        copy_application(root)
    data_root.mkdir(parents=True, exist_ok=True)
    atomic_json(data_root / 'studio-data.json', {'app': APP_NAME})
    links = []
    if desktop:
        links.append(desktop_folder() / (APP_NAME + '.lnk'))
    if startmenu:
        links.append(Path(os.environ["APPDATA"]) / 'Microsoft/Windows/Start Menu/Programs' / (APP_NAME + '.lnk'))
    for link in links:
        shortcut(link, root / APP_EXE, root)
    # Preserve links recorded by an earlier installation if a repair adds no new shortcuts.
    import json
    marker = data_root / "shortcuts.json"
    previous = []
    try:
        previous = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for old in previous:
        if Path(old).name in ('Wan Video Studio.lnk', APP_NAME + '.lnk') and Path(old).exists():
            shortcut(Path(old), root / APP_EXE, root)
    atomic_json(marker, sorted(set(previous + [str(link) for link in links])))
    ensure_desktop_runtime()
    register_uninstall(root, data_root)
    return root


class Installer:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title(APP_NAME + ' — Setup')
        self.window.geometry(f"780x{min(960, self.window.winfo_screenheight() - 80)}")
        self.window.minsize(690, 750)
        self.window.configure(bg="#101522")
        self.window.option_add("*Font", ("Segoe UI", 10))
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#101522")
        self.style.configure("TLabel", background="#101522", foreground="#dbe3f3")
        self.style.configure("Muted.TLabel", foreground="#9daac0")
        self.style.configure("TCheckbutton", background="#101522", foreground="#dbe3f3")
        self.style.map("TCheckbutton", background=[("active", "#101522")])
        self.style.configure("TEntry", fieldbackground="#1c2435", foreground="#eef1fa", padding=8)
        self.style.configure("TButton", padding=(13, 8), background="#2b344a", foreground="#edf0fa")
        self.style.configure("Accent.TButton", background="#ae9cff", foreground="#141423", padding=(18, 11))
        self.style.map("Accent.TButton", background=[("active", "#c4b7ff"), ("disabled", "#4b465e")])
        self.style.configure("Help.TButton", padding=0, width=2, background="#27314a")
        self.style.configure("TProgressbar", background="#a99aff", troughcolor="#263047")
        self.path = tk.StringVar(value=str(default_install_path()))
        self.data_path = tk.StringVar(value=str(default_data_path(self.path.get())))
        self.auto_data_path = self.data_path.get()
        self.desktop = tk.BooleanVar(value=True)
        self.menu = tk.BooleanVar(value=True)
        self.full = tk.BooleanVar(value=True)
        self.packs = {key: tk.BooleanVar(value=False) for key in pack_catalog()}
        self.launch = tk.BooleanVar(value=True)
        self.token = tk.StringVar()
        self.status = tk.StringVar(value="Ready to install. Windows will request administrator approval for Program Files.")
        self.disk = tk.StringVar()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.installed = None
        self.widgets = []
        self.build()
        self.path.trace_add("write", self.location_changed)
        self.data_path.trace_add('write', lambda *args: self.refresh_disk())
        self.refresh_disk()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(100, self.poll)

    def help(self, parent, text):
        button = ttk.Button(parent, text="?", style="Help.TButton", width=2,
                            command=lambda: messagebox.showinfo("What does this do?", text, parent=self.window))
        button.pack(side="left", padx=8)

    def label(self, parent, title, helptext):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(12, 6))
        ttk.Label(row, text=title).pack(side="left")
        self.help(row, helptext)

    def checkbox(self, parent, title, variable, helptext):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        widget = ttk.Checkbutton(row, text=title, variable=variable)
        widget.pack(side="left")
        self.widgets.append(widget)
        self.help(row, helptext)

    def build(self):
        actions = ttk.Frame(self.window, padding=(32, 14))
        actions.pack(side='bottom', fill='x')
        body = ttk.Frame(self.window)
        body.pack(fill='both', expand=True)
        canvas = tk.Canvas(body, bg='#101522', highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        frame = ttk.Frame(canvas, padding=(32, 20))
        item = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        def wheel(event):
            if event.widget.winfo_toplevel() == self.window and not isinstance(event.widget, tk.Text):
                canvas.yview_scroll(-int(event.delta / 120), 'units')
        self.window.bind('<MouseWheel>', wheel)
        branding = ttk.Frame(frame)
        branding.pack(fill='x', pady=(0, 6))
        self.logo_image = tk.PhotoImage(file=str(resource('installer-logo.png')))
        tk.Label(branding, image=self.logo_image, bg='white', borderwidth=0).pack(side='left', padx=(0, 22))
        brand_text = ttk.Frame(branding)
        brand_text.pack(side='left', fill='both', expand=True)
        ttk.Label(brand_text, text="Install the studio", font=("Segoe UI", 22, "bold")).pack(anchor='w', pady=(16, 9))
        ttk.Label(brand_text, text="Choose folders, model downloads and shortcuts.", style="Muted.TLabel").pack(anchor='w')
        self.label(frame, "Install location", "Choose where the application is installed. The default is C:\\Program Files\\AI Image & Video Studio. Windows requests administrator approval to copy the app there. You can also select your existing studio folder to upgrade.")
        pathrow = ttk.Frame(frame)
        pathrow.pack(fill="x")
        pathentry = ttk.Entry(pathrow, textvariable=self.path)
        pathentry.pack(side="left", fill="x", expand=True)
        browse = ttk.Button(pathrow, text="Browse…", command=self.browse)
        browse.pack(side="left", padx=(8, 0))
        self.widgets.extend([pathentry, browse])
        self.label(frame, 'Studio data & models', 'The writable folder for downloaded models, the Python/CUDA runtime, settings, logs, and your image/video library. Keep this outside Program Files so daily use needs no administrator rights. Existing studio files can be reused here; nothing is moved or deleted.')
        datarow = ttk.Frame(frame)
        datarow.pack(fill='x')
        dataentry = ttk.Entry(datarow, textvariable=self.data_path)
        dataentry.pack(side='left', fill='x', expand=True)
        databrowse = ttk.Button(datarow, text='Browse…', command=self.browse_data)
        databrowse.pack(side='left', padx=(8, 0))
        self.widgets.extend([dataentry, databrowse])
        ttk.Label(frame, textvariable=self.disk, style="Muted.TLabel").pack(anchor="w", pady=(5, 8))
        self.checkbox(frame, "Download the runtime and model now (recommended)", self.full,
                      "Downloads about 12 GB: ComfyUI with Python, PyTorch and CUDA; experimental epoch 14; the FP8 UMT5 text encoder; and the Wan VAE. All files are SHA-256 verified. If unchecked, install them later using Settings → Install / repair files.")
        packbutton = ttk.Button(frame, text='Choose optional image & video models…', command=self.choose_packs)
        packbutton.pack(anchor='w', pady=(4,6))
        self.widgets.append(packbutton)
        self.checkbox(frame, "Create a desktop shortcut", self.desktop, "Adds an A.I. Image & Video Studio shortcut to your Windows desktop. It opens the studio in its own application window.")
        self.checkbox(frame, "Create a Start menu shortcut", self.menu, "Adds A.I. Image & Video Studio to your own Windows Start menu, without requiring administrator rights.")
        self.checkbox(frame, "Open the studio when setup finishes", self.launch, "Opens the studio in its own desktop window after setup succeeds. Closing that window also stops the video engine and releases GPU memory.")
        self.label(frame, "Hugging Face token (optional)", "Public files normally download without a token. If access is denied, accept any conditions on the model page and use a read-only Hugging Face token. It is used only for the current download and is not saved.")
        tokenentry = ttk.Entry(frame, textvariable=self.token, show="•")
        tokenentry.pack(fill="x")
        self.widgets.append(tokenentry)
        ttk.Label(frame, text="Windows 10/11 x64 · NVIDIA RTX GPU · current NVIDIA driver\nNo separate Python, Git or CUDA Toolkit installation needed.", style="Muted.TLabel", justify="left").pack(anchor="w", pady=(15, 14))
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x")
        ttk.Label(frame, textvariable=self.status, wraplength=680, style="Muted.TLabel").pack(fill="x", pady=(8, 7))
        self.log = tk.Text(frame, height=4, bg="#0c111c", fg="#abbad3", relief="flat", font=("Consolas", 9), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=(3, 12))
        self.cancel_button = ttk.Button(actions, text="Close", command=self.close)
        self.cancel_button.pack(side="left")
        self.install_button = ttk.Button(actions, text="Install studio", style="Accent.TButton", command=self.start)
        self.install_button.pack(side="right")

    def browse(self):
        selected = filedialog.askdirectory(initialdir=str(existing_parent(self.path.get())), title="Choose the parent installation folder", parent=self.window)
        if selected:
            candidate = Path(selected)
            self.path.set(str(candidate if (candidate / "studio-install.json").exists() else candidate / "AI Image & Video Studio"))

    def browse_data(self):
        selected = filedialog.askdirectory(initialdir=str(existing_parent(self.data_path.get())), title='Choose the studio data folder', parent=self.window)
        if selected:
            candidate = Path(selected)
            marked = any((candidate / name).is_file() for name in ('studio-install.json', 'studio-data.json'))
            self.data_path.set(str(candidate if marked else candidate / 'AI Image & Video Studio'))

    def location_changed(self, *args):
        try:
            updated = str(default_data_path(self.path.get()))
            if self.data_path.get() == self.auto_data_path:
                self.data_path.set(updated)
            self.auto_data_path = updated
        except (OSError, ValueError):
            pass
        self.refresh_disk()

    def choose_packs(self):
        dialog = tk.Toplevel(self.window)
        dialog.title('Optional image & video models')
        dialog.configure(bg='#101522')
        dialog.transient(self.window)
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Install the models you want', font=('Segoe UI',16,'bold')).pack(anchor='w')
        for key, pack in pack_catalog().items():
            size = sum(f['size'] for f in pack['files']) / 1024**3
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=(14,0))
            ttk.Checkbutton(row, text=f"{pack['name']} · {size:.1f} GB", variable=self.packs[key]).pack(side='left')
            self.help(row, pack['description'] + ' Downloads are resumable and SHA-256 verified. You can also install this pack later in Settings.')
        def done():
            if any(v.get() for v in self.packs.values()):
                self.full.set(True)
            self.refresh_disk()
            dialog.destroy()
        ttk.Button(frame, text='Done', command=done).pack(anchor='e', pady=(20,0))
        dialog.protocol('WM_DELETE_WINDOW', done)
        dialog.grab_set()

    def refresh_disk(self):
        try:
            free = shutil.disk_usage(existing_parent(self.data_path.get())).free / 1024**3
            extra = sum(sum(f['size'] for f in pack_catalog()[key]['files']) for key,var in self.packs.items() if var.get()) / 1024**3
            self.disk.set(f"{free:.1f} GB free · allow {30+extra:.1f} GB for setup and selected packs")
        except (OSError, ValueError):
            self.disk.set("Choose an accessible local drive.")

    def report(self, message, progress):
        self.events.put(("progress", (message, progress)))

    def start(self):
        try:
            destination = check_install_path(self.path.get())
            data_root = check_data_path(self.data_path.get())
            if self.full.get():
                gpu = gpu_info()
                if not gpu["vram_gb"]:
                    raise ValueError("An NVIDIA GPU with an installed driver was not detected. This release needs NVIDIA CUDA. Install a current NVIDIA driver and retry, or uncheck the download option to install just the interface.")
            selected = (self.desktop.get(), self.menu.get(), self.full.get(), self.token.get().strip(), [k for k,v in self.packs.items() if v.get()])
        except (OSError, ValueError) as error:
            return messagebox.showerror("Check your setup", str(error), parent=self.window)
        self.cancel.clear()
        self.busy = True
        self.install_button.configure(state="disabled")
        self.cancel_button.configure(text="Cancel")
        for widget in self.widgets:
            widget.configure(state="disabled")
        def work():
            try:
                self.report("Installing the studio application…", 0)
                root = install_application(destination, selected[0], selected[1], data_root)
                if selected[2]:
                    provision(data_root, self.report, self.cancel, selected[3])
                    if selected[4]:
                        install_packs(data_root, selected[4], self.report, self.cancel, selected[3])
                if self.cancel.is_set():
                    raise Cancelled("Setup cancelled. Run setup again to resume the downloads.")
                self.events.put(("done", root))
            except Cancelled as error:
                self.events.put(("cancelled", str(error)))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    message, progress = value
                    self.status.set(message)
                    if progress is not None:
                        self.progress["value"] = progress * 100
                    stage = message.split(":")[0]
                    if stage != getattr(self, "last_stage", ""):
                        self.log.configure(state="normal")
                        self.log.insert("end", message + "\n")
                        self.log.see("end")
                        self.log.configure(state="disabled")
                        self.last_stage = stage
                else:
                    self.busy = False
                    self.token.set("")
                    self.cancel_button.configure(text="Close")
                    for widget in self.widgets:
                        widget.configure(state="normal")
                    if kind == "done":
                        self.installed = value
                        self.progress["value"] = 100
                        self.status.set(f"Installed successfully at {value}")
                        self.install_button.configure(text="Open studio", state="normal", command=self.open_studio)
                        if self.launch.get():
                            self.open_studio()
                    else:
                        self.status.set("Setup cancelled. Downloads are kept for retry." if kind == "cancelled" else "Setup failed. Correct the issue below and retry.")
                        self.install_button.configure(state="normal", text="Retry setup")
                        if kind == "error":
                            messagebox.showerror("Setup could not finish", value, parent=self.window)
                        self.log.configure(state="normal")
                        self.log.insert("end", value + "\n")
                        self.log.see("end")
                        self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def open_studio(self):
        if self.installed:
            subprocess.Popen([str(self.installed / APP_EXE)], cwd=self.installed, creationflags=CREATE_NO_WINDOW)

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set("Cancelling safely. Partial downloads will be kept…")
        else:
            self.window.destroy()


def uninstall(root):
    import json
    import winreg
    window = tk.Tk()
    window.withdraw()
    root = Path(root).resolve()
    if not (root / "studio-install.json").is_file() or root == root.parent:
        return messagebox.showerror(APP_NAME, "This is not a recognized installation folder.")
    data_root = check_data_path(installed_data_path(root))
    if not messagebox.askyesno("Uninstall " + APP_NAME,
            "Remove A.I. Image & Video Studio and its downloaded runtime/model files?\n\nYour images, videos, metadata, library and settings will be kept. Close the studio using Exit app before continuing."):
        return
    try:
        if in_program_files(root):
            elevated_application_action(root, remove=True)
        else:
            remove_application(root)
        # Only remove known generated directories inside the marked application root.
        for name in ("runtime", "downloads"):
            target = (data_root / name).resolve()
            if target.parent != data_root:
                raise RuntimeError("Unexpected folder redirection. Remove the runtime manually.")
            if target.exists():
                shutil.rmtree(target)
        links = load_json(data_root / 'shortcuts.json', [])
        allowed = {desktop_folder() / (APP_NAME + ".lnk"), Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / (APP_NAME + ".lnk"), desktop_folder() / "Wan Video Studio.lnk", Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Wan Video Studio.lnk"}
        for link in links:
            if Path(link) in allowed:
                Path(link).unlink(missing_ok=True)
        (data_root / "runtime-ready.json").unlink(missing_ok=True)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        messagebox.showinfo(APP_NAME, "App and model files removed. Your videos and settings are preserved. You may remove the remaining folder manually when you no longer need them.")
    except Exception as error:
        messagebox.showerror(APP_NAME, str(error))
    finally:
        window.destroy()


def remove_application(root):
    root = Path(root).resolve()
    if root == root.parent or not (root / 'studio-install.json').is_file():
        raise ValueError('This is not a recognized installation folder.')
    for name in (APP_EXE, 'WanVideoStudio.exe'):
        (root / name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall")
    parser.add_argument("--headless-install")
    parser.add_argument("--app-only", action="store_true")
    parser.add_argument("--no-shortcuts", action="store_true")
    parser.add_argument('--data-root')
    parser.add_argument('--elevated-app-install')
    parser.add_argument('--elevated-app-remove')
    parser.add_argument('--result-file')
    args = parser.parse_args()
    privileged = args.elevated_app_install or args.elevated_app_remove
    if privileged:
        if not args.result_file:
            raise ValueError('The setup helper requires a result file.')
        try:
            target = Path(privileged).resolve()
            if not in_program_files(target):
                raise ValueError('This helper is only for installations under Program Files.')
            if args.elevated_app_install:
                copy_application(target)
            else:
                remove_application(target)
            atomic_json(args.result_file, {'ok': True})
        except Exception as error:
            atomic_json(args.result_file, {'ok': False, 'error': str(error)})
            raise SystemExit(1)
    elif args.uninstall:
        uninstall(args.uninstall)
    elif args.headless_install:
        data_root = check_data_path(args.data_root or default_data_path(args.headless_install))
        root = install_application(args.headless_install, not args.no_shortcuts, not args.no_shortcuts, data_root)
        if not args.app_only:
            provision(data_root, lambda m, p: print(m, flush=True) if sys.stdout else None, threading.Event())
        atomic_json(data_root / "headless-install-result.json", {"ok": True, "root": str(root), 'data_root': str(data_root)})
    else:
        Installer().window.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if "--headless-install" in sys.argv:
            try:
                root = Path(sys.argv[sys.argv.index("--headless-install") + 1])
                data_root = Path(sys.argv[sys.argv.index('--data-root') + 1]) if '--data-root' in sys.argv else default_data_path(root)
                atomic_json(data_root / "headless-install-result.json", {"ok": False, "error": str(error)})
            except Exception:
                pass
            raise
        messagebox.showerror("Setup failed", str(error))

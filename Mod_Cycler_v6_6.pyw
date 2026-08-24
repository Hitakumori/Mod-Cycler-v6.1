import sys
import os
import re
import random
import threading
import ctypes
import shutil
from ctypes import wintypes
from datetime import datetime
import json
import hashlib
import tempfile
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk, filedialog, simpledialog, colorchooser
import pystray
from PIL import Image, ImageDraw

askcolor = colorchooser.askcolor

# PATH RESOLUTION
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# APPDATA FOR INVISIBLE CONFIG STORAGE
APP_NAME = "Mod Cycler"
APP_ID = "ModCycler"
APP_VERSION = "6.6"
GITHUB_REPO = "Hitakumori/Mod-Cycler"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
GITHUB_LATEST_RELEASE_URL = f"{GITHUB_RELEASES_URL}/latest"
GITHUB_TAGS_URL = f"https://github.com/{GITHUB_REPO}/tags"
SUPPORT_URL = "https://www.patreon.com/cw/Hitakumori"
INSTANCE_HASH = hashlib.sha1(os.path.normcase(BASE).encode("utf-8")).hexdigest()[:16]
INSTANCE_NAME = f"Local\\{APP_ID}_{INSTANCE_HASH}"
APPDATA_DIR = os.path.join(os.getenv('APPDATA') or os.path.expanduser("~"), "NRMM_Mod_Cycler")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")
CYCLER_DIR_NAME = "Mod Cycler"
ACTIVE_INI_NAME = "mod_cycler.ini"
PROFILES_DIR_NAME = "Profiles"
BACKUPS_DIR_NAME = "Backups"
STATE_FILE_NAME = "mod_cycler_state.json"
MODS_DIR_NAME = "Mods"
MANAGED_DIR_NAME = "_MANAGED_"
LEGACY_MANAGED_DIR_NAMES = (
    "V1_3_x_MANAGED-DO_NOT_EDIT_COPY_MOVE_CUT",
    "MANAGED-DO_NOT_EDIT_COPY_MOVE_CUT",
)

NAME_STOP_WORDS = {
    "animated", "animation", "author", "basic", "bikini", "black", "body",
    "bodysuit", "bottom", "by", "clothes", "costume", "default", "dress",
    "enhanced", "final", "fix", "fixed", "hair", "heavy", "high", "hot",
    "insiders", "lewd", "maid", "mega", "megattoggle", "mod", "mods", "new",
    "nude", "nsfw", "old", "outfit", "pack", "queen", "school", "sfw",
    "skin", "skins", "succubus", "swimsuit", "thicc", "toggle", "uniform",
    "version", "white", "with",
}

KNOWN_NAME_FIXES = {
    "kukishinobu": "Kuki Shinobu",
}

MANAGED_SLOT_ID_PATTERN = re.compile(
    r"^\s*global\s+\$managed_slot_id\s*=\s*(\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def find_child_dir(parent, names):
    if not parent or not os.path.isdir(parent):
        return ""
    wanted = {name.casefold() for name in names}
    try:
        for entry in os.scandir(parent):
            if entry.is_dir() and entry.name.casefold() in wanted:
                return os.path.normpath(entry.path)
    except OSError:
        return ""
    return ""


def resolve_mods_folder(path):
    if not path:
        return "", "", ""

    start = os.path.abspath(os.path.normpath(path))
    if not os.path.isdir(start):
        start = os.path.dirname(start)

    managed_name = MANAGED_DIR_NAME.casefold()
    legacy_names = {name.casefold() for name in LEGACY_MANAGED_DIR_NAMES}
    mods_fallback = ""
    legacy_fallback = ("", "")
    current = start
    visited = set()

    while current and current not in visited:
        visited.add(current)
        base_name = os.path.basename(current).casefold()
        parent = os.path.dirname(current)

        if base_name == MODS_DIR_NAME.casefold() and not mods_fallback:
            mods_fallback = current

        if base_name == managed_name and parent:
            return os.path.normpath(parent), os.path.normpath(current), ""

        if base_name in legacy_names and parent and not legacy_fallback[0]:
            legacy_fallback = (parent, current)

        managed_child = find_child_dir(current, (MANAGED_DIR_NAME,))
        if managed_child:
            return os.path.normpath(current), managed_child, ""

        legacy_child = find_child_dir(current, LEGACY_MANAGED_DIR_NAMES)
        if legacy_child and not legacy_fallback[0]:
            legacy_fallback = (current, legacy_child)

        mods_child = find_child_dir(current, (MODS_DIR_NAME,))
        if mods_child:
            if not mods_fallback:
                mods_fallback = mods_child
            managed_under_mods = find_child_dir(mods_child, (MANAGED_DIR_NAME,))
            if managed_under_mods:
                return os.path.normpath(mods_child), managed_under_mods, ""
            legacy_under_mods = find_child_dir(mods_child, LEGACY_MANAGED_DIR_NAMES)
            if legacy_under_mods and not legacy_fallback[0]:
                legacy_fallback = (mods_child, legacy_under_mods)

        if parent == current:
            break
        current = parent

    if legacy_fallback[0]:
        return os.path.normpath(legacy_fallback[0]), "", os.path.normpath(legacy_fallback[1])
    if mods_fallback:
        return os.path.normpath(mods_fallback), "", ""
    return os.path.normpath(start), "", ""


def find_managed_slot_id(mod_path):
    """Read NRMM's authoritative slot ID from a managed mod's generated ini."""
    try:
        for root_dir, dirs, files in os.walk(mod_path):
            dirs.sort(key=str.lower)
            for file_name in sorted(files, key=str.lower):
                if not file_name.lower().endswith(".ini"):
                    continue
                ini_path = os.path.join(root_dir, file_name)
                try:
                    with open(ini_path, "r", encoding="utf-8", errors="ignore") as ini_file:
                        match = MANAGED_SLOT_ID_PATTERN.search(ini_file.read())
                except OSError:
                    continue
                if match:
                    return int(match.group(1))
    except OSError:
        pass
    return None


class UpdateError(Exception):
    pass


def parse_version(value):
    match = re.search(r"(\d+(?:\.\d+){0,3})", str(value or ""))
    if not match:
        return ()
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def compare_versions(left, right):
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    if not left_parts or not right_parts:
        return 0
    return (left_parts > right_parts) - (left_parts < right_parts)


def fetch_github_json(path_or_url):
    url = path_or_url if path_or_url.startswith("http") else f"{GITHUB_API_BASE}{path_or_url}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_ID}/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def pick_release_asset(release_data):
    exe_assets = []
    fallback_assets = []
    for asset in release_data.get("assets", []):
        name = asset.get("name", "")
        download_url = asset.get("browser_download_url")
        if not download_url:
            continue
        lower_name = name.lower()
        if lower_name.endswith(".exe"):
            exe_assets.append((name, download_url))
        elif lower_name.endswith((".zip", ".7z")):
            fallback_assets.append((name, download_url))

    preferred_exes = [
        asset for asset in exe_assets
        if "mod" in asset[0].lower() and "cycler" in asset[0].lower()
    ]
    if preferred_exes:
        return preferred_exes[0][0], preferred_exes[0][1], True
    if exe_assets:
        return exe_assets[0][0], exe_assets[0][1], True
    if fallback_assets:
        return fallback_assets[0][0], fallback_assets[0][1], False
    return "", "", False


def get_latest_update_info():
    try:
        release = fetch_github_json("/releases/latest")
        asset_name, asset_url, installable = pick_release_asset(release)
        version = release.get("tag_name") or release.get("name")
        if not version:
            raise UpdateError("Latest GitHub release does not have a version tag.")
        return {
            "source": "release",
            "version": version,
            "title": release.get("name") or version,
            "url": release.get("html_url") or GITHUB_LATEST_RELEASE_URL,
            "asset_name": asset_name,
            "asset_url": asset_url,
            "installable": installable,
        }
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise UpdateError(f"GitHub release check failed: HTTP {e.code}") from e

    try:
        tags = fetch_github_json("/tags")
    except urllib.error.HTTPError as e:
        raise UpdateError(f"GitHub update check failed: HTTP {e.code}") from e

    if not tags:
        raise UpdateError("No GitHub releases or tags were found.")

    tag = tags[0]
    version = tag.get("name")
    if not version:
        raise UpdateError("Latest GitHub tag does not have a version name.")
    return {
        "source": "tag",
        "version": version,
        "title": version,
        "url": GITHUB_TAGS_URL,
        "asset_name": "",
        "asset_url": "",
        "installable": False,
    }


def download_update_asset(asset_url, asset_name):
    parsed_name = os.path.basename(urllib.parse.urlparse(asset_url).path)
    file_name = asset_name or urllib.parse.unquote(parsed_name) or "Mod_Cycler_update.exe"
    if not file_name.lower().endswith(".exe"):
        raise UpdateError("The latest release asset is not a Windows executable.")

    update_dir = tempfile.mkdtemp(prefix="ModCyclerUpdate_")
    download_path = os.path.join(update_dir, file_name)
    request = urllib.request.Request(
        asset_url,
        headers={"User-Agent": f"{APP_ID}/{APP_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response, open(download_path, "wb") as output:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)

    if os.path.getsize(download_path) < 1024 * 1024:
        raise UpdateError("Downloaded update is too small to be a valid app executable.")
    with open(download_path, "rb") as f:
        if f.read(2) != b"MZ":
            raise UpdateError("Downloaded update is not a Windows executable.")
    return download_path


def write_updater_script(download_path, destination_path, pid):
    script_path = os.path.join(os.path.dirname(download_path), "apply_mod_cycler_update.bat")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("setlocal\n")
        f.write(f"set \"SRC={download_path}\"\n")
        f.write(f"set \"DST={destination_path}\"\n")
        f.write(f"set \"PID={pid}\"\n")
        f.write(":wait\n")
        f.write("tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul\n")
        f.write("if not errorlevel 1 (\n")
        f.write("    timeout /t 1 /nobreak >nul\n")
        f.write("    goto wait\n")
        f.write(")\n")
        f.write("copy /Y \"%SRC%\" \"%DST%\" >nul\n")
        f.write("if errorlevel 1 (\n")
        f.write(f"    start \"\" \"{GITHUB_RELEASES_URL}\"\n")
        f.write("    exit /b 1\n")
        f.write(")\n")
        f.write("start \"\" \"%DST%\"\n")
        f.write("exit /b 0\n")
    return script_path


# --- SINGLE INSTANCE CHECK ---
def focus_existing_window():
    """Best-effort restore/focus for the already-running app window."""
    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    matches = []

    def foreach_window(hwnd, lParam):
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value == APP_NAME:
            matches.append(hwnd)
            return False
        return True

    callback = enum_proc_type(foreach_window)
    user32.EnumWindows(callback, 0)

    if not matches:
        return False

    hwnd = matches[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    return True


def check_single_instance():
    """Prevents more than one instance from running at the same time."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateSemaphoreW.argtypes = [wintypes.LPVOID, wintypes.LONG, wintypes.LONG, wintypes.LPCWSTR]
    kernel32.CreateSemaphoreW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    h_semaphore = kernel32.CreateSemaphoreW(None, 1, 1, INSTANCE_NAME)
    last_error = kernel32.GetLastError()

    if last_error == 183:  # ERROR_ALREADY_EXISTS
        focus_existing_window()
        if h_semaphore:
            kernel32.CloseHandle(h_semaphore)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error", "Another instance of Mod Cycler is already running.")
        root.destroy()
        sys.exit(0)

    return h_semaphore


def create_tray_icon(theme_color):
    image = Image.new('RGB', (64, 64), color=(30, 30, 30))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=theme_color)
    return image


class GeneratorApp:
    def __init__(self, root, semaphore_handle=None):
        self.root = root

        self.semaphore_handle = semaphore_handle or check_single_instance()

        self.root.title(APP_NAME)
        self.root.geometry("380x780+150+150")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")

        self.is_visible = True
        self.group_vars = {}
        self.group_widgets = []
        self.group_paths = {}  # gid -> absolute path, populated by refresh_groups
        self.group_slot_counts = {}
        self.group_favorite_slot_counts = {}
        self.group_favorite_slots = {}
        self.duplicate_group_paths = []
        self.master_var = tk.BooleanVar(value=True)

        # Load Config
        config_data = self.load_config()
        self.target_dir, self.managed_path, self.legacy_managed_path = resolve_mods_folder(config_data["mods_path"])
        self.ui_alpha = config_data.get("ui_alpha", 0.95)
        self.ui_color = config_data.get("ui_color", "#007acc")
        self.nicknames_by_path = config_data.get("nicknames_by_path", {})
        self.legacy_nicknames = config_data.get("legacy_nicknames", {})
        self.nicknames = {}
        self.use_target_nicknames()

        self.root.attributes("-alpha", self.ui_alpha)

        self.key_options = [
            "PGUP", "PGDN", "INSERT", "DELETE", "HOME", "END",
            "UP", "DOWN", "LEFT", "RIGHT", "SPACE", "TAB", "ENTER",
            "ESCAPE", "BACKSPACE", "CAPSLOCK", "SCROLLLOCK", "PAUSE",
            "LBUTTON", "RBUTTON", "MBUTTON", "XBUTTON1", "XBUTTON2",
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
            "NUMPAD0", "NUMPAD1", "NUMPAD2", "NUMPAD3", "NUMPAD4",
            "NUMPAD5", "NUMPAD6", "NUMPAD7", "NUMPAD8", "NUMPAD9",
            "MULTIPLY", "ADD", "SUBTRACT", "DECIMAL", "DIVIDE",
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
            "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "`", "-", "=", "[", "]", "\\", ";", "'", ",", ".", "/"
        ]

        self.keys = {
            "next":      tk.StringVar(value=config_data["keys"]["next"]),
            "prev":      tk.StringVar(value=config_data["keys"]["prev"]),
            "shuffle":   tk.StringVar(value=config_data["keys"]["shuffle"]),
            "auto":      tk.StringVar(value=config_data["keys"]["auto"]),
            "auto_shuf": tk.StringVar(value=config_data["keys"]["auto_shuf"])
        }
        self.favorite_only_var = tk.BooleanVar(value=config_data.get("favorite_only", False))

        # --- CUSTOM THEMES ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Vertical.TScrollbar", gripcount=0, troughcolor="#252526", bordercolor="#252526", arrowcolor="white")
        self.style.configure("TCombobox", fieldbackground="#333337", background="#252526", foreground="white", bordercolor="#1e1e1e", arrowcolor="white")
        self.root.option_add('*TCombobox*Listbox.bg', '#252526')
        self.root.option_add('*TCombobox*Listbox.fg', 'white')

        # --- DRAGGABLE TITLE BAR ---
        self.title_bar = tk.Frame(root, bg="#2d2d30", relief="raised", bd=0)
        self.title_bar.pack(fill="x")
        self.title_bar.bind("<ButtonPress-1>", self.start_move)
        self.title_bar.bind("<B1-Motion>", self.do_move)

        self.title_lbl = tk.Label(self.title_bar, text=f" Mod Cycler v{APP_VERSION}", bg="#2d2d30", fg=self.ui_color, font=("Segoe UI", 10, "bold"))
        self.title_lbl.pack(side="left", pady=6, padx=10)

        self.close_btn = tk.Button(self.title_bar, text="✕", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10), command=self.hide_window, activeforeground="white")
        self.close_btn.pack(side="right", padx=(0, 10))

        self.min_btn = tk.Button(self.title_bar, text="—", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10, "bold"), command=self.hide_window, activeforeground="white")
        self.min_btn.pack(side="right", padx=5)

        # --- FOOTER SECTION ---
        footer_frame = tk.Frame(root, bg="#1e1e1e")
        footer_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 10))

        # FIX 2: Store info_frame as self.info_frame so update_ui_theme can reach it directly.
        self.info_frame = tk.Frame(footer_frame, bg="#1e1e1e")
        self.info_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(self.info_frame, text="Custom Keybinds:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))

        self.create_keybind_row(self.info_frame, 1, "Next Mod:", self.keys["next"], "Prev Mod:", self.keys["prev"])
        self.create_keybind_row(self.info_frame, 2, "Shuffle:", self.keys["shuffle"], "", None)
        self.create_keybind_row(self.info_frame, 3, "Auto-Cycle:", self.keys["auto"], "Auto-Shuffle:", self.keys["auto_shuf"])

        self.profile_frame = tk.Frame(footer_frame, bg="#1e1e1e")
        self.profile_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(self.profile_frame, text="Profile:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(self.profile_frame, textvariable=self.profile_var, state="readonly", width=18)
        self.profile_combo.bind("<<ComboboxSelected>>", self.load_selected_profile)
        self.profile_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=2, padx=(0, 8))

        self.save_profile_btn = tk.Button(self.profile_frame, text="SAVE", bg=self.ui_color, fg="white", bd=0,
                                          font=("Segoe UI", 8, "bold"), command=self.save_current_profile,
                                          activeforeground="white")
        self.save_profile_btn.grid(row=1, column=3, sticky="ew", pady=2, ipady=3)

        settings_frame = tk.Frame(footer_frame, bg="#1e1e1e")
        settings_frame.grid(row=2, column=0, sticky="nsew")

        tk.Label(settings_frame, text="UI Customization:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))

        self.theme_btn = tk.Button(settings_frame, text="Choose UI Color", bg=self.ui_color, fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.pick_ui_color)
        self.theme_btn.grid(row=1, column=0, columnspan=2, pady=2, ipady=3, padx=(0, 10))

        tk.Label(settings_frame, text="UI Transparency:", bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=2)

        self.alpha_scale = tk.Scale(settings_frame, from_=0.1, to=1.0, resolution=0.01, orient="horizontal",
                                    bg="#333337", activebackground=self.ui_color, troughcolor="#1e1e1e",
                                    highlightthickness=0, bd=0, length=130, showvalue=0,
                                    command=self.update_alpha_from_scale)
        self.alpha_scale.set(self.ui_alpha)
        self.alpha_scale.grid(row=1, column=3, sticky="w", padx=2)

        self.update_btn = tk.Button(settings_frame, text="CHECK UPDATES", bg=self.ui_color, fg="white", bd=0,
                                    font=("Segoe UI", 8, "bold"), command=self.check_for_updates,
                                    activeforeground="white")
        self.update_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0), ipady=3, padx=(0, 10))

        self.support_btn = tk.Button(settings_frame, text="SUPPORT ME", bg=self.ui_color, fg="white", bd=0,
                                     font=("Segoe UI", 8, "bold"), command=self.open_support_page,
                                     activeforeground="white")
        self.support_btn.grid(row=2, column=2, columnspan=2, sticky="ew", pady=(8, 0), ipady=3, padx=(10, 0))

        self.gen_btn = tk.Button(root, text="GENERATE .INI", bg=self.ui_color, fg="white", bd=0, font=("Segoe UI", 10, "bold"), command=self.generate_ini, activeforeground="white")
        self.gen_btn.pack(side="bottom", fill="x", padx=20, pady=10, ipady=8)

        # --- HEADER SECTION ---
        top_frame = tk.Frame(root, bg="#1e1e1e")
        top_frame.pack(side="top", fill="x", padx=20, pady=(15, 5))

        folder_lbl_frame = tk.Frame(top_frame, bg="#1e1e1e")
        folder_lbl_frame.pack(fill="x", pady=(0, 15))
        tk.Label(folder_lbl_frame, text="Mods Folder:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(side="top", anchor="w")

        path_display_frame = tk.Frame(folder_lbl_frame, bg="#1e1e1e")
        path_display_frame.pack(fill="x", pady=(2, 0))

        self.path_lbl = tk.Label(path_display_frame, text=self.truncate_path(self.target_dir), bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8))
        self.path_lbl.pack(side="left", anchor="w")

        self.browse_btn = tk.Button(path_display_frame, text="BROWSE", bg=self.ui_color, fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.browse_folder, activeforeground="white", padx=10)
        self.browse_btn.pack(side="right")

        tk.Label(top_frame, text="Mod Change Interval (Seconds):", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))

        self.timer_var = tk.StringVar(value="120")
        entry = tk.Entry(top_frame, textvariable=self.timer_var, width=10, bg="#333337", fg="white", bd=1, insertbackground="white", font=("Segoe UI", 11), justify="center")
        entry.pack(anchor="w")

        self.favorites_only_cb = tk.Checkbutton(
            top_frame,
            text="Favorites only (NRMM fav files)",
            variable=self.favorite_only_var,
            command=self.save_config,
            bg="#1e1e1e",
            selectcolor="#1e1e1e",
            activebackground="#1e1e1e",
            fg="#ffffff",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            bd=0,
        )
        self.favorites_only_cb.pack(anchor="w", pady=(5, 0))

        self.groups_lbl = tk.Label(root, text="Detected Groups (Right-Click to Rename):", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold"))
        self.groups_lbl.pack(side="top", anchor="w", padx=20, pady=(10, 0))

        self.master_cb = tk.Checkbutton(root, text="Select All", variable=self.master_var, command=self.toggle_all,
                                        bg="#1e1e1e", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                                        font=("Segoe UI", 9, "bold"), bd=0)
        self.master_cb.pack(side="top", anchor="w", padx=20, pady=(0, 5))

        list_container = tk.Frame(root, bg="#252526", bd=1, relief="flat")
        list_container.pack(fill="both", expand=True, padx=20, pady=(0, 5))

        self.canvas = tk.Canvas(list_container, bg="#252526", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview, style="Vertical.TScrollbar")
        self.scroll_frame = tk.Frame(self.canvas, bg="#252526")

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.refresh_groups()
        self.refresh_profile_list()

        self.grip = tk.Canvas(root, width=15, height=15, bg="#1e1e1e", highlightthickness=0, cursor="bottom_right_corner")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        self.start_x = self.start_y = self.start_w = self.start_h = 0
        self.x = self.y = 0
        self.current_columns = 1

        self.grip.bind("<ButtonPress-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.do_resize)

        self.update_ui_theme()

        self.setup_tray()
        self.hotkey_thread = threading.Thread(target=self.listen_for_hotkey, daemon=True)
        self.hotkey_thread.start()

    # -----------------------------------------------------------------------

    def update_alpha_from_scale(self, value):
        self.ui_alpha = float(value)
        self.root.attributes("-alpha", self.ui_alpha)
        self.save_config()

    def pick_ui_color(self):
        color_tuple = askcolor(color=self.ui_color, title="Select UI Theme Color")
        if color_tuple[1]:
            self.ui_color = color_tuple[1]
            self.update_ui_theme()
            self.save_config()
            self.tray_icon.stop()
            self.setup_tray()

    def set_update_button(self, text="CHECK UPDATES", enabled=True):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.update_btn.config(text=text, state=state)

    def open_support_page(self):
        webbrowser.open(SUPPORT_URL)

    def check_for_updates(self):
        self.set_update_button("CHECKING...", False)
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

    def _check_for_updates_worker(self):
        try:
            update_info = get_latest_update_info()
            self.root.after(0, lambda: self.handle_update_result(update_info))
        except Exception as e:
            self.root.after(0, lambda err=e: self.handle_update_error(err))

    def handle_update_error(self, error):
        self.set_update_button()
        messagebox.showerror("Update Check Failed", str(error))

    def handle_update_result(self, update_info):
        self.set_update_button()
        latest_version = update_info["version"]
        if compare_versions(latest_version, APP_VERSION) <= 0:
            messagebox.showinfo("No Update Available", f"Mod Cycler {APP_VERSION} is current.\n\nLatest GitHub version: {latest_version}")
            return

        message = f"Mod Cycler {latest_version} is available.\nCurrent version: {APP_VERSION}\n\n"
        if update_info.get("asset_url") and update_info.get("installable") and getattr(sys, "frozen", False):
            choice = messagebox.askyesnocancel(
                "Update Available",
                message + "Yes: download and install now\nNo: open GitHub release page\nCancel: do nothing"
            )
            if choice is True:
                self.download_and_install_update(update_info)
            elif choice is False:
                webbrowser.open(update_info["url"])
            return

        if messagebox.askyesno("Update Available", message + "Open the GitHub release page?"):
            webbrowser.open(update_info["url"])

    def download_and_install_update(self, update_info):
        self.set_update_button("DOWNLOADING...", False)
        threading.Thread(target=self._download_update_worker, args=(update_info,), daemon=True).start()

    def _download_update_worker(self, update_info):
        try:
            download_path = download_update_asset(update_info["asset_url"], update_info.get("asset_name", ""))
            self.root.after(0, lambda: self.install_downloaded_update(download_path))
        except Exception as e:
            self.root.after(0, lambda err=e: self.handle_update_error(err))

    def install_downloaded_update(self, download_path):
        self.set_update_button()
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("Update Downloaded", f"Downloaded update to:\n{download_path}\n\nOpen the release page to install it manually.")
            webbrowser.open(GITHUB_RELEASES_URL)
            return

        if not messagebox.askyesno("Install Update", "Update downloaded. Mod Cycler will close, replace the EXE, and restart.\n\nInstall now?"):
            return

        try:
            updater_script = write_updater_script(download_path, sys.executable, os.getpid())
            subprocess.Popen(
                ["cmd.exe", "/c", updater_script],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            messagebox.showerror("Install Failed", f"Could not start updater:\n{e}")
            return

        self.quit_app()

    def update_ui_theme(self):
        self.style.map("Vertical.TScrollbar", background=[('active', self.ui_color)])
        self.root.option_add('*TCombobox*Listbox.selectBackground', self.ui_color)

        try:
            self.theme_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        except AttributeError:
            pass

        self.gen_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.browse_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.update_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.support_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.save_profile_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.title_lbl.config(fg=self.ui_color)
        self.close_btn.config(activebackground="#ff1123")
        self.min_btn.config(activebackground=self.ui_color)
        self.alpha_scale.config(activebackground=self.ui_color)
        self.master_cb.config(activeforeground="#ffffff", fg=self.ui_color)
        self.groups_lbl.config(fg=self.ui_color)

        # FIX 2: Recolor keybind labels directly via stored self.info_frame reference.
        for widget in self.info_frame.winfo_children():
            if isinstance(widget, tk.Label):
                text = widget.cget("text")
                # Color the key-name labels (e.g. "Next Mod:", "Shuffle:") with theme color
                if text and "Custom Keybinds" not in text and text.endswith(":"):
                    widget.config(fg=self.ui_color)

        self.grip.delete("all")
        self.grip.create_line(5, 15, 15, 5, fill=self.ui_color, width=2)
        self.grip.create_line(10, 15, 15, 10, fill=self.ui_color, width=2)

        self.regrid_checkboxes()

    def rename_group_ui(self, event, gid, current_name):
        new_name = simpledialog.askstring("Rename Group", f"Enter nickname for Group {gid}:", initialvalue=current_name)
        if new_name is not None:
            new_name = new_name.strip()
            if new_name:
                self.nicknames[str(gid)] = new_name
            else:
                self.nicknames.pop(str(gid), None)
            self.save_config()
            self.refresh_groups()

    def get_path_key(self, path=None):
        normalized = os.path.normcase(os.path.normpath(path or self.target_dir))
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]

    def use_target_nicknames(self):
        self.nickname_key = self.get_path_key()
        self.nicknames = self.nicknames_by_path.setdefault(self.nickname_key, {})

    def create_keybind_row(self, parent, row, label1, var1, label2, var2):
        tk.Label(parent, text=label1, bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=row, column=0, sticky="e", padx=(0, 5), pady=2)
        ttk.Combobox(parent, textvariable=var1, values=self.key_options, width=10).grid(row=row, column=1, sticky="w", pady=2)
        if label2 and var2:
            tk.Label(parent, text=label2, bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=row, column=2, sticky="e", padx=(15, 5), pady=2)
            ttk.Combobox(parent, textvariable=var2, values=self.key_options, width=10).grid(row=row, column=3, sticky="w", pady=2)

    def on_canvas_resize(self, event):
        columns = max(1, event.width // 240)
        if getattr(self, 'current_columns', 0) != columns:
            self.current_columns = columns
            self.regrid_checkboxes()
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def regrid_checkboxes(self):
        cols = max(1, getattr(self, 'current_columns', 1))
        for index, widget in enumerate(self.group_widgets):
            widget.grid(row=index // cols, column=index % cols, sticky="w", padx=5, pady=2)
            if isinstance(widget, tk.Checkbutton):
                widget.config(activeforeground="#ffffff", activebackground="#252526", fg="#ffffff")
            else:
                widget.config(fg=widget.cget("fg"))

    def clear_generation_warning_labels(self):
        kept_widgets = []
        for widget in self.group_widgets:
            if getattr(widget, "is_generation_warning", False):
                widget.destroy()
            else:
                kept_widgets.append(widget)
        if len(kept_widgets) != len(self.group_widgets):
            self.group_widgets = kept_widgets
            self.regrid_checkboxes()

    def load_config(self):
        config = {
            "mods_path": BASE,
            "ui_alpha": 0.95,
            "ui_color": "#007acc",
            "keys": {
                "next": "PGUP",
                "prev": "PGDN",
                "shuffle": "INSERT",
                "auto": "CAPSLOCK",
                "auto_shuf": "END"
            },
            "nicknames_by_path": {},
            "legacy_nicknames": {},
            "favorite_only": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    config["mods_path"] = data.get("mods_path", BASE)
                    config["ui_alpha"] = data.get("ui_alpha", 0.95)
                    config["ui_color"] = data.get("ui_color", "#007acc")
                    config["favorite_only"] = bool(data.get("favorite_only", False))
                    nicknames_by_path = data.get("nicknames_by_path", {})
                    if isinstance(nicknames_by_path, dict):
                        config["nicknames_by_path"] = {
                            str(path_key): {str(gid): str(name) for gid, name in names.items() if str(name)}
                            for path_key, names in nicknames_by_path.items()
                            if isinstance(names, dict)
                        }
                    legacy_nicknames = data.get("legacy_nicknames", data.get("nicknames", {}))
                    if isinstance(legacy_nicknames, dict):
                        config["legacy_nicknames"] = {str(gid): str(name) for gid, name in legacy_nicknames.items() if str(name)}
                    if "keys" in data:
                        config["keys"].update(data["keys"])
            except Exception as e:
                print(f"[Mod Cycler] Failed to load config: {e}")
        return config

    def save_config(self):
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            self.nicknames_by_path[self.nickname_key] = self.nicknames
            with open(CONFIG_FILE, 'w', encoding="utf-8") as f:
                json.dump({
                    "mods_path": self.target_dir,
                    "ui_alpha": self.ui_alpha,
                    "ui_color": self.ui_color,
                    "favorite_only": self.favorite_only_var.get(),
                    "keys": {k: v.get() for k, v in self.keys.items()},
                    "nicknames_by_path": self.nicknames_by_path,
                    "legacy_nicknames": self.legacy_nicknames,
                    "nicknames": {}
                }, f, indent=2)
        except Exception as e:
            print(f"[Mod Cycler] Failed to save config: {e}")

    def truncate_path(self, path, max_len=40):
        return "..." + path[-(max_len - 3):] if len(path) > max_len else path

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.target_dir)
        if folder:
            self.target_dir, self.managed_path, self.legacy_managed_path = resolve_mods_folder(folder)
            self.use_target_nicknames()
            self.path_lbl.config(text=self.truncate_path(self.target_dir))
            self.save_config()
            self.refresh_groups()
            self.refresh_profile_list()

    def start_resize(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root
        self.start_w, self.start_h = self.root.winfo_width(), self.root.winfo_height()

    def do_resize(self, event):
        new_w = max(320, self.start_w + (event.x_root - self.start_x))
        new_h = max(580, self.start_h + (event.y_root - self.start_y))
        self.root.geometry(f"{new_w}x{new_h}")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def toggle_all(self):
        for var in self.group_vars.values():
            var.set(self.master_var.get())

    def sync_master_var(self):
        if self.group_vars:
            self.master_var.set(all(var.get() for var in self.group_vars.values()))

    def get_cycler_dir(self):
        return os.path.join(self.target_dir, CYCLER_DIR_NAME)

    def get_profiles_dir(self):
        return os.path.join(self.get_cycler_dir(), PROFILES_DIR_NAME)

    def get_backups_dir(self):
        return os.path.join(self.get_cycler_dir(), BACKUPS_DIR_NAME)

    def get_active_ini_path(self):
        return os.path.join(self.get_cycler_dir(), ACTIVE_INI_NAME)

    def get_state_path(self):
        return os.path.join(self.get_cycler_dir(), STATE_FILE_NAME)

    def get_legacy_root_ini_path(self):
        return os.path.join(self.target_dir, ACTIVE_INI_NAME)

    def refresh_target_dir(self):
        resolved_dir, managed_path, legacy_managed_path = resolve_mods_folder(self.target_dir)
        if resolved_dir and resolved_dir != self.target_dir:
            self.target_dir = resolved_dir
            self.use_target_nicknames()
            if hasattr(self, "path_lbl"):
                self.path_lbl.config(text=self.truncate_path(self.target_dir))
        self.managed_path = managed_path
        self.legacy_managed_path = legacy_managed_path
        return managed_path

    def load_generation_state(self):
        state_path = self.get_state_path()
        if not os.path.exists(state_path):
            return {}
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state if isinstance(state, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            print(f"[Mod Cycler] Failed to load generation state: {e}")
            return {}

    def save_generation_state(self, final_groups):
        state_path = self.get_state_path()
        tmp_path = state_path + ".tmp"
        groups = {
            str(group["id"]): {
                "slots": int(group["slots"]),
                "all_slots": int(group.get("all_slots", group["slots"])),
                "favorite_slots": list(group.get("favorite_slots", [])),
                "name": self.nicknames.get(str(group["id"]), ""),
            }
            for group in final_groups
        }
        detected_groups = {
            str(gid): {
                "slots": int(slots),
                "favorite_slots": list(self.group_favorite_slots.get(gid, [])),
            }
            for gid, slots in self.group_slot_counts.items()
            if slots >= 2
        }
        state = {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "active_ini": ACTIVE_INI_NAME,
            "favorite_only": self.favorite_only_var.get(),
            "groups": groups,
            "detected_groups": detected_groups,
        }
        os.makedirs(self.get_cycler_dir(), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, state_path)

    def get_generation_warnings(self):
        state = self.load_generation_state()
        generated_groups = state.get("groups", {})
        if not isinstance(generated_groups, dict) or not generated_groups:
            return []
        detected_at_generate = state.get("detected_groups", {})
        if not isinstance(detected_at_generate, dict):
            detected_at_generate = {}
        favorite_only = bool(state.get("favorite_only", False))

        warnings = []
        generated_ids = {str(gid) for gid in generated_groups}
        previously_detected_ids = {str(gid) for gid in detected_at_generate}
        for gid in sorted(self.group_slot_counts):
            current_slots = self.group_slot_counts.get(gid, 0)
            current_effective_slots = self.group_favorite_slot_counts.get(gid, 0) if favorite_only else current_slots
            minimum_slots = 1 if favorite_only else 2
            if current_effective_slots < minimum_slots:
                continue

            group_key = str(gid)
            generated = generated_groups.get(group_key)
            if generated is None:
                if group_key not in previously_detected_ids:
                    warnings.append(
                        f"New Group {gid} has {current_effective_slots} {'favorite(s)' if favorite_only else 'mods'} but is not in the generated cycler."
                    )
                continue

            try:
                generated_slots = int(generated.get("slots", 0))
            except (TypeError, ValueError):
                generated_slots = 0

            if generated_slots != current_effective_slots:
                warnings.append(
                    f"Group {gid} has {current_effective_slots} {'favorite(s)' if favorite_only else 'mods'}; generated cycler has {generated_slots}."
                )
            elif favorite_only:
                generated_favorites = generated.get("favorite_slots", [])
                if not isinstance(generated_favorites, list):
                    generated_favorites = []
                if generated_favorites != self.group_favorite_slots.get(gid, []):
                    warnings.append(f"Group {gid} has different favorited mods than the generated cycler.")

        missing_generated = []
        current_ids = {
            str(gid)
            for gid, count in self.group_slot_counts.items()
            if (self.group_favorite_slot_counts.get(gid, 0) >= 1 if favorite_only else count >= 2)
        }
        sort_key = lambda value: (0, int(value)) if value.isdigit() else (1, value)
        for group_key in sorted(generated_ids - current_ids, key=sort_key):
            missing_generated.append(group_key)
        if missing_generated:
            warnings.append(
                f"{len(missing_generated)} generated group(s) are no longer valid in _MANAGED_."
            )

        return warnings

    def safe_profile_name(self, name):
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "")).strip(" .")
        return safe_name[:80] or "Profile"

    def get_profile_path(self, name):
        return os.path.join(self.get_profiles_dir(), f"{self.safe_profile_name(name)}.json")

    def list_profile_names(self):
        profiles_dir = self.get_profiles_dir()
        if not os.path.isdir(profiles_dir):
            return []
        names = []
        for filename in os.listdir(profiles_dir):
            if filename.lower().endswith(".json"):
                names.append(os.path.splitext(filename)[0])
        names.sort(key=str.lower)
        return names

    def refresh_profile_list(self, select_name=None):
        if not hasattr(self, "profile_combo"):
            return
        names = self.list_profile_names()
        self.profile_combo["values"] = names
        current = select_name or self.profile_var.get()
        if current in names:
            self.profile_var.set(current)
        elif names:
            self.profile_var.set(names[0])
        else:
            self.profile_var.set("")

    def collect_profile_data(self, name):
        selected_groups = sorted(gid for gid, var in self.group_vars.items() if var.get())
        return {
            "version": 1,
            "name": name,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "interval": self.timer_var.get().strip(),
            "keys": {key: value.get().strip() for key, value in self.keys.items()},
            "selected_groups": selected_groups,
            "favorite_only": self.favorite_only_var.get(),
        }

    def save_current_profile(self):
        initial_name = self.profile_var.get() or "Default"
        name = simpledialog.askstring("Save Profile", "Profile name:", initialvalue=initial_name, parent=self.root)
        if not name:
            return
        profile_name = self.safe_profile_name(name)
        profile_path = self.get_profile_path(profile_name)
        tmp_path = profile_path + ".tmp"
        try:
            os.makedirs(self.get_profiles_dir(), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.collect_profile_data(profile_name), f, indent=2)
            os.replace(tmp_path, profile_path)
        except OSError as e:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            messagebox.showerror("Profile Save Failed", f"Could not save profile:\n{e}")
            return

        self.refresh_profile_list(profile_name)
        messagebox.showinfo("Profile Saved", f"Saved profile:\n{profile_name}")

    def load_selected_profile(self, event=None):
        profile_name = self.profile_var.get()
        if not profile_name:
            return

        profile_path = self.get_profile_path(profile_name)
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("Profile Load Failed", f"Could not load profile:\n{e}")
            return

        interval = str(profile.get("interval", "")).strip()
        if interval:
            self.timer_var.set(interval)

        keys = profile.get("keys", {})
        if isinstance(keys, dict):
            for key_name, value in keys.items():
                if key_name in self.keys and str(value).strip():
                    self.keys[key_name].set(str(value).strip())
        self.favorite_only_var.set(bool(profile.get("favorite_only", False)))

        raw_selected_groups = profile.get("selected_groups", [])
        if not isinstance(raw_selected_groups, (list, tuple, set)):
            raw_selected_groups = []
        selected_groups = {int(gid) for gid in raw_selected_groups if str(gid).isdigit()}
        detected_groups = set(self.group_vars)
        for gid, var in self.group_vars.items():
            var.set(gid in selected_groups)
        self.sync_master_var()
        self.save_config()

        missing_groups = sorted(selected_groups - detected_groups)
        if missing_groups:
            messagebox.showwarning(
                "Profile Partially Loaded",
                f"Loaded profile, but {len(missing_groups)} group(s) are not detected in the current Mods folder."
            )

    def next_backup_path(self, label):
        os.makedirs(self.get_backups_dir(), exist_ok=True)
        safe_label = re.sub(r"[^0-9A-Za-z_-]+", "_", label).strip("_") or "backup"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp}_{safe_label}.bak"
        backup_path = os.path.join(self.get_backups_dir(), base_name)
        suffix = 1
        while os.path.exists(backup_path):
            backup_path = os.path.join(self.get_backups_dir(), f"{timestamp}_{safe_label}_{suffix}.bak")
            suffix += 1
        return backup_path

    def backup_file(self, path, label, move=False):
        if not os.path.exists(path):
            return ""
        backup_path = self.next_backup_path(label)
        if move:
            os.replace(path, backup_path)
        else:
            shutil.copy2(path, backup_path)
        return backup_path

    def migrate_legacy_root_ini(self):
        legacy_path = self.get_legacy_root_ini_path()
        active_path = self.get_active_ini_path()
        if os.path.normcase(os.path.abspath(legacy_path)) == os.path.normcase(os.path.abspath(active_path)):
            return ""
        return self.backup_file(legacy_path, "root_mod_cycler", move=True)

    def format_display_name(self, token):
        fixed = KNOWN_NAME_FIXES.get(token.lower())
        if fixed:
            return fixed
        parts = re.findall(r"[a-zA-Z]+|\d+", token)
        if parts:
            return " ".join(part.capitalize() if part.isalpha() else part for part in parts)
        return token.strip().title()

    def name_tokens(self, raw_name):
        text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", " ", raw_name)
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        text = re.sub(r"[^0-9A-Za-z]+", " ", text)
        tokens = []
        for token in text.split():
            token = token.lower()
            token = re.sub(r"^\d+|\d+$", "", token)
            for suffix in ("mods", "mod", "skins", "skin"):
                if token.endswith(suffix) and len(token) > len(suffix) + 2:
                    token = token[:-len(suffix)]
                    break
            if len(token) < 3 or token in NAME_STOP_WORDS:
                continue
            tokens.append(token)
        return tokens

    def clean_name(self, raw_name):
        tokens = self.name_tokens(raw_name)
        if tokens:
            return self.format_display_name(tokens[0])
        text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", " ", raw_name)
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        text = re.sub(r"[_+\-.]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text.title() if text else "Unknown"

    def infer_group_name(self, slot_names):
        token_sets = []
        ordered_token_lists = []
        first_seen = {}
        for index, raw_name in enumerate(slot_names):
            tokens = self.name_tokens(raw_name)
            if not tokens:
                continue
            ordered_token_lists.append((index, tokens))
            unique_tokens = set(tokens)
            token_sets.append(unique_tokens)
            for token in unique_tokens:
                first_seen.setdefault(token, index)

        if not token_sets:
            return self.clean_name(slot_names[0]) if slot_names else "Unknown"

        scores = {}
        for tokens in token_sets:
            for token in tokens:
                scores[token] = scores.get(token, 0) + 1

        prefix_scores = {}
        prefix_first_seen = {}
        for index, tokens in enumerate(token_sets):
            prefixes = set()
            for token in tokens:
                for length in range(4, min(len(token), 16) + 1):
                    prefixes.add(token[:length])
            for prefix in prefixes:
                prefix_scores[prefix] = prefix_scores.get(prefix, 0) + 1
                prefix_first_seen.setdefault(prefix, index)

        candidates = []
        for token, score in scores.items():
            if score >= 2:
                candidates.append((score, len(token), -first_seen[token], token))
        for prefix, score in prefix_scores.items():
            if score >= 2:
                candidates.append((score, len(prefix), -prefix_first_seen[prefix], prefix))

        if candidates:
            _, _, _, token = max(candidates)
            return self.format_display_name(token)

        if ordered_token_lists:
            _, tokens = max(ordered_token_lists, key=lambda item: (len(item[1]), -item[0]))
            return " ".join(self.format_display_name(token) for token in tokens[:2])
        return "Unknown"

    def refresh_groups(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.group_widgets.clear()
        self.group_paths.clear()
        self.group_slot_counts.clear()
        self.group_favorite_slot_counts.clear()
        self.group_favorite_slots.clear()
        self.duplicate_group_paths.clear()
        # FIX 3: Also clear group_vars so stale entries from a previous folder don't linger.
        self.group_vars.clear()

        managed_path = self.refresh_target_dir()
        if not managed_path:
            if self.legacy_managed_path:
                legacy_name = os.path.basename(self.legacy_managed_path)
                text = (
                    f"Old NRMM folder found: {legacy_name}\n"
                    "Open NRMM and run Update Mod Data to migrate it to _MANAGED_."
                )
            else:
                text = "No _MANAGED_ folder found. Select Mods, the XXMI root, or an NRMM managed folder."
            lbl = tk.Label(self.scroll_frame, text=text, bg="#252526", fg="#ff4444", font=("Segoe UI", 9),
                           wraplength=300, justify="left")
            lbl.grid(row=0, column=0, pady=10, padx=10)
            self.group_widgets.append(lbl)
            return

        group_folders = []
        # Deep scan: find group folders anywhere inside _MANAGED_
        for root_dir, dirs, _ in os.walk(managed_path):
            dirs.sort(key=str.lower)
            found_group_dirs = []
            for d in list(dirs):
                m = re.fullmatch(r"group[_]?(\d+)", d, re.IGNORECASE)
                if m:
                    found_group_dirs.append(d)
                    gid = int(m.group(1))
                    gpath = os.path.join(root_dir, d)
                    if gid in self.group_paths:
                        self.duplicate_group_paths.append(gpath)
                        continue
                    try:
                        subs = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                        subs.sort()
                        self.group_slot_counts[gid] = len(subs)
                        favorite_slots = []
                        for mod_name in subs:
                            mod_path = os.path.join(gpath, mod_name)
                            if not os.path.isfile(os.path.join(mod_path, "fav")):
                                continue
                            slot_id = find_managed_slot_id(mod_path)
                            if slot_id is not None:
                                favorite_slots.append(slot_id)
                        self.group_favorite_slots[gid] = favorite_slots
                        self.group_favorite_slot_counts[gid] = len(favorite_slots)
                        if len(subs) >= 2:
                            raw_name = self.infer_group_name(subs)
                            display_name = self.nicknames.get(str(gid), raw_name)
                            group_folders.append((gid, display_name))
                            # FIX 4: Cache the actual found path so generate_ini uses it correctly.
                            self.group_paths[gid] = gpath
                    except Exception as e:
                        print(f"[Mod Cycler] Could not read group folder '{d}': {e}")
                        continue
            for d in found_group_dirs:
                if d in dirs:
                    dirs.remove(d)

        generation_warnings = self.get_generation_warnings()
        if generation_warnings:
            preview = "\n".join(generation_warnings[:4])
            if len(generation_warnings) > 4:
                preview += f"\n+{len(generation_warnings) - 4} more cycler mismatch(es)."
            lbl = tk.Label(self.scroll_frame, text=f"Cycler out of date:\n{preview}",
                           bg="#252526", fg="#ffcc66", font=("Segoe UI", 9),
                           wraplength=320, justify="left")
            lbl.is_generation_warning = True
            self.group_widgets.append(lbl)

        group_folders.sort()
        for gid, name in group_folders:
            var = tk.BooleanVar(value=True)
            self.group_vars[gid] = var
            cb = tk.Checkbutton(self.scroll_frame, text=f"Group {gid} ({name})", variable=var,
                                bg="#252526", selectcolor="#1e1e1e", activebackground="#252526",
                                font=("Segoe UI", 9), wraplength=220, justify="left")
            cb.bind("<Button-3>", lambda e, g=gid, n=name: self.rename_group_ui(e, g, n))
            self.group_widgets.append(cb)

        if not group_folders:
            lbl = tk.Label(self.scroll_frame, text="No valid group folders found.", bg="#252526", fg="#ff4444", font=("Segoe UI", 9))
            self.group_widgets.append(lbl)

        if self.duplicate_group_paths:
            skipped = len(self.duplicate_group_paths)
            lbl = tk.Label(self.scroll_frame, text=f"{skipped} duplicate group ID(s) skipped.", bg="#252526", fg="#ffcc66", font=("Segoe UI", 9))
            self.group_widgets.append(lbl)

        self.regrid_checkboxes()

    def start_move(self, event):
        self.x, self.y = event.x, event.y

    def do_move(self, event):
        self.root.geometry(f"+{self.root.winfo_x() + (event.x - self.x)}+{self.root.winfo_y() + (event.y - self.y)}")

    def setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem('Show (Alt+S)', self.show_from_tray),
            pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon(APP_NAME, create_tray_icon(self.ui_color), APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.is_visible = False
        self.root.withdraw()

    def show_window(self):
        self.is_visible = True
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()

    def show_from_tray(self, icon, item):
        self.root.after(0, self.show_window)

    def toggle_from_hotkey(self):
        self.root.after(0, self.hide_window if self.is_visible else self.show_window)

    def quit_app(self, icon=None, item=None):
        ctypes.windll.user32.UnregisterHotKey(None, 1)
        if getattr(self, "tray_icon", None):
            self.tray_icon.stop()
        if self.semaphore_handle:
            ctypes.windll.kernel32.CloseHandle(self.semaphore_handle)
            self.semaphore_handle = None
        self.root.after(0, self.root.destroy)

    def listen_for_hotkey(self):
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, 0x0001, 0x53):
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312 and msg.wParam == 1:
                self.root.after(0, self.toggle_from_hotkey)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def generate_ini(self):
        self.save_config()
        try:
            timer_seconds = int(self.timer_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number.")
            return

        if timer_seconds < 1:
            messagebox.showerror("Error", "Interval must be at least 1 second.")
            return

        key_values = {}
        for label, key_name in (
            ("Next Mod", "next"),
            ("Prev Mod", "prev"),
            ("Shuffle", "shuffle"),
            ("Auto-Cycle", "auto"),
            ("Auto-Shuffle", "auto_shuf"),
        ):
            value = self.keys[key_name].get().strip()
            if not value or "\n" in value or "\r" in value:
                messagebox.showerror("Error", f"{label} keybind is invalid.")
                return
            key_values[key_name] = value

        final_groups = []
        groups_without_favorites = []
        unresolved_favorites = []
        for gid, var in self.group_vars.items():
            if not var.get():
                continue
            # FIX 4: Use the cached path from refresh_groups instead of reconstructing it.
            gpath = self.group_paths.get(gid)
            if gpath and os.path.exists(gpath):
                try:
                    mods = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                except OSError as e:
                    print(f"[Mod Cycler] Could not read group folder '{gpath}': {e}")
                    continue
                self.group_slot_counts[gid] = len(mods)
                mods.sort()
                favorite_slots = []
                for mod_name in mods:
                    mod_path = os.path.join(gpath, mod_name)
                    if not os.path.isfile(os.path.join(mod_path, "fav")):
                        continue
                    slot_id = find_managed_slot_id(mod_path)
                    if slot_id is None:
                        unresolved_favorites.append((gid, mod_name))
                        continue
                    favorite_slots.append(slot_id)
                self.group_favorite_slot_counts[gid] = len(favorite_slots)
                self.group_favorite_slots[gid] = favorite_slots
                active_slots = favorite_slots if self.favorite_only_var.get() else list(range(1, len(mods) + 1))
                if active_slots and (self.favorite_only_var.get() or len(mods) >= 2):
                    deck = active_slots[:]
                    random.shuffle(deck)
                    final_groups.append({
                        'id': gid,
                        'slots': len(active_slots),
                        'all_slots': len(mods),
                        'favorite_slots': favorite_slots,
                        'active_slots': active_slots,
                        'deck': deck,
                    })
                elif self.favorite_only_var.get() and len(mods) >= 2:
                    groups_without_favorites.append(gid)

        if not final_groups:
            message = "No selected groups contain favorited mods." if self.favorite_only_var.get() else "No valid groups selected."
            messagebox.showwarning("Warning", message)
            return

        ini_path = self.get_active_ini_path()
        tmp_path = ini_path + ".tmp"
        legacy_backup = ""
        previous_backup = ""
        state_warning = ""
        try:
            os.makedirs(self.get_cycler_dir(), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("; v6.6\nnamespace = mod_cycler_indie\\cycler\n\n[Constants]\n")
                f.write("global persist $auto_enable = 0\nglobal persist $shuffle_auto_enable = 0\nglobal persist $last_cycle = 0\n\n")
                for g in final_groups:
                    if self.favorite_only_var.get():
                        f.write(
                            f"global persist $g{g['id']}_cycle_pos = 0\n"
                            f"global persist $g{g['id']}_shuffle_pos = 0\n"
                            f"global persist $g{g['id']}_slot = {g['active_slots'][0]}\n"
                        )
                    else:
                        f.write(f"global persist $g{g['id']}_pos = 0\nglobal persist $g{g['id']}_slot = {g['deck'][0]}\n")

                f.write(f"\n[KeyNext]\nkey = {key_values['next']}\nrun = CommandListNext\n")
                f.write(f"[KeyPrev]\nkey = {key_values['prev']}\nrun = CommandListPrev\n")
                f.write(f"[KeyRandom]\nkey = {key_values['shuffle']}\nrun = CommandListShuffle\n")
                f.write(f"[KeyToggleAuto]\nkey = {key_values['auto']}\nrun = CommandListToggleAuto\n")
                f.write(f"[KeyToggleShuffleAuto]\nkey = {key_values['auto_shuf']}\nrun = CommandListToggleShuffleAuto\n")

                f.write("\n[CommandListToggleAuto]\n$auto_enable = 1 - $auto_enable\n$shuffle_auto_enable = 0\n")
                f.write("if $auto_enable == 1\n    $last_cycle = time\n    run = CommandListNext\nendif\n")

                f.write("\n[CommandListToggleShuffleAuto]\n$shuffle_auto_enable = 1 - $shuffle_auto_enable\n$auto_enable = 0\n")
                f.write("if $shuffle_auto_enable == 1\n    $last_cycle = time\n    run = CommandListShuffle\nendif\n")

                f.write("\n[CommandListNext]\n")
                for g in final_groups:
                    if self.favorite_only_var.get():
                        f.write(f"$g{g['id']}_cycle_pos = ($g{g['id']}_cycle_pos + 1) % {g['slots']}\n")
                        for pos, mod_id in enumerate(g['active_slots']):
                            f.write(f"if $g{g['id']}_cycle_pos == {pos}\n    $g{g['id']}_slot = {mod_id}\nendif\n")
                    else:
                        f.write(f"$g{g['id']}_slot = $g{g['id']}_slot + 1\n")
                        f.write(f"if $g{g['id']}_slot > {g['slots']}\n    $g{g['id']}_slot = 1\nendif\n")
                    f.write(f"$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")

                f.write("\n[CommandListPrev]\n")
                for g in final_groups:
                    if self.favorite_only_var.get():
                        f.write(f"$g{g['id']}_cycle_pos = $g{g['id']}_cycle_pos - 1\n")
                        f.write(f"if $g{g['id']}_cycle_pos < 0\n    $g{g['id']}_cycle_pos = {g['slots'] - 1}\nendif\n")
                        for pos, mod_id in enumerate(g['active_slots']):
                            f.write(f"if $g{g['id']}_cycle_pos == {pos}\n    $g{g['id']}_slot = {mod_id}\nendif\n")
                    else:
                        f.write(f"$g{g['id']}_slot = $g{g['id']}_slot - 1\n")
                        f.write(f"if $g{g['id']}_slot < 1\n    $g{g['id']}_slot = {g['slots']}\nendif\n")
                    f.write(f"$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")

                f.write("\n[CommandListShuffle]\n")
                for g in final_groups:
                    position_name = "shuffle_pos" if self.favorite_only_var.get() else "pos"
                    f.write(f"$g{g['id']}_{position_name} = ($g{g['id']}_{position_name} + 1) % {g['slots']}\n")
                    for pos, mod_id in enumerate(g['deck']):
                        f.write(f"if $g{g['id']}_{position_name} == {pos}\n    $g{g['id']}_slot = {mod_id}\nendif\n")
                    f.write(f"$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n\n")

                f.write(f"[Present]\nif $auto_enable == 1 || $shuffle_auto_enable == 1\n")
                f.write(f"    if time - $last_cycle >= {timer_seconds}\n")
                f.write(f"        $last_cycle = time\n")
                f.write(f"        if $auto_enable == 1\n")
                f.write(f"            run = CommandListNext\n")
                f.write(f"        else\n")
                f.write(f"            run = CommandListShuffle\n")
                f.write(f"        endif\n")
                f.write(f"    endif\n")
                f.write(f"endif\n")
            previous_backup = self.backup_file(ini_path, "previous_mod_cycler", move=False)
            legacy_backup = self.migrate_legacy_root_ini()
            os.replace(tmp_path, ini_path)
            try:
                self.save_generation_state(final_groups)
                self.clear_generation_warning_labels()
            except OSError as e:
                state_warning = f"\n\nCould not save cycler state snapshot:\n{e}"
        except OSError as e:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            messagebox.showerror("Error", f"Failed to write mod_cycler.ini:\n{e}")
            return

        self.root.configure(bg="#2b6b3e")
        self.title_bar.configure(bg="#2b6b3e")
        self.root.after(300, self.reset_generate_ini_colors)
        details = f"Generated:\n{ini_path}\n\nPress F10 in-game."
        if previous_backup:
            details += "\n\nPrevious active ini was backed up."
        if legacy_backup:
            details += "\n\nOld root mod_cycler.ini was moved to backup."
        if state_warning:
            details += state_warning
        if self.favorite_only_var.get():
            details += "\n\nFavorites-only cycling is enabled."
            if groups_without_favorites:
                details += f"\nSkipped {len(groups_without_favorites)} selected group(s) with no favorited mods."
            if unresolved_favorites:
                details += f"\nSkipped {len(unresolved_favorites)} favorited mod(s) with no NRMM managed slot ID."
        messagebox.showinfo("Success", details)

    def reset_generate_ini_colors(self):
        self.root.configure(bg="#1e1e1e")
        self.title_bar.configure(bg="#2d2d30")
        self.update_ui_theme()


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    semaphore_handle = check_single_instance()
    root = tk.Tk()
    app = GeneratorApp(root, semaphore_handle)
    root.protocol("WM_DELETE_WINDOW", app.quit_app)
    root.mainloop()

import sys
import os
import re
import random
import threading
import ctypes
from ctypes import wintypes
import json
import tkinter as tk
from tkinter import messagebox, ttk, filedialog, simpledialog
import pystray
from PIL import Image, ImageDraw

# Requires: pip install tkcolorpicker
try:
    from tkcolorpicker import askcolor
except ImportError:
    askcolor = None 

# PATH RESOLUTION
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# APPDATA FOR INVISIBLE CONFIG STORAGE
APPDATA_DIR = os.path.join(os.getenv('APPDATA'), "NRMM_Mod_Cycler")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

# --- PRO FEATURE: SINGLE INSTANCE CHECK ---
def check_single_instance():
    """Detects if another instance of this .exe is already running."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    semaphore_name = f"ModCycler_{BASE.replace('\\', '_')}"
    h_semaphore = kernel32.CreateSemaphoreW(None, 1, 1, semaphore_name)
    last_error = kernel32.GetLastError()
    
    if last_error == 183: # ERROR_ALREADY_EXISTS
        other_hwnds = []
        def foreach_window(hwnd, lParam):
            class_name = ctypes.create_unicode_buffer(1024)
            user32.GetClassNameW(hwnd, class_name, 1024)
            if class_name.value == semaphore_name:
                other_hwnds.append(hwnd)
            return True
        user32.EnumWindows(ctypes.WNDENUMPROC(foreach_window), 0)
        if other_hwnds:
            user32.ShowWindow(other_hwnds[0], 5) # SW_SHOW
            user32.SetForegroundWindow(other_hwnds[0])
            
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
    def __init__(self, root):
        self.root = root
        
        # Window identification for single instance
        self.semaphore_handle = check_single_instance()
        self.semaphore_name = ctypes.windll.kernel32.CreateSemaphoreW(None, 1, 1, f"ModCycler_{BASE.replace('\\', '_')}")
        self.root.option_add('*tk_menu', self.semaphore_name) 

        self.root.title("Mod Cycler")
        self.root.geometry("380x780+150+150")
        self.root.overrideredirect(True)      
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")     

        self.is_visible = True
        self.group_vars = {} 
        self.group_widgets = [] 
        self.master_var = tk.BooleanVar(value=True)
        
        # Load Config
        config_data = self.load_config()
        self.target_dir = config_data["mods_path"]
        self.ui_alpha = config_data.get("ui_alpha", 0.95)
        self.ui_color = config_data.get("ui_color", "#007acc") 
        self.nicknames = config_data.get("nicknames", {})
        
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
            "next": tk.StringVar(value=config_data["keys"]["next"]),
            "prev": tk.StringVar(value=config_data["keys"]["prev"]),
            "shuffle": tk.StringVar(value=config_data["keys"]["shuffle"]),
            "auto": tk.StringVar(value=config_data["keys"]["auto"]),
            "auto_shuf": tk.StringVar(value=config_data["keys"]["auto_shuf"])
        }

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
        
        self.title_lbl = tk.Label(self.title_bar, text=" Mod Cycler v6.4", bg="#2d2d30", fg=self.ui_color, font=("Segoe UI", 10, "bold"))
        self.title_lbl.pack(side="left", pady=6, padx=10)
        
        self.close_btn = tk.Button(self.title_bar, text="✕", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10), command=self.hide_window, activeforeground="white")
        self.close_btn.pack(side="right", padx=(0, 10))

        self.min_btn = tk.Button(self.title_bar, text="—", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10, "bold"), command=self.hide_window, activeforeground="white")
        self.min_btn.pack(side="right", padx=5)

        # --- FOOTER SECTION ---
        footer_frame = tk.Frame(root, bg="#1e1e1e")
        footer_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 10))
        
        info_frame = tk.Frame(footer_frame, bg="#1e1e1e")
        info_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(info_frame, text="Custom Keybinds:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,5))
        
        self.create_keybind_row(info_frame, 1, "Next Mod:", self.keys["next"], "Prev Mod:", self.keys["prev"])
        self.create_keybind_row(info_frame, 2, "Shuffle:", self.keys["shuffle"], "", None)
        self.create_keybind_row(info_frame, 3, "Auto-Cycle:", self.keys["auto"], "Auto-Shuffle:", self.keys["auto_shuf"])
        
        settings_frame = tk.Frame(footer_frame, bg="#1e1e1e")
        settings_frame.grid(row=1, column=0, sticky="nsew")
        
        tk.Label(settings_frame, text="UI Customization:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,5))
        
        if askcolor:
            self.theme_btn = tk.Button(settings_frame, text="Choose UI Color", bg=self.ui_color, fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.pick_ui_color)
            self.theme_btn.grid(row=1, column=0, columnspan=2, pady=2, ipady=3, padx=(0,10))
        else:
            tk.Label(settings_frame, text="Install 'tkcolorpicker' for color wheel.", bg="#1e1e1e", fg="#ff4444", font=("Segoe UI", 8, "italic")).grid(row=1, column=0, columnspan=2, pady=2, padx=(0,10))
        
        tk.Label(settings_frame, text="UI Transparency:", bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=2)
        
        # FIXED: Highly visible standard tk.Scale instead of invisible ttk.Scale
        self.alpha_scale = tk.Scale(settings_frame, from_=0.1, to=1.0, resolution=0.01, orient="horizontal", 
                                    bg="#333337", activebackground=self.ui_color, troughcolor="#1e1e1e", 
                                    highlightthickness=0, bd=0, length=130, showvalue=0, 
                                    command=self.update_alpha_from_scale)
        self.alpha_scale.set(self.ui_alpha)
        self.alpha_scale.grid(row=1, column=3, sticky="w", padx=2)

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

        self.groups_lbl = tk.Label(root, text="Detected Groups (Right-Click to Rename):", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold"))
        self.groups_lbl.pack(side="top", anchor="w", padx=20, pady=(10, 0))

        self.master_cb = tk.Checkbutton(root, text="Select All", variable=self.master_var, command=self.toggle_all, bg="#1e1e1e", selectcolor="#1e1e1e", activebackground="#1e1e1e", font=("Segoe UI", 9, "bold"), bd=0)
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

    def update_ui_theme(self):
        self.style.map("Vertical.TScrollbar", background=[('active', self.ui_color)])
        self.root.option_add('*TCombobox*Listbox.selectBackground', self.ui_color)

        try:
            self.theme_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        except AttributeError: pass
        
        self.gen_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.browse_btn.config(bg=self.ui_color, activebackground=self.ui_color)
        self.title_lbl.config(fg=self.ui_color)
        self.close_btn.config(activebackground="#ff1123") 
        self.min_btn.config(activebackground=self.ui_color)
        
        # Link transparency slider's active color to theme
        try:
            self.alpha_scale.config(activebackground=self.ui_color)
        except AttributeError: pass
        
        info_frame_widgets = self.gen_btn.master.winfo_children()
        actual_binds_frame = footer_frame = None
        for w in info_frame_widgets:
             if w.winfo_class() == "Frame":
                 footer_frame = w
                 break
        if footer_frame:
            for w in footer_frame.winfo_children():
                 if w.winfo_class() == "Frame":
                     actual_binds_frame = w
                     break
        if actual_binds_frame:
            for w in actual_binds_frame.winfo_children():
                 if w.winfo_class() == "Label" and "Custom Keybinds" not in w.cget("text") and ":" not in w.cget("text"):
                     w.config(fg=self.ui_color)
                         
        self.master_cb.config(activeforeground="#ffffff", fg=self.ui_color)
        self.groups_lbl.config(fg=self.ui_color)
        
        self.grip.delete("all")
        self.grip.create_line(5, 15, 15, 5, fill=self.ui_color, width=2)
        self.grip.create_line(10, 15, 15, 10, fill=self.ui_color, width=2)
        
        self.regrid_checkboxes() 

    def rename_group_ui(self, event, gid, current_name):
        new_name = simpledialog.askstring("Rename Group", f"Enter nickname for Group {gid}:", initialvalue=current_name)
        if new_name is not None:
            self.nicknames[str(gid)] = new_name
            self.save_config()
            self.refresh_groups()

    def create_keybind_row(self, parent, row, label1, var1, label2, var2):
        tk.Label(parent, text=label1, bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=row, column=0, sticky="e", padx=(0,5), pady=2)
        cb1 = ttk.Combobox(parent, textvariable=var1, values=self.key_options, width=10)
        cb1.grid(row=row, column=1, sticky="w", pady=2)
        
        if label2 and var2:
            tk.Label(parent, text=label2, bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8)).grid(row=row, column=2, sticky="e", padx=(15,5), pady=2)
            cb2 = ttk.Combobox(parent, textvariable=var2, values=self.key_options, width=10)
            cb2.grid(row=row, column=3, sticky="w", pady=2)

    def on_canvas_resize(self, event):
        columns = max(1, event.width // 240)
        if getattr(self, 'current_columns', 0) != columns:
            self.current_columns = columns
            self.regrid_checkboxes()
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def regrid_checkboxes(self):
        cols = max(1, getattr(self, 'current_columns', 1))
        for index, cb in enumerate(self.group_widgets):
            cb.grid(row=index//cols, column=index%cols, sticky="w", padx=5, pady=2)
            cb.config(activeforeground="#ffffff", activebackground="#252526", fg="#ffffff")

    def load_config(self):
        config = {
            "mods_path": BASE, 
            "ui_alpha": 0.95,
            "ui_color": "#007acc", 
            "keys": {"next": "PGUP", "prev": "PGDN", "shuffle": "INSERT", "auto": "CAPSLOCK", "auto_shuf": "END"},
            "nicknames": {}
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    config["mods_path"] = data.get("mods_path", BASE)
                    config["ui_alpha"] = data.get("ui_alpha", 0.95)
                    config["ui_color"] = data.get("ui_color", "#007acc")
                    config["nicknames"] = data.get("nicknames", {})
                    if "keys" in data:
                        config["keys"].update(data["keys"])
            except: pass
        return config

    def save_config(self):
        if not os.path.exists(APPDATA_DIR):
            os.makedirs(APPDATA_DIR)
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "mods_path": self.target_dir,
                "ui_alpha": self.ui_alpha,
                "ui_color": self.ui_color,
                "keys": {k: v.get() for k, v in self.keys.items()},
                "nicknames": self.nicknames
            }, f)

    def truncate_path(self, path, max_len=40):
        return "..." + path[-(max_len-3):] if len(path) > max_len else path

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.target_dir)
        if folder:
            self.target_dir = os.path.normpath(folder)
            self.path_lbl.config(text=self.truncate_path(self.target_dir))
            self.save_config()
            self.refresh_groups()

    def start_resize(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root
        self.start_w, self.start_h = self.root.winfo_width(), self.root.winfo_height()

    def do_resize(self, event):
        new_w = max(320, self.start_w + (event.x_root - self.start_x))
        new_h = max(580, self.start_h + (event.y_root - self.start_y))
        self.root.geometry(f"{new_w}x{new_h}")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def toggle_all(self):
        for var in self.group_vars.values(): var.set(self.master_var.get())

    def clean_name(self, raw_name):
        return re.split(r'[-(\[]', raw_name)[0].replace('_', ' ').strip().title()

    def refresh_groups(self):
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        self.group_widgets.clear()

        managed_path = os.path.join(self.target_dir, "_MANAGED_")
        if not os.path.exists(managed_path):
            lbl = tk.Label(self.scroll_frame, text="No _MANAGED_ folder found.", bg="#252526", fg="#ff4444", font=("Segoe UI", 9))
            lbl.grid(row=0, column=0, pady=10, padx=10)
            self.group_widgets.append(lbl)
            return

        group_folders = []
        for g in os.listdir(managed_path):
            m = re.match(r"group[_]?(\d+)", g)
            if m:
                gid = int(m.group(1))
                try:
                    gpath = os.path.join(managed_path, g)
                    subs = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                    if len(subs) >= 2:
                        raw_name = self.clean_name(subs[0])
                        display_name = self.nicknames.get(str(gid), raw_name)
                        group_folders.append((gid, display_name))
                except: pass
        
        group_folders.sort()
        for gid, name in group_folders:
            var = tk.BooleanVar(value=True)
            self.group_vars[gid] = var
            cb = tk.Checkbutton(self.scroll_frame, text=f"Group {gid} ({name})", variable=var, bg="#252526", selectcolor="#1e1e1e", activebackground="#252526", font=("Segoe UI", 9), wraplength=220, justify="left")
            cb.bind("<Button-3>", lambda e, g=gid, n=name: self.rename_group_ui(e, g, n))
            self.group_widgets.append(cb)
            
        self.regrid_checkboxes()

    def start_move(self, event):
        self.x, self.y = event.x, event.y

    def do_move(self, event):
        self.root.geometry(f"+{self.root.winfo_x() + (event.x - self.x)}+{self.root.winfo_y() + (event.y - self.y)}")

    def setup_tray(self):
        menu = pystray.Menu(pystray.MenuItem('Show (Alt+S)', self.show_from_tray), pystray.MenuItem('Quit', self.quit_app))
        self.tray_icon = pystray.Icon("Mod Cycler", create_tray_icon(self.ui_color), "Mod Cycler", menu)
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

    def quit_app(self, icon, item):
        ctypes.windll.user32.UnregisterHotKey(None, 1)
        self.tray_icon.stop()
        ctypes.windll.kernel32.CloseHandle(self.semaphore_handle)
        self.root.after(0, self.root.destroy)

    def listen_for_hotkey(self):
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, 0x0001, 0x53): return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312 and msg.wParam == 1:
                self.root.after(0, self.toggle_from_hotkey)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def generate_ini(self):
        self.save_config()
        try: timer_seconds = int(self.timer_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number.")
            return

        managed_path = os.path.join(self.target_dir, "_MANAGED_")
        if not os.path.exists(managed_path):
            messagebox.showerror("Error", "Could not find _MANAGED_ folder.")
            return

        final_groups = []
        for gid, var in self.group_vars.items():
            if not var.get(): continue
            gpath = os.path.join(managed_path, f"group{gid}")
            if not os.path.exists(gpath): gpath = os.path.join(managed_path, f"group_{gid}")
            if os.path.exists(gpath):
                mods = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                if len(mods) >= 2:
                    mods.sort(); deck = list(range(1, len(mods) + 1)); random.shuffle(deck)
                    final_groups.append({'id': gid, 'slots': len(mods), 'deck': deck})

        if not final_groups:
            messagebox.showwarning("Warning", "No valid groups selected.")
            return

        ini_path = os.path.join(self.target_dir, "mod_cycler.ini")
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write("; v6.4 CUSTOM THEME EDITION\nnamespace = mod_cycler_indie\\cycler\n\n[Constants]\n")
            f.write("global persist $auto_enable = 0\nglobal persist $shuffle_auto_enable = 0\nglobal persist $last_cycle = 0\n\n")
            for g in final_groups: f.write(f"global persist $g{g['id']}_pos = 0\nglobal persist $g{g['id']}_slot = {g['deck'][0]}\n")
            
            f.write(f"\n[KeyNext]\nkey = {self.keys['next'].get()}\nrun = CommandListNext\n")
            f.write(f"[KeyPrev]\nkey = {self.keys['prev'].get()}\nrun = CommandListPrev\n")
            f.write(f"[KeyRandom]\nkey = {self.keys['shuffle'].get()}\nrun = CommandListShuffle\n")
            f.write(f"[KeyToggleAuto]\nkey = {self.keys['auto'].get()}\nrun = CommandListToggleAuto\n")
            f.write(f"[KeyToggleShuffleAuto]\nkey = {self.keys['auto_shuf'].get()}\nrun = CommandListToggleShuffleAuto\n")
            
            f.write("\n[CommandListToggleAuto]\n$auto_enable = 1 - $auto_enable\n$shuffle_auto_enable = 0\nif $auto_enable == 1\n    $last_cycle = time\n    run = CommandListNext\nendif\n")
            f.write("\n[CommandListToggleShuffleAuto]\n$shuffle_auto_enable = 1 - $shuffle_auto_enable\n$auto_enable = 0\nif $shuffle_auto_enable == 1\n    $last_cycle = time\n    run = CommandListShuffle\nendif\n")
            
            f.write("\n[CommandListNext]\n")
            for g in final_groups: f.write(f"$g{g['id']}_slot = $g{g['id']}_slot + 1\nif $g{g['id']}_slot > {g['slots']}\n    $g{g['id']}_slot = 1\nendif\n$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")
            
            f.write("\n[CommandListPrev]\n")
            for g in final_groups: f.write(f"$g{g['id']}_slot = $g{g['id']}_slot - 1\nif $g{g['id']}_slot < 1\n    $g{g['id']}_slot = {g['slots']}\nendif\n$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")
            
            f.write("\n[CommandListShuffle]\n")
            for g in final_groups:
                f.write(f"$g{g['id']}_pos = ($g{g['id']}_pos + 1) % {g['slots']}\n")
                for pos, mod_id in enumerate(g['deck']): f.write(f"if $g{g['id']}_pos == {pos}\n    $g{g['id']}_slot = {mod_id}\nendif\n")
                f.write(f"$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n\n")

            f.write(f"[Present]\nif $auto_enable == 1 || $shuffle_auto_enable == 1\n    if time - $last_cycle >= {timer_seconds}\n        $last_cycle = time\n        if $auto_enable == 1\n            run = CommandListNext\n        else\n            run = CommandListShuffle\n        endif\n    endif\nendif\n")
            
        orig_bg, success_bg = "#1e1e1e", "#2b6b3e"
        self.root.configure(bg=success_bg)
        self.title_bar.configure(bg=success_bg)
        for child in self.root.winfo_children():
            try:
                if child not in [self.gen_btn, self.title_bar] and child.winfo_class() != "Canvas": child.configure(bg=success_bg)
            except: pass
        self.root.after(300, self.reset_generate_ini_colors)
        self.root.attributes("-topmost", True)
        messagebox.showinfo("Success", "mod_cycler.ini generated!\n\nPress F10 in-game.")

    def reset_generate_ini_colors(self):
        orig_bg = "#1e1e1e"
        self.root.configure(bg=orig_bg)
        self.title_bar.configure(bg="#2d2d30")
        for child in self.root.winfo_children():
            try:
                if child not in [self.gen_btn, self.title_bar] and child.winfo_class() != "Canvas": child.configure(bg=orig_bg)
            except: pass
        self.update_ui_theme()

if __name__ == "__main__":
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except: pass

    root = tk.Tk()
    app = GeneratorApp(root)
    root.mainloop()
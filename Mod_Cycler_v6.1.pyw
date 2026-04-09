import sys
import os
import re
import random
import threading
import ctypes
from ctypes import wintypes
import json
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import pystray
from PIL import Image, ImageDraw

# PATH RESOLUTION (Fallback)
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# APPDATA FOR INVISIBLE CONFIG STORAGE
APPDATA_DIR = os.path.join(os.getenv('APPDATA'), "NRMM_Mod_Cycler")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(30, 30, 30))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 122, 204)) 
    return image

class GeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mod Cycler")
        
        self.root.geometry("360x650+150+150")
        self.root.overrideredirect(True)      
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)  
        self.root.configure(bg="#1e1e1e")     

        self.is_visible = True
        self.group_vars = {} 
        self.group_widgets = [] # Used to store widgets for dynamic columns
        self.master_var = tk.BooleanVar(value=True)
        
        self.target_dir = self.load_config()

        # --- CUSTOM SCROLLBAR THEME (BLUE) ---
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vertical.TScrollbar", gripcount=0,
                        background="#007acc", darkcolor="#005e9c", lightcolor="#00a2ff",
                        troughcolor="#252526", bordercolor="#252526", arrowcolor="white")
        style.map("Vertical.TScrollbar", background=[('active', '#00a2ff')])

        # --- DRAGGABLE TITLE BAR ---
        title_bar = tk.Frame(root, bg="#2d2d30", relief="raised", bd=0)
        title_bar.pack(fill="x")
        title_bar.bind("<ButtonPress-1>", self.start_move)
        title_bar.bind("<B1-Motion>", self.do_move)
        
        tk.Label(title_bar, text=" Mod Cycler", bg="#2d2d30", fg="#00a2ff", font=("Segoe UI", 10, "bold")).pack(side="left", pady=6, padx=10)
        
        close_btn = tk.Button(title_bar, text="✕", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10), 
                              command=self.hide_window, activebackground="#e81123", activeforeground="white")
        close_btn.pack(side="right", padx=(0, 10))

        min_btn = tk.Button(title_bar, text="—", bg="#2d2d30", fg="#cccccc", bd=0, font=("Segoe UI", 10, "bold"), 
                            command=self.hide_window, activebackground="#555555", activeforeground="white")
        min_btn.pack(side="right", padx=5)

        # --- FOOTER SECTION (Pinned to Bottom) ---
        info_frame = tk.Frame(root, bg="#1e1e1e")
        info_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 15))
        
        binds = [("PGUP/DN", "Next/Prev"), ("INSERT", "Shuffle"), ("CAPS", "Auto-Cycle"), ("END", "Auto-Shuffle")]
        for i, (key, desc) in enumerate(binds):
            tk.Label(info_frame, text=key, bg="#1e1e1e", fg="#00a2ff", font=("Segoe UI", 8, "bold")).grid(row=i, column=0, sticky="w")
            tk.Label(info_frame, text=f" : {desc}", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 8)).grid(row=i, column=1, sticky="w")

        gen_btn = tk.Button(root, text="GENERATE .INI", bg="#007acc", fg="white", bd=0, font=("Segoe UI", 10, "bold"), 
                            command=self.generate_ini, activebackground="#005e9c", activeforeground="white")
        gen_btn.pack(side="bottom", fill="x", padx=20, pady=10, ipady=8)

        # --- HEADER SECTION (Pinned to Top) ---
        top_frame = tk.Frame(root, bg="#1e1e1e")
        top_frame.pack(side="top", fill="x", padx=20, pady=(15, 5))
        
        # FOLDER SELECTOR ROW WITH NEW LABEL
        folder_lbl_frame = tk.Frame(top_frame, bg="#1e1e1e")
        folder_lbl_frame.pack(fill="x", pady=(0, 15))
        tk.Label(folder_lbl_frame, text="Mods Folder (XXMI\\...MI\\Mods):", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(side="top", anchor="w")
        
        path_display_frame = tk.Frame(folder_lbl_frame, bg="#1e1e1e")
        path_display_frame.pack(fill="x", pady=(2, 0))
        
        self.path_lbl = tk.Label(path_display_frame, text=self.truncate_path(self.target_dir), bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 8))
        self.path_lbl.pack(side="left", anchor="w")
        
        browse_btn = tk.Button(path_display_frame, text="BROWSE", bg="#007acc", fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                               command=self.browse_folder, activebackground="#005e9c", activeforeground="white", padx=10)
        browse_btn.pack(side="right")

        tk.Label(top_frame, text="Mod Change Interval (Seconds):", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        self.timer_var = tk.StringVar(value="120")
        entry = tk.Entry(top_frame, textvariable=self.timer_var, width=10, bg="#333337", fg="white", bd=1, 
                         insertbackground="white", font=("Segoe UI", 11), justify="center")
        entry.pack(anchor="w")

        tk.Label(root, text="Detected Groups:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(side="top", anchor="w", padx=20, pady=(10, 0))

        # --- SELECT ALL SECTION ---
        tk.Checkbutton(root, text="Select All", variable=self.master_var, command=self.toggle_all,
                       bg="#1e1e1e", fg="#00a2ff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                       activeforeground="#ffffff", font=("Segoe UI", 9, "bold"), bd=0).pack(side="top", anchor="w", padx=20, pady=(0, 5))

        # --- SCROLLABLE LIST ---
        list_container = tk.Frame(root, bg="#252526", bd=1, relief="flat")
        list_container.pack(fill="both", expand=True, padx=20, pady=(0, 5))

        self.canvas = tk.Canvas(list_container, bg="#252526", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview, style="Vertical.TScrollbar")
        self.scroll_frame = tk.Frame(self.canvas, bg="#252526")

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Bind canvas resize to our dynamic columns function
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.refresh_groups()

        # --- RESIZE GRIP (Blue Bottom Right Corner) ---
        self.grip = tk.Canvas(root, width=15, height=15, bg="#1e1e1e", highlightthickness=0, cursor="bottom_right_corner")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.create_line(5, 15, 15, 5, fill="#00a2ff", width=2)
        self.grip.create_line(10, 15, 15, 10, fill="#00a2ff", width=2)
        
        self.grip.bind("<ButtonPress-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.do_resize)

        self.setup_tray()
        self.hotkey_thread = threading.Thread(target=self.listen_for_hotkey, daemon=True)
        self.hotkey_thread.start()

    # --- DYNAMIC COLUMNS LOGIC ---
    def on_canvas_resize(self, event):
        """Calculates how many columns can fit, updates the grid, and recalculates scroll region."""
        canvas_width = event.width
        # Assume each checkbox needs about 240 pixels to comfortably display
        col_width = 240 
        columns = max(1, canvas_width // col_width)

        if getattr(self, 'current_columns', 0) != columns:
            self.current_columns = columns
            self.regrid_checkboxes()
            
        # Ensure scroll region always updates when canvas resizes
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def regrid_checkboxes(self):
        """Arranges the checkboxes into the calculated number of columns."""
        cols = getattr(self, 'current_columns', 1)
        for index, cb in enumerate(self.group_widgets):
            r = index // cols
            c = index % cols
            cb.grid(row=r, column=c, sticky="w", padx=5, pady=2)

    # --- CONFIG & PATH LOGIC ---
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    saved_path = data.get("mods_path", BASE)
                    if os.path.exists(saved_path):
                        return saved_path
            except:
                pass
        return BASE

    def save_config(self, path):
        if not os.path.exists(APPDATA_DIR):
            os.makedirs(APPDATA_DIR)
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"mods_path": path}, f)

    def truncate_path(self, path, max_len=40):
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len-3):]

    def browse_folder(self):
        folder_selected = filedialog.askdirectory(title="Select your 'Mods' folder", initialdir=self.target_dir)
        if folder_selected:
            self.target_dir = os.path.normpath(folder_selected)
            self.path_lbl.config(text=self.truncate_path(self.target_dir))
            self.save_config(self.target_dir)
            self.refresh_groups()

    # --- RESIZE LOGIC ---
    def start_resize(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.start_w = self.root.winfo_width()
        self.start_h = self.root.winfo_height()

    def do_resize(self, event):
        dx = event.x_root - self.start_x
        dy = event.y_root - self.start_y
        new_w = max(320, self.start_w + dx)
        new_h = max(450, self.start_h + dy)
        self.root.geometry(f"{new_w}x{new_h}")

    # --- MOUSE LOGIC ---
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def toggle_all(self):
        state = self.master_var.get()
        for var in self.group_vars.values():
            var.set(state)

    def clean_name(self, raw_name):
        clean = re.split(r'[-(\[]', raw_name)[0]
        clean = clean.replace('_', ' ')
        return clean.strip().title()

    def refresh_groups(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        self.group_widgets.clear()

        managed_path = os.path.join(self.target_dir, "_MANAGED_")
        
        if not os.path.exists(managed_path):
            lbl = tk.Label(self.scroll_frame, text="No _MANAGED_ folder found.\nPlease select your game's Mods folder.", 
                           bg="#252526", fg="#ff4444", font=("Segoe UI", 9))
            lbl.grid(row=0, column=0, pady=10, padx=10)
            self.group_widgets.append(lbl)
            return

        group_folders = []
        for g in os.listdir(managed_path):
            m = re.match(r"group[_]?(\d+)", g)
            if m:
                gid = int(m.group(1))
                gpath = os.path.join(managed_path, g)
                
                try:
                    subfolders = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                    if len(subfolders) >= 2:
                        subfolders.sort()
                        display_label = self.clean_name(subfolders[0])
                        group_folders.append((gid, display_label))
                except:
                    pass
        
        group_folders.sort()

        for gid, name in group_folders:
            var = tk.BooleanVar(value=True)
            self.group_vars[gid] = var
            display_text = f"Group {gid} ({name})"
            cb = tk.Checkbutton(self.scroll_frame, text=display_text, variable=var, 
                                bg="#252526", fg="white", selectcolor="#1e1e1e", 
                                activebackground="#252526", activeforeground="#00a2ff",
                                font=("Segoe UI", 9), wraplength=220, justify="left")
            self.group_widgets.append(cb)
            
        # Initial grid placement
        self.regrid_checkboxes()
        # Force a scroll region update
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def setup_tray(self):
        menu = pystray.Menu(pystray.MenuItem('Show (Alt+S)', self.show_from_tray), pystray.MenuItem('Quit', self.quit_app))
        self.tray_icon = pystray.Icon("Mod Cycler", create_tray_icon(), "Mod Cycler", menu)
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
        try:
            timer_seconds = int(self.timer_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number.")
            return

        managed_path = os.path.join(self.target_dir, "_MANAGED_")
        if not os.path.exists(managed_path):
            messagebox.showerror("Error", "Could not find _MANAGED_ folder in the selected directory.")
            return

        final_groups = []
        for gid, var in self.group_vars.items():
            if not var.get(): continue
            
            g_folder = f"group{gid}"
            gpath = os.path.join(managed_path, g_folder)
            if not os.path.exists(gpath):
                gpath = os.path.join(managed_path, f"group_{gid}")

            if os.path.exists(gpath):
                mods = [f for f in os.listdir(gpath) if os.path.isdir(os.path.join(gpath, f)) and not f.startswith("_")]
                if len(mods) >= 2:
                    mods.sort()
                    deck = list(range(1, len(mods) + 1))
                    random.shuffle(deck)
                    final_groups.append({'id': gid, 'slots': len(mods), 'deck': deck})

        if not final_groups:
            messagebox.showwarning("Warning", "No valid groups selected.")
            return

        ini_path = os.path.join(self.target_dir, "mod_cycler.ini")
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write("; v6.1 WIDESCREEN EDITION\nnamespace = modmanageragl\\cycler\n\n[Constants]\n")
            f.write("global persist $auto_enable = 0\nglobal persist $shuffle_auto_enable = 0\nglobal persist $last_cycle = 0\n\n")
            for g in final_groups:
                f.write(f"global persist $g{g['id']}_pos = 0\nglobal persist $g{g['id']}_slot = {g['deck'][0]}\n")
            
            f.write("\n[KeyNext]\nkey = PGUP\nrun = CommandListNext\n[KeyPrev]\nkey = PGDN\nrun = CommandListPrev\n[KeyRandom]\nkey = INSERT\nrun = CommandListShuffle\n[KeyToggleAuto]\nkey = CAPSLOCK\nrun = CommandListToggleAuto\n[KeyToggleShuffleAuto]\nkey = END\nrun = CommandListToggleShuffleAuto\n")
            f.write("\n[CommandListToggleAuto]\n$auto_enable = 1 - $auto_enable\n$shuffle_auto_enable = 0\nif $auto_enable == 1\n    $last_cycle = time\n    run = CommandListNext\nendif\n")
            f.write("\n[CommandListToggleShuffleAuto]\n$shuffle_auto_enable = 1 - $shuffle_auto_enable\n$auto_enable = 0\nif $shuffle_auto_enable == 1\n    $last_cycle = time\n    run = CommandListShuffle\nendif\n")
            
            f.write("\n[CommandListNext]\n")
            for g in final_groups:
                f.write(f"$g{g['id']}_slot = $g{g['id']}_slot + 1\nif $g{g['id']}_slot > {g['slots']}\n    $g{g['id']}_slot = 1\nendif\n$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")
            
            f.write("\n[CommandListPrev]\n")
            for g in final_groups:
                f.write(f"$g{g['id']}_slot = $g{g['id']}_slot - 1\nif $g{g['id']}_slot < 1\n    $g{g['id']}_slot = {g['slots']}\nendif\n$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n")
            
            f.write("\n[CommandListShuffle]\n")
            for g in final_groups:
                f.write(f"$g{g['id']}_pos = ($g{g['id']}_pos + 1) % {g['slots']}\n")
                for pos, mod_id in enumerate(g['deck']):
                    f.write(f"if $g{g['id']}_pos == {pos}\n    $g{g['id']}_slot = {mod_id}\nendif\n")
                f.write(f"$\\modmanageragl\\group_{g['id']}\\active_slot = $g{g['id']}_slot\n\n")

            f.write(f"[Present]\nif $auto_enable == 1 || $shuffle_auto_enable == 1\n    if time - $last_cycle >= {timer_seconds}\n        $last_cycle = time\n        if $auto_enable == 1\n            run = CommandListNext\n        else\n            run = CommandListShuffle\n        endif\n    endif\nendif\n")
            
        orig_bg = self.root.cget("bg")
        self.root.configure(bg="#2b6b3e")
        self.root.after(300, lambda: self.root.configure(bg=orig_bg))
        messagebox.showinfo("Success", f"mod_cycler.ini generated in:\n{self.target_dir}\n\nPress F10 in-game to apply.")

if __name__ == "__main__":
    root = tk.Tk()
    app = GeneratorApp(root)
    root.mainloop()
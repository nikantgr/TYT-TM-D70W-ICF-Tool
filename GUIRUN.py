"""
ICF Tool GUI - A graphical frontend for icf_tool.py
Author: SV1TSD Nikos K. Kantarakias

Run with: python icf_tool_gui.py
No extra packages required - uses only Python standard library (tkinter).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import sys
import os
import threading
from datetime import datetime
import webbrowser

# ─────────────────────────────────────────────
#  Theme / Colour Palette
# ─────────────────────────────────────────────
BG       = "#f0f0f0"   # main background
BG2      = "#ffffff"   # panel/card background
BG3      = "#ffffff"   # input background
ACCENT   = "#005a9e"   # blue accent
ACCENT2  = "#008a00"   # cyan accent (encode)
SUCCESS  = "#107c10"
WARNING  = "#d83b01"
ERROR    = "#a80000"
FG       = "#000000"   # primary text
FG_DIM   = "#555555"   # secondary text
BORDER   = "#cccccc"
FONT_UI  = ("Segoe UI", 10)
FONT_H1  = ("Segoe UI", 16, "bold")
FONT_H2  = ("Segoe UI", 12, "bold")
FONT_MONO= ("Consolas", 9)

# Locate icf_tool.py relative to this script
TOOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icf_tool.py")


# ─────────────────────────────────────────────
#  Helper: themed tk.Frame  (card style)
# ─────────────────────────────────────────────
def card(parent, **kw):
    f = tk.Frame(parent, bg=BG2, relief="flat", bd=0, **kw)
    return f

def label(parent, text, font=FONT_UI, fg=FG, **kw):
    bg = kw.pop("bg", parent["bg"])
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)

def dim_label(parent, text, **kw):
    return label(parent, text, fg=FG_DIM, **kw)


# ─────────────────────────────────────────────
#  Custom styled widgets
# ─────────────────────────────────────────────
class IconButton(tk.Button):
    """Flat, rounded-looking button with hover effect."""
    def __init__(self, parent, text, command, color=ACCENT, **kw):
        super().__init__(
            parent, text=text, command=command,
            bg=color, fg="#ffffff", font=("Segoe UI", 10, "bold"),
            relief="solid", bd=1, padx=18, pady=8, cursor="hand2",
            activebackground=self._lighten(color), activeforeground="#ffffff",
            **kw
        )
        self._base = color
        self._light = self._lighten(color)
        self.bind("<Enter>", lambda e: self.config(bg=self._light))
        self.bind("<Leave>", lambda e: self.config(bg=self._base))

    @staticmethod
    def _lighten(hex_color):
        r = min(255, int(hex_color[1:3], 16) + 30)
        g = min(255, int(hex_color[3:5], 16) + 30)
        b = min(255, int(hex_color[5:7], 16) + 30)
        return f"#{r:02x}{g:02x}{b:02x}"


class FilePicker(tk.Frame):
    """Label + Entry + Browse button row."""
    def __init__(self, parent, label_text, filetypes, save=False,
                 initial_dir=None, accent=ACCENT):
        super().__init__(parent, bg=parent["bg"])
        self._save = save
        self._filetypes = filetypes
        self._initial_dir = initial_dir or os.path.expanduser("~")
        self._accent = accent

        label(self, label_text, fg=FG_DIM).pack(anchor="w", pady=(0, 2))

        row = tk.Frame(self, bg=parent["bg"])
        row.pack(fill="x")

        self.var = tk.StringVar()
        entry = tk.Entry(
            row, textvariable=self.var, font=FONT_MONO,
            bg=BG3, fg=FG, insertbackground=FG,
            relief="solid", bd=1
        )
        entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 6))

        btn = tk.Button(
            row, text="Browse…", font=("Segoe UI", 9),
            bg=BG3, fg=FG_DIM, relief="solid", bd=1, padx=10,
            cursor="hand2", command=self._browse,
            activebackground=BORDER, activeforeground=FG
        )
        btn.pack(side="left", ipady=7)

    def _browse(self):
        if self._save:
            path = filedialog.asksaveasfilename(
                initialdir=self._dir(), filetypes=self._filetypes,
                defaultextension=self._filetypes[0][1] if self._filetypes else ""
            )
        else:
            path = filedialog.askopenfilename(
                initialdir=self._dir(), filetypes=self._filetypes
            )
        if path:
            self.var.set(path)

    def _dir(self):
        current = self.var.get()
        if current:
            d = os.path.dirname(current)
            if os.path.isdir(d):
                return d
        return self._initial_dir

    def get(self):
        return self.var.get().strip()

    def set(self, val):
        self.var.set(val)


class LogBox(tk.Frame):
    """Scrollable log area with colour-coded lines."""
    def __init__(self, parent, height=12):
        super().__init__(parent, bg=BG, relief="flat", bd=0)

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x")
        label(header, "Output Log", font=("Segoe UI", 9, "bold"), fg=FG_DIM).pack(side="left")
        tk.Button(
            header, text="Clear", font=("Segoe UI", 8), bg=BG, fg=FG_DIM,
            relief="solid", bd=1, cursor="hand2", activebackground=BG,
            command=self.clear
        ).pack(side="right")

        frame = tk.Frame(self, bg=BG2, relief="flat", bd=0)
        frame.pack(fill="both", expand=True, pady=(4, 0))

        self.text = tk.Text(
            frame, height=height, font=FONT_MONO,
            bg="#ffffff", fg=FG, insertbackground=FG,
            relief="solid", bd=1, state="disabled", wrap="word"
        )
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb.pack(side="right", fill="y")

        self.text.tag_configure("info",    foreground=FG)
        self.text.tag_configure("success", foreground=SUCCESS)
        self.text.tag_configure("warning", foreground=WARNING)
        self.text.tag_configure("error",   foreground=ERROR)
        self.text.tag_configure("dim",     foreground=FG_DIM)
        self.text.tag_configure("accent",  foreground=ACCENT2)

    def _write(self, msg, tag="info"):
        self.text.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] ", "dim")
        self.text.insert("end", msg + "\n", tag)
        self.text.see("end")
        self.text.config(state="disabled")

    def info(self, msg):    self._write(msg, "info")
    def success(self, msg): self._write(msg, "success")
    def warning(self, msg): self._write(msg, "warning")
    def error(self, msg):   self._write(msg, "error")
    def accent(self, msg):  self._write(msg, "accent")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")


# ─────────────────────────────────────────────
#  Separator with optional label
# ─────────────────────────────────────────────
def separator(parent, label_text=None, pady=(12, 12)):
    f = tk.Frame(parent, bg=parent["bg"])
    f.pack(fill="x", pady=pady)
    if label_text:
        lbl = tk.Label(f, text=f"  {label_text}  ", font=("Segoe UI", 8, "bold"),
                       fg=FG_DIM, bg=parent["bg"])
        lbl.pack()
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", before=lbl, pady=(0, 0))
    else:
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x")


# ─────────────────────────────────────────────
#  Tool runner
# ─────────────────────────────────────────────
def run_tool(args, log, on_done=None):
    """Run icf_tool.py in a background thread and stream output to log."""
    cmd = [sys.executable, TOOL_PATH] + args

    def _work():
        log.accent("► " + " ".join(f'"{a}"' if " " in a else a for a in cmd[2:]))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(TOOL_PATH)
            )
            for line in proc.stdout:
                stripped = line.rstrip()
                if not stripped:
                    continue
                lo = stripped.lower()
                if any(k in lo for k in ("error", "traceback", "exception")):
                    log.error(stripped)
                elif any(k in lo for k in ("decoded", "encoded", "done", "ok")):
                    log.success(stripped)
                elif "warning" in lo:
                    log.warning(stripped)
                else:
                    log.info(stripped)
            proc.wait()
            if proc.returncode == 0:
                log.success("✔ Finished successfully (exit 0)")
                if on_done:
                    on_done(True)
            else:
                log.error(f"✖ Process exited with code {proc.returncode}")
                if on_done:
                    on_done(False)
        except FileNotFoundError:
            log.error(f"Cannot find Python or icf_tool.py: {TOOL_PATH}")
            if on_done:
                on_done(False)
        except Exception as ex:
            log.error(f"Unexpected error: {ex}")
            if on_done:
                on_done(False)

    t = threading.Thread(target=_work, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════════════════
#  DECODE TAB
# ═══════════════════════════════════════════════════════════════════
class DecodeTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()

    def _build(self):
        # ── Header ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(18, 0))
        label(hdr, "📥  Decode ICF → CHIRP style CSV", font=FONT_H1, fg=ACCENT).pack(anchor="w")
        dim_label(hdr, "Convert a radio .icf file into editable channels and settings CSVs.").pack(anchor="w", pady=(2, 0))

        separator(self, pady=(12, 4))

        # ── Input card ──────────────────────────────────────────────
        c = card(self)
        c.pack(fill="x", padx=20, pady=6)
        inner = tk.Frame(c, bg=BG2)
        inner.pack(fill="x", padx=16, pady=14)

        label(inner, "Input", font=FONT_H2).pack(anchor="w", pady=(0, 8))

        self.icf_in = FilePicker(
            inner, "Source .icf file",
            filetypes=[("ICF radio files", "*.icf"), ("All files", "*.*")],
            accent=ACCENT
        )
        self.icf_in.pack(fill="x")
        self.icf_in.var.trace_add("write", self._autofill_outputs)

        separator(c, pady=(0, 0))

        # ── Output card ─────────────────────────────────────────────
        c2 = card(self)
        c2.pack(fill="x", padx=20, pady=6)
        inner2 = tk.Frame(c2, bg=BG2)
        inner2.pack(fill="x", padx=16, pady=14)

        label(inner2, "Output  (optional – leave blank for defaults)", font=FONT_H2).pack(anchor="w", pady=(0, 8))

        self.out_ch = FilePicker(
            inner2, "Channels CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            save=True, accent=ACCENT
        )
        self.out_ch.pack(fill="x", pady=(0, 8))

        self.out_set = FilePicker(
            inner2, "Settings CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            save=True, accent=ACCENT
        )
        self.out_set.pack(fill="x")

        # ── Run button ───────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=10)
        self.run_btn = IconButton(btn_row, "  ▶  Run Decode", command=self._run, color=ACCENT)
        self.run_btn.pack(side="left")
        self.open_btn = tk.Button(
            btn_row, text="Open output folder", font=("Segoe UI", 9),
            bg=BG2, fg=FG_DIM, relief="solid", bd=1, padx=12, pady=8,
            cursor="hand2", command=self._open_folder,
            activebackground=BORDER, activeforeground=FG
        )
        self.open_btn.pack(side="left", padx=(8, 0))

        # ── Log ──────────────────────────────────────────────────────
        self.log = LogBox(self, height=10)
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 16))

        self.log.info("Ready. Select an .icf file and click Run Decode.")

    def _autofill_outputs(self, *_):
        src = self.icf_in.get()
        if not src:
            return
        base = os.path.splitext(src)[0]
        date = datetime.now().strftime("%Y%m%d")
        base_name = os.path.basename(base)
        dir_name  = os.path.dirname(src)
        stem = os.path.join(dir_name, f"{base_name}-{date}")
        if not self.out_ch.get():
            self.out_ch.set(stem + "-channels.csv")
        if not self.out_set.get():
            self.out_set.set(stem + "-settings.csv")

    def _run(self):
        icf = self.icf_in.get()
        if not icf:
            messagebox.showwarning("Missing input", "Please choose a source .icf file.")
            return
        if not os.path.isfile(icf):
            messagebox.showerror("File not found", f"Cannot find:\n{icf}")
            return

        args = ["decode", icf]
        ch  = self.out_ch.get()
        st  = self.out_set.get()
        if ch:  args.append(ch)
        if st:  args.append(st)

        self.run_btn.config(state="disabled", text="  ⏳  Running…")
        self.log.info(f"Decoding: {os.path.basename(icf)}")

        def done(ok):
            self.run_btn.config(state="normal", text="  ▶  Run Decode")
            if ok and ch:
                self._last_dir = os.path.dirname(ch)

        run_tool(args, self.log, on_done=lambda ok: self.after(0, lambda: done(ok)))

    def _open_folder(self):
        path = self.out_ch.get() or self.icf_in.get()
        if path:
            d = os.path.dirname(os.path.abspath(path))
            if os.path.isdir(d):
                os.startfile(d)


# ═══════════════════════════════════════════════════════════════════
#  ENCODE TAB
# ═══════════════════════════════════════════════════════════════════
class EncodeTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()

    def _build(self):
        # ── Header ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(18, 0))
        label(hdr, "📤  Encode CHIRP style CSV → ICF", font=FONT_H1, fg=ACCENT2).pack(anchor="w")
        dim_label(hdr, "Rebuild a radio .icf file from your edited channels and settings CSVs.").pack(anchor="w", pady=(2, 0))

        separator(self, pady=(12, 4))

        # ── Input card ──────────────────────────────────────────────
        c = card(self)
        c.pack(fill="x", padx=20, pady=6)
        inner = tk.Frame(c, bg=BG2)
        inner.pack(fill="x", padx=16, pady=14)

        label(inner, "Input", font=FONT_H2).pack(anchor="w", pady=(0, 8))

        self.ch_in = FilePicker(
            inner, "Channels CSV  (required)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            accent=ACCENT2
        )
        self.ch_in.pack(fill="x", pady=(0, 8))
        self.ch_in.var.trace_add("write", self._autofill_settings)

        self.set_in = FilePicker(
            inner, "Settings CSV  (auto-derived from channels name if blank)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            accent=ACCENT2
        )
        self.set_in.pack(fill="x", pady=(0, 8))

        self.tpl_in = FilePicker(
            inner, "Template .icf  (optional – uses built-in template if blank)",
            filetypes=[("ICF radio files", "*.icf"), ("All files", "*.*")],
            accent=ACCENT2
        )
        self.tpl_in.pack(fill="x")

        # ── Output card ─────────────────────────────────────────────
        c2 = card(self)
        c2.pack(fill="x", padx=20, pady=6)
        inner2 = tk.Frame(c2, bg=BG2)
        inner2.pack(fill="x", padx=16, pady=14)

        label(inner2, "Output", font=FONT_H2).pack(anchor="w", pady=(0, 8))

        self.icf_out = FilePicker(
            inner2, "Output .icf file  (required)",
            filetypes=[("ICF radio files", "*.icf"), ("All files", "*.*")],
            save=True, accent=ACCENT2
        )
        self.icf_out.pack(fill="x")

        # ── Run button ───────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=10)
        self.run_btn = IconButton(btn_row, "  ▶  Run Encode", command=self._run, color=ACCENT2)
        self.run_btn.pack(side="left")
        self.open_btn = tk.Button(
            btn_row, text="Open output folder", font=("Segoe UI", 9),
            bg=BG2, fg=FG_DIM, relief="solid", bd=1, padx=12, pady=8,
            cursor="hand2", command=self._open_folder,
            activebackground=BORDER, activeforeground=FG
        )
        self.open_btn.pack(side="left", padx=(8, 0))

        # ── Log ──────────────────────────────────────────────────────
        self.log = LogBox(self, height=10)
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 16))

        self.log.info("Ready. Select channels CSV and output .icf path, then click Run Encode.")

    def _autofill_settings(self, *_):
        ch = self.ch_in.get()
        if not ch:
            return
        # Mirror icf-encode.cmd logic: replace -channels.csv with -settings.csv
        derived = ch.replace("-channels.csv", "-settings.csv")
        if derived != ch and os.path.isfile(derived):
            if not self.set_in.get():
                self.set_in.set(derived)
        # Suggest output ICF path next to channels
        if not self.icf_out.get():
            base = ch.replace("-channels.csv", "").replace(".csv", "")
            self.icf_out.set(base + "-output.icf")

    def _run(self):
        ch  = self.ch_in.get()
        st  = self.set_in.get()
        out = self.icf_out.get()
        tpl = self.tpl_in.get()

        if not ch:
            messagebox.showwarning("Missing input", "Please choose a channels CSV file.")
            return
        if not os.path.isfile(ch):
            messagebox.showerror("File not found", f"Cannot find channels CSV:\n{ch}")
            return

        # Derive settings CSV if not set
        if not st:
            derived = ch.replace("-channels.csv", "-settings.csv")
            if derived != ch and os.path.isfile(derived):
                st = derived
                self.set_in.set(st)
            else:
                messagebox.showwarning("Missing settings", 
                    "Could not auto-find settings CSV.\nPlease select it manually.")
                return
        if not os.path.isfile(st):
            messagebox.showerror("File not found", f"Cannot find settings CSV:\n{st}")
            return
        if not out:
            messagebox.showwarning("Missing output", "Please choose an output .icf file path.")
            return

        args = ["encode", ch, st, out]
        if tpl:
            if not os.path.isfile(tpl):
                messagebox.showerror("File not found", f"Cannot find template .icf:\n{tpl}")
                return
            args.append(tpl)

        self.run_btn.config(state="disabled", text="  ⏳  Running…")
        self.log.info(f"Encoding: {os.path.basename(ch)} → {os.path.basename(out)}")

        def done(ok):
            self.run_btn.config(state="normal", text="  ▶  Run Encode")

        run_tool(args, self.log, on_done=lambda ok: self.after(0, lambda: done(ok)))

    def _open_folder(self):
        path = self.icf_out.get() or self.ch_in.get()
        if path:
            d = os.path.dirname(os.path.abspath(path))
            if os.path.isdir(d):
                os.startfile(d)


# ═══════════════════════════════════════════════════════════════════
#  ABOUT TAB
# ═══════════════════════════════════════════════════════════════════
class AboutTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()

    def _build(self):
        wrapper = tk.Frame(self, bg=BG)
        wrapper.pack(expand=True)

        label(wrapper, "TYT TM-D70W  ICF Tool", font=("Segoe UI", 20, "bold"), fg=FG).pack(pady=(30, 4))
        label(wrapper, "Graphical Frontend", font=("Segoe UI", 12), fg=FG_DIM).pack()

        separator(wrapper, pady=(18, 18))

        rows = [
            ("Author",   "SV1TSD  Nikos K. Kantarakias"),
            ("YouTube",  "youtube.com/@NikosKantarakias"),
            ("Core",     "icf_tool.py  (standalone – no changes)"),
            ("Requires", "Python 3.8+  ·  tkinter (built-in)"),
            ("License",  "GNU Affero General Public License v3"),
        ]
        for key, val in rows:
            row = tk.Frame(wrapper, bg=BG)
            row.pack(pady=3)
            label(row, f"{key}:", fg=FG_DIM, width=10, anchor="e").pack(side="left")
            if "youtube.com" in val:
                lbl = tk.Label(row, text=f"  {val}", fg=ACCENT, bg=BG, cursor="hand2", font=("Segoe UI", 10, "bold"))
                lbl.pack(side="left")
                lbl.bind("<Button-1>", lambda e, url=val: webbrowser.open("https://www." + url.strip() + "?sub_confirmation=1"))
            else:
                label(row, f"  {val}", fg=FG).pack(side="left")

        separator(wrapper, pady=(18, 18))

        label(wrapper, "⚠  Disclaimer", font=("Segoe UI", 10, "bold"), fg=WARNING).pack()
        label(
            wrapper,
            "This tool is provided as-is. Always back up your .icf file before use.\n"
            "The author accepts no liability for radio misconfiguration or data loss.",
            fg=FG_DIM, justify="center"
        ).pack(pady=(4, 0))

        # Show tool path
        separator(wrapper, pady=(18, 8))
        dim_label(wrapper, f"icf_tool.py path:  {TOOL_PATH}").pack()
        exists_text = "✔  Found" if os.path.isfile(TOOL_PATH) else "✖  NOT FOUND"
        exists_color = SUCCESS if os.path.isfile(TOOL_PATH) else ERROR
        label(wrapper, exists_text, fg=exists_color, font=("Segoe UI", 10, "bold")).pack(pady=4)


# ═══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION WINDOW
# ═══════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ICF Tool  ·  TYT TM-D70W")
        self.geometry("780x760")
        self.minsize(700, 680)
        self.configure(bg=BG)
        self._set_icon()
        self._build_ui()

    def _set_icon(self):
        # Draw a simple coloured emoji-style icon in the title bar using PhotoImage
        try:
            img = tk.PhotoImage(width=32, height=32)
            # Draw a radio-ish icon: blue rectangle + antenna
            for y in range(8, 24):
                for x in range(4, 28):
                    img.put("#3b82f6", (x, y))
            for y in range(2, 9):
                img.put("#22d3ee", (14, y))
                img.put("#22d3ee", (15, y))
            for y in range(1, 5):
                img.put("#22d3ee", (11+y, 2))
            self.iconphoto(True, img)
        except Exception:
            pass

    def _build_ui(self):
        # ── Top title bar ─────────────────────────────────────────────
        topbar = tk.Frame(self, bg="#e6e6e6", height=44)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)
        label(topbar, "  📡  ICF Tool  ·  TYT TM-D70W", font=("Segoe UI", 12, "bold"), fg=FG,
              bg="#e6e6e6").pack(side="left", padx=10, pady=8)
        dim_label(topbar, "SV1TSD  |  Radio File Converter", bg="#e6e6e6").pack(side="right", padx=14)

        # ── Tab selector (custom) ─────────────────────────────────────
        self.tab_bar = tk.Frame(self, bg="#e6e6e6", height=36)
        self.tab_bar.pack(fill="x", side="top")

        self._tabs = {}
        self._tab_btns = {}
        self._active_tab = None

        tab_frame = tk.Frame(self, bg=BG)
        tab_frame.pack(fill="both", expand=True)
        self._tab_frame = tab_frame

        tabs_def = [
            ("decode", "  📥  Decode  ",   DecodeTab),
            ("encode", "  📤  Encode  ",   EncodeTab),
            ("about",  "  ℹ  About   ",   AboutTab),
        ]
        for key, title, cls in tabs_def:
            frame = cls(self._tab_frame)
            frame.place(relwidth=1, relheight=1)
            self._tabs[key] = frame

            btn = tk.Button(
                self.tab_bar, text=title, font=("Segoe UI", 10),
                bg="#e6e6e6", fg=FG_DIM, relief="flat", bd=0, padx=6,
                cursor="hand2", activebackground=BG2, activeforeground=FG,
                command=lambda k=key: self._switch(k)
            )
            btn.pack(side="left", pady=4, padx=2)
            self._tab_btns[key] = btn

        # Active underline indicator
        self._indicator = tk.Frame(self.tab_bar, bg=ACCENT, height=3)

        self._switch("decode")

    def _switch(self, key):
        if self._active_tab == key:
            return
        self._active_tab = key

        for k, f in self._tabs.items():
            if k == key:
                f.lift()
            else:
                f.lower()

        for k, b in self._tab_btns.items():
            if k == key:
                b.config(fg=FG, bg=BG2)
                color = ACCENT2 if key == "encode" else ACCENT
                # move indicator
                b.update_idletasks()
                x = b.winfo_x()
                w = b.winfo_width()
                self._indicator.place(x=x, y=30, width=w, height=3)
                self._indicator.config(bg=color)
            else:
                b.config(fg=FG_DIM, bg="#e6e6e6")


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()

"""
app/ingest_app.py
GHG-MONITOR — Ingestion Desktop App

Cross-platform desktop UI using standard tkinter + ttk.
Works on Python 3.9+ with no external UI dependencies.

Requires:
    pip install pyyaml loguru
"""

import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Constants ──────────────────────────────────────────────────────────────────

# DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[2] / "ghg-monitor-data"

GAS_OPTIONS      = ["CH4", "CO2", "N2O", "Other"]
PLATFORM_OPTIONS = ["GND", "AIR"]
YESNO_OPTIONS    = ["yes", "no"]

BG        = "#2b2b2b"
BG_CARD   = "#3c3f41"
BG_HEADER = "#1a5c96"
BG_ENTRY  = "#45494a"
FG        = "#bbbbbb"
FG_BRIGHT = "#ffffff"
FG_DIM    = "#888888"
ACCENT    = "#4a9fd4"

LOG_COLORS = {
    "INFO":    "#4a9fd4",
    "SUCCESS": "#4caf50",
    "WARNING": "#ff9800",
    "ERROR":   "#f44336",
    "DEBUG":   "#888888",
}

LABEL_WIDTH = 22
FONT        = ("Helvetica", 11)
FONT_BOLD   = ("Helvetica", 11, "bold")
FONT_MONO   = ("Courier New", 11)


# ── Main App ───────────────────────────────────────────────────────────────────

class IngestApp(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("Hyperspectral Data Ingestion App")
        self.geometry("820x900")
        self.minsize(700, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._log_queue = queue.Queue()
        self._build_ui()
        self._poll_log_queue()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG_HEADER)
        header.pack(fill="x")
        tk.Label(header, text="Hyperspectral Data Ingestion", bg=BG_HEADER, fg=FG_BRIGHT,
                 font=("Helvetica", 18, "bold"), pady=10).pack()
        # tk.Label(header, text="Hyperspectral Data Ingestion", bg=BG_HEADER,
        #          fg="#add4f5", font=FONT, pady=0).pack(pady=(0, 10))

        # Scrollable area
        wrapper = tk.Frame(self, bg=BG)
        wrapper.pack(fill="both", expand=True)

        canvas    = tk.Canvas(wrapper, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._frame = tk.Frame(canvas, bg=BG)
        frame_id = canvas.create_window((0, 0), window=self._frame, anchor="nw")

        def on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(e):
            canvas.itemconfig(frame_id, width=e.width)

        self._frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-int(e.delta / 60), "units"))

        f = self._frame
        f.columnconfigure(0, weight=1)

        # ── Fields ────────────────────────────────────────────────────────────
        self._section(f, "📁  Source")
        self._source_var    = tk.StringVar()
        self._data_root_var = tk.StringVar() # value=str(DEFAULT_DATA_ROOT))
        self._folder_row(f, "Path files (hdr, hyspex)", self._source_var)
        self._folder_row(f, "Path to save data", self._data_root_var)

        self._section(f, "🗂  Campaign")
        self._site_id_var     = tk.StringVar()
        self._campaign_id_var = tk.StringVar()
        self._platform_var    = tk.StringVar(value="GND")
        self._entry_row(f, "Site ID", self._site_id_var, "e.g. LAB_AAR01")
        self._entry_row(f, "Campaign ID", self._campaign_id_var, "Auto-generated if left empty")
        self._combo_row(f, "Platform", self._platform_var, PLATFORM_OPTIONS)

        self._section(f, "👤  Operator")
        self._operator_var   = tk.StringVar()
        self._target_gas_var = tk.StringVar(value="CH4")
        self._time_end_var   = tk.StringVar()
        self._entry_row(f, "Operator name", self._operator_var, "Your full name")
        self._combo_row(f, "Target gas", self._target_gas_var, GAS_OPTIONS)
        self._entry_row(f, "End time (UTC)", self._time_end_var, "e.g. 10:02:00")

        # self._section(f, "⚙️  References")
        # self._white_ref_var = tk.StringVar(value="no")
        # self._dark_ref_var  = tk.StringVar(value="no")
        # self._gps_log_var   = tk.StringVar(value="no")
        # self._combo_row(f, "White reference", self._white_ref_var, YESNO_OPTIONS)
        # self._combo_row(f, "Dark reference",  self._dark_ref_var,  YESNO_OPTIONS)
        # self._combo_row(f, "GPS log",         self._gps_log_var,   YESNO_OPTIONS)

        self._section(f, "📝  Notes")
        notes_outer = tk.Frame(f, bg=BG)
        notes_outer.pack(fill="x", padx=16, pady=4)
        tk.Label(notes_outer, text="Notes", bg=BG, fg=FG,
                 font=FONT, width=LABEL_WIDTH, anchor="nw").pack(side="left", anchor="nw", pady=2)
        self._notes_text = tk.Text(notes_outer, height=4, bg=BG_ENTRY, fg=FG,
                                   font=FONT, relief="flat", wrap="word",
                                   insertbackground=FG,
                                   highlightthickness=1, highlightbackground="#555")
        self._notes_text.pack(side="left", fill="x", expand=True)

        # # Run button
        # tk.Frame(f, bg=BG, height=8).pack()
        # self._run_btn = tk.Button(
        #     f, text="▶  Run Ingestion",
        #     bg=BG_HEADER, fg=FG_BRIGHT,
        #     activebackground="#154d80", activeforeground=FG_BRIGHT,
        #     font=("Helvetica", 13, "bold"),
        #     relief="flat", cursor="hand2", pady=10,
        #     command=self._run
        # )
        # self._run_btn.pack(fill="x", padx=16, pady=(4, 2))

        # Run button
        tk.Frame(f, bg=BG, height=8).pack()
        self._run_btn = tk.Button(
            f, text="▶  Run Ingestion",
            bg="#2e7d32", fg="#000000",
            activebackground="#1b5e20", activeforeground="#000000",
            font=("Helvetica", 13, "bold"),
            relief="flat", cursor="hand2", pady=10,
            command=self._run
        )
        self._run_btn.pack(fill="x", padx=16, pady=(4, 2))

        # Status
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(f, textvariable=self._status_var, bg=BG, fg=FG_DIM,
                 font=("Helvetica", 10), anchor="w").pack(fill="x", padx=20, pady=(0, 4))

        # Log
        self._section(f, "📋  Log Output")
        log_outer = tk.Frame(f, bg=BG)
        log_outer.pack(fill="x", padx=16, pady=(0, 20))
        log_outer.columnconfigure(0, weight=1)

        self._log_box = tk.Text(
            log_outer, height=12,
            bg="#1e1e1e", fg=FG,
            font=FONT_MONO,
            state="disabled", relief="flat",
            wrap="word", insertbackground=FG,
            highlightthickness=1, highlightbackground="#555",
        )
        self._log_box.pack(side="left", fill="both", expand=True)

        log_sb = ttk.Scrollbar(log_outer, orient="vertical", command=self._log_box.yview)
        log_sb.pack(side="right", fill="y")
        self._log_box.configure(yscrollcommand=log_sb.set)

        for level, color in LOG_COLORS.items():
            self._log_box.tag_config(level, foreground=color)

    # ── Row helpers ────────────────────────────────────────────────────────────

    def _section(self, parent, title):
        frame = tk.Frame(parent, bg=BG_CARD, pady=6)
        frame.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(frame, text=title, bg=BG_CARD, fg=FG_BRIGHT,
                 font=FONT_BOLD, anchor="w").pack(side="left", padx=12)

    def _folder_row(self, parent, label, var):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=BG_ENTRY, fg=FG,
                 font=FONT, relief="flat", insertbackground=FG,
                 highlightthickness=1, highlightbackground="#555").pack(
            side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        tk.Button(row, text="Browse", bg=BG_CARD, fg=FG,
                  font=("Helvetica", 10), relief="flat", cursor="hand2",
                  activebackground="#555", padx=8,
                  command=lambda v=var: v.set(filedialog.askdirectory() or v.get())
                  ).pack(side="left")

    def _entry_row(self, parent, label, var, placeholder=""):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=var, bg=BG_ENTRY, fg=FG,
                         font=FONT, relief="flat", insertbackground=FG,
                         highlightthickness=1, highlightbackground="#555")
        entry.pack(side="left", fill="x", expand=True, ipady=4)

        if placeholder:
            entry.insert(0, placeholder)
            entry.config(fg=FG_DIM)

            def on_in(e, en=entry, ph=placeholder):
                if en.get() == ph:
                    en.delete(0, "end")
                    en.config(fg=FG)

            def on_out(e, en=entry, ph=placeholder, v=var):
                if not en.get():
                    en.insert(0, ph)
                    en.config(fg=FG_DIM)
                    v.set("")

            entry.bind("<FocusIn>",  on_in)
            entry.bind("<FocusOut>", on_out)

    def _combo_row(self, parent, label, var, options):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=var, values=options,
                          state="readonly", font=FONT, width=16)
        cb.pack(side="left", ipady=3)

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate(self) -> list:
        errors = []
        if not self._source_var.get().strip():
            errors.append("Raw files folder is required.")
        elif not Path(self._source_var.get()).exists():
            errors.append("Raw files folder does not exist.")
        if not self._data_root_var.get().strip():
            errors.append("Data root folder is required.")
        if not self._site_id_var.get().strip():
            errors.append("Site ID is required.")
        if not self._operator_var.get().strip():
            errors.append("Operator name is required.")
        return errors

    # ── Run ────────────────────────────────────────────────────────────────────

    def _run(self):
        errors = self._validate()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(f"• {e}" for e in errors))
            return

        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._run_btn.configure(state="disabled", text="Running…")
        self._status_var.set("Running ingestion…")

        params = {
            "source_folder":  self._source_var.get().strip(),
            "data_root":      self._data_root_var.get().strip(),
            "site_id":        self._site_id_var.get().strip(),
            "campaign_id":    self._campaign_id_var.get().strip() or None,
            "platform":       self._platform_var.get(),
            "operator":       self._operator_var.get().strip(),
            "target_gas":     self._target_gas_var.get(),
            "time_end":       self._time_end_var.get().strip() or None,
            # "white_ref":      self._white_ref_var.get(),
            # "dark_ref":       self._dark_ref_var.get(),
            # "gps_log":        self._gps_log_var.get(),
            "notes":          self._notes_text.get("1.0", "end").strip(),
            "sensor":         None,
            "serial_number":  None,
            "overwrite_meta": False,
        }

        thread = threading.Thread(target=self._run_worker, args=(params,), daemon=True)
        thread.start()

    def _run_worker(self, params: dict):
        try:
            from ingestion.ingest_core import run_ingestion
            run_ingestion(params, log_callback=self._queue_log)
            self._queue_log("SUCCESS", "=== Ingestion complete ===")
            self.after(0, self._on_success)
        except SystemExit:
            self.after(0, self._on_error)
        except Exception as e:
            self._queue_log("ERROR", f"Unexpected error: {e}")
            self.after(0, self._on_error)

    def _on_success(self):
        self._run_btn.configure(state="normal", text="▶  Run Ingestion")
        self._status_var.set("✓ Ingestion completed successfully")

    def _on_error(self):
        self._run_btn.configure(state="normal", text="▶  Run Ingestion")
        self._status_var.set("✗ Ingestion failed — see log for details")

    # ── Log queue ──────────────────────────────────────────────────────────────

    def _queue_log(self, level: str, message: str):
        self._log_queue.put((level, message))

    def _poll_log_queue(self):
        try:
            while True:
                level, message = self._log_queue.get_nowait()
                self._append_log(level, message)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp}  {level:<8}  {message}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line, level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = IngestApp()
    app.mainloop()

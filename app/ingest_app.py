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

from utils.dmp import SITE_TYPE_CODES
from utils.dmp import SITE_LOCATION_CODES

# ── Constants ──────────────────────────────────────────────────────────────────

GAS_OPTIONS       = ["CH4", "CO2", "N2O", "Other"]
OPERATOR_NAME = ["DANIEL", "SOPHIE", "CHRISTOFFER","JESPER"]
PLATFORM_OPTIONS  = ["GND", "AIR"]
DATATYPE_OPTIONS  = ["raw", "hyrad"]
SITE_TYPE_OPTIONS = sorted(SITE_TYPE_CODES)  # e.g. ["AGR", "BIO", "LAB", ...]
SITE_LOCATION_OPTIONS = sorted(SITE_LOCATION_CODES)

BG          = "#2b2b2b"
BG_CARD     = "#3c3f41"
BG_HEADER   = "#1a5c96"
BG_ENTRY    = "#45494a"
BG_READONLY = "#3a3a3a"
FG          = "#bbbbbb"
FG_BRIGHT   = "#ffffff"
FG_DIM      = "#888888"
FG_AUTO     = "#4a9fd4"

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
        self._hdr_date  = ""

        self._build_ui()
        self._poll_log_queue()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG_HEADER)
        header.pack(fill="x")
        tk.Label(header, text="Hyperspectral Data Ingestion", bg=BG_HEADER, fg=FG_BRIGHT,
                 font=("Helvetica", 18, "bold"), pady=10).pack()

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

        self._frame.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(frame_id, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-int(e.delta / 60), "units"))

        f = self._frame
        f.columnconfigure(0, weight=1)

        # ── Source ────────────────────────────────────────────────────────────
        self._section(f, "📁  Source")
        self._source_var    = tk.StringVar()
        self._data_root_var = tk.StringVar()
        self._folder_row(f, "Path files (hdr, hyspex)", self._source_var,
                         on_browse=self._on_source_browsed)
        self._folder_row(f, "Path to save data", self._data_root_var)

        # ── Campaign ──────────────────────────────────────────────────────────
        self._section(f, "🗂  Campaign")
        self._site_type_var = tk.StringVar(value=SITE_TYPE_OPTIONS[0])
        self._site_loc_var = tk.StringVar(value=SITE_LOCATION_OPTIONS[0])
        #self._site_loc_var  = tk.StringVar()
        self._site_num_var  = tk.StringVar(value="01")
        self._camp_seq_var  = tk.StringVar(value="01")
        self._platform_var  = tk.StringVar(value="GND")
        self._datatype_var  = tk.StringVar(value="raw")

        self._site_id_row(f)
        self._campaign_id_row(f)
        self._combo_row(f, "Platform", self._platform_var, PLATFORM_OPTIONS)
        self._combo_row(f, "Data type", self._datatype_var, DATATYPE_OPTIONS)

        # ── Operator ──────────────────────────────────────────────────────────
        self._section(f, "👤  Operator")
        self._operator_var   = tk.StringVar()
        self._target_gas_var = tk.StringVar(value="CH4")
        # self._time_end_var   = tk.StringVar()
        self._combo_row(f, "Operator name", self._operator_var, OPERATOR_NAME)
        self._combo_row(f, "Target gas", self._target_gas_var, GAS_OPTIONS)
        # self._entry_row(f, "End time (UTC)", self._time_end_var, "e.g. 10:02:00")

        # ── Notes ─────────────────────────────────────────────────────────────
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

        # ── Run button ────────────────────────────────────────────────────────
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

        # ── Status ────────────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(f, textvariable=self._status_var, bg=BG, fg=FG_DIM,
                 font=("Helvetica", 10), anchor="w").pack(fill="x", padx=20, pady=(0, 4))

        # ── Log output ────────────────────────────────────────────────────────
        self._section(f, "📋  Log Output")
        log_outer = tk.Frame(f, bg=BG)
        log_outer.pack(fill="x", padx=16, pady=(0, 20))

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

    def _folder_row(self, parent, label, var, on_browse=None):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=BG_ENTRY, fg=FG,
                 font=FONT, relief="flat", insertbackground=FG,
                 highlightthickness=1, highlightbackground="#555").pack(
            side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

        def browse():
            folder = filedialog.askdirectory()
            if folder:
                var.set(folder)
                if on_browse:
                    on_browse(folder)

        tk.Button(row, text="Browse", bg=BG_CARD, fg=FG,
                  font=("Helvetica", 10), relief="flat", cursor="hand2",
                  activebackground="#555", padx=8,
                  command=browse).pack(side="left")

    def _site_id_row(self, parent):
        """
        Site ID row: [ TYPE ▾ ] _ [ LOC ] _ [ ## ]
        Assembled as TYPE_LOC## e.g. LAB_AAR01
        """
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)

        tk.Label(row, text="Site ID", bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")

        # Site type — dropdown
        ttk.Combobox(row, textvariable=self._site_type_var,
                     values=SITE_TYPE_OPTIONS, state="readonly",
                     font=FONT, width=6).pack(side="left", ipady=3)

        tk.Label(row, text="_", bg=BG, fg=FG_AUTO,
                 font=FONT_BOLD).pack(side="left", padx=2)

        # Location — 3 letter free text

        ttk.Combobox(row, textvariable=self._site_loc_var,
                     values=SITE_LOCATION_OPTIONS, state="readonly",
                     font=FONT, width=6).pack(side="left", ipady=3)

        tk.Label(row, text="_", bg=BG, fg=FG_AUTO,
                 font=FONT_BOLD).pack(side="left", padx=2)

        # loc_entry = tk.Entry(row, textvariable=self._site_loc_var,
        #                      bg=BG_ENTRY, fg=FG, font=FONT, relief="flat",
        #                      insertbackground=FG,
        #                      highlightthickness=1, highlightbackground="#555",
        #                      width=5)
        # loc_entry.pack(side="left", ipady=4)
        #
        # tk.Label(row, text="_", bg=BG, fg=FG_AUTO,
        #          font=FONT_BOLD).pack(side="left", padx=2)

        # Number — 2 digit
        tk.Entry(row, textvariable=self._site_num_var,
                 bg=BG_ENTRY, fg=FG, font=FONT, relief="flat",
                 insertbackground=FG,
                 highlightthickness=1, highlightbackground="#555",
                 width=4).pack(side="left", ipady=4, padx=(0, 8))

        # Preview
        self._site_id_preview_var = tk.StringVar()
        tk.Label(row, textvariable=self._site_id_preview_var,
                 bg=BG, fg=FG_AUTO, font=FONT).pack(side="left")

        # Update preview on any change
        for var in (self._site_type_var, self._site_loc_var, self._site_num_var):
            var.trace_add("write", self._update_site_id_preview)

        self._update_site_id_preview()

    def _update_site_id_preview(self, *_):
        site_id = self._build_site_id()
        self._site_id_preview_var.set(f"→  {site_id}" if site_id else "")

    def _campaign_id_row(self, parent):
        """
        Campaign ID row: [ YYYYMMDD ] C [ ## ] (sequence number)
        Date auto-filled from HDR.
        """
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=16, pady=4)

        tk.Label(row, text="Campaign ID", bg=BG, fg=FG, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")

        # Date — read-only, auto-filled from HDR
        self._camp_date_var = tk.StringVar(value="YYYYMMDD")
        tk.Entry(row, textvariable=self._camp_date_var,
                 bg=BG_READONLY, fg=FG_AUTO,
                 font=FONT, relief="flat",
                 highlightthickness=1, highlightbackground="#555",
                 state="readonly", width=10).pack(side="left", ipady=4, padx=(0, 2))

        tk.Label(row, text="C", bg=BG, fg=FG_AUTO,
                 font=FONT_BOLD).pack(side="left", padx=2)

        tk.Entry(row, textvariable=self._camp_seq_var,
                 bg=BG_ENTRY, fg=FG, font=FONT, relief="flat",
                 insertbackground=FG,
                 highlightthickness=1, highlightbackground="#555",
                 width=4).pack(side="left", ipady=4, padx=(2, 8))

        tk.Label(row, text="(sequence number)", bg=BG, fg=FG_DIM,
                 font=("Helvetica", 10)).pack(side="left")

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
        ttk.Combobox(row, textvariable=var, values=options,
                     state="readonly", font=FONT, width=16).pack(side="left", ipady=3)

    # ── Site ID assembly ───────────────────────────────────────────────────────

    def _build_site_id(self) -> str:
        site_type = self._site_type_var.get().strip().upper()
        location  = self._site_loc_var.get().strip().upper()
        number    = self._site_num_var.get().strip().zfill(2)
        if site_type and location and number:
            return f"{site_type}_{location}{number}"
        return ""

    # ── HDR auto-read on browse ────────────────────────────────────────────────

    def _on_source_browsed(self, folder: str):
        try:
            from utils.meta import parse_hdr
            hdr_files = sorted(Path(folder).glob("*.hdr"))
            if not hdr_files:
                return
            hdr_meta = parse_hdr(hdr_files[0])
            if hdr_meta.acquisition_date:
                date_str = hdr_meta.acquisition_date.replace("-", "")
                self._hdr_date = date_str
                self._camp_date_var.set(date_str)
                self._append_log("INFO", f"HDR date detected: {date_str}")
        except Exception as e:
            self._append_log("WARNING", f"Could not read HDR date: {e}")

    # ── Campaign ID assembly ───────────────────────────────────────────────────

    def _build_campaign_id(self) -> str:
        date = self._hdr_date or self._camp_date_var.get()
        seq  = self._camp_seq_var.get().strip().zfill(2) or "01"
        return f"{date}C{seq}"

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate(self) -> list:
        errors = []
        if not self._source_var.get().strip():
            errors.append("Raw files folder is required.")
        elif not Path(self._source_var.get()).exists():
            errors.append("Raw files folder does not exist.")
        if not self._data_root_var.get().strip():
            errors.append("Data root folder is required.")
        if not self._hdr_date:
            errors.append("Could not detect date from HDR. Check the raw files folder.")
        if not self._camp_seq_var.get().strip().isdigit():
            errors.append("Campaign sequence number must be a number e.g. 01.")

        # Site ID validation
        # loc = self._site_loc_var.get().strip()
        num = self._site_num_var.get().strip()
        # if not loc:
        #     errors.append("Site location is required e.g. AAR.")
        # elif not loc.isalpha() or len(loc) != 3:
        #     errors.append("Site location must be exactly 3 letters e.g. AAR.")
        if not num.isdigit():
            errors.append("Site number must be a number e.g. 01.")

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
            "site_id":        self._build_site_id(),
            "campaign_id":    self._build_campaign_id(),
            "platform":       self._platform_var.get(),
            "data_type":      self._datatype_var.get(),
            "operator":       self._operator_var.get().strip(),
            "target_gas":     self._target_gas_var.get(),
            # "time_end":       self._time_end_var.get().strip() or None,
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

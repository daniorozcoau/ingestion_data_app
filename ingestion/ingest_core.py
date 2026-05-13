"""
ingestion/ingest_core.py
GHG-MONITOR — Core ingestion logic.

Contains the pure ingestion logic with no dependency on argparse or loguru.
Used by both:
  - ingestion/00_ingest (CLI)
  - app/ingest_app.py       (desktop UI)

The log_callback parameter accepts any callable(level: str, message: str)
so callers can route log output wherever they need (terminal, UI, file, etc.)
"""

import hashlib
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.dmp import build_filename
from utils.meta import parse_hdr, campaign_meta_from_hdr, write_campaign_meta


# ── Checksum ───────────────────────────────────────────────────────────────────

def md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


# ── File discovery ─────────────────────────────────────────────────────────────

def discover_captures(source_folder: Path, log: Callable) -> list:
    """
    Scan source folder and group files into capture sets.
    Each set: {hdr, data, bmp, log}
    """
    hdr_files = sorted(source_folder.glob("*.hdr"))

    if not hdr_files:
        raise ValueError(f"No .hdr files found in: {source_folder}")

    captures = []
    for hdr in hdr_files:
        stem    = hdr.stem
        capture = {"hdr": hdr, "data": None, "bmp": None, "log": None}

        for ext in (".img", ".hyspex"):
            candidate = hdr.with_suffix(ext)
            if candidate.exists():
                capture["data"] = candidate
                break

        if capture["data"] is None:
            log("WARNING", f"No .img or .hyspex found for {hdr.name} — skipping")
            continue

        bmp = source_folder / (stem + ".BMP")
        lg  = source_folder / (stem + ".log")
        if bmp.exists(): capture["bmp"] = bmp
        if lg.exists():  capture["log"] = lg

        captures.append(capture)

    if not captures:
        raise ValueError(f"No complete capture sets found in: {source_folder}")

    return captures


# ── Campaign ID helpers ────────────────────────────────────────────────────────

def infer_campaign_date(hdr_path: Path) -> str:
    try:
        hdr_meta = parse_hdr(hdr_path)
        if hdr_meta.acquisition_date:
            return hdr_meta.acquisition_date.replace("-", "")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def next_campaign_number(site_campaigns_dir: Path, date_str: str) -> str:
    existing = [
        d.name for d in site_campaigns_dir.iterdir()
        if d.is_dir() and d.name.startswith(date_str + "C")
    ] if site_campaigns_dir.exists() else []

    if not existing:
        return "01"

    numbers = []
    for name in existing:
        m = re.search(r"C(\d{2})$", name)
        if m:
            numbers.append(int(m.group(1)))

    return str(max(numbers) + 1).zfill(2)


# ── Core ───────────────────────────────────────────────────────────────────────

def run_ingestion(params: dict, log_callback: Callable) -> None:
    """
    Run the full ingestion pipeline.

    Args:
        params:       Dict of ingestion parameters (mirrors CLI args).
                      Key params:
                        - data_type: "raw" or "hyrad" — which subfolder to copy into
                        - platform:  "GND" or "AIR"   — goes into the DMP filename only
        log_callback: callable(level: str, message: str) for routing log output.

    Raises:
        SystemExit on unrecoverable errors.
    """
    log = log_callback

    source_folder = Path(params["source_folder"]).resolve()
    data_root     = Path(params["data_root"]).resolve()

    if not source_folder.exists():
        log("ERROR", f"Source folder does not exist: {source_folder}")
        raise SystemExit(1)

    # ── Discover captures ──────────────────────────────────────────────────
    log("INFO", f"Scanning: {source_folder}")
    captures = discover_captures(source_folder, log)
    log("INFO", f"Found {len(captures)} capture set(s)")

    # ── Parse HDR ─────────────────────────────────────────────────────────
    first_hdr = captures[0]["hdr"]
    hdr_meta  = parse_hdr(first_hdr)

    # ── Campaign ID ───────────────────────────────────────────────────────
    date_str           = infer_campaign_date(first_hdr)
    site_id            = params["site_id"]
    site_campaigns_dir = data_root / "sites" / site_id / "campaigns"

    campaign_id = params.get("campaign_id") or \
                  f"{date_str}C{next_campaign_number(site_campaigns_dir, date_str)}"

    log("INFO", f"Campaign ID : {campaign_id}")
    log("INFO", f"Site ID     : {site_id}")

    # ── Folder structure ───────────────────────────────────────────────────
    # data_type determines which subfolder files are copied into:
    #   "raw"   → campaign_dir/raw/
    #   "hyrad" → campaign_dir/hyrad/
    # platform (GND/AIR) is only used in the DMP filename, not the folder.

    platform  = params.get("platform", "GND")
    data_type = params.get("data_type", "raw")  # "raw" or "hyrad"

    if data_type not in ("raw", "hyrad"):
        log("ERROR", f"Invalid data_type '{data_type}'. Must be 'raw' or 'hyrad'.")
        raise SystemExit(1)

    campaign_dir = site_campaigns_dir / campaign_id

    # Create full campaign structure
    (campaign_dir / "raw").mkdir(parents=True, exist_ok=True)
    (campaign_dir / "hyrad").mkdir(parents=True, exist_ok=True)
    (campaign_dir / "logs").mkdir(parents=True, exist_ok=True)

    destination_dir = campaign_dir / data_type

    log("INFO", f"Data type   : {data_type}")
    log("INFO", f"Destination : {destination_dir}")

    # ── Sensor info ───────────────────────────────────────────────────────
    sensor_code = hdr_meta.sensor_code or params.get("sensor")
    serial_num  = hdr_meta.serial_number_dmp or params.get("serial_number")

    if not sensor_code:
        log("ERROR", "Could not determine sensor code from HDR. Check the HDR file.")
        raise SystemExit(1)
    if not serial_num:
        log("ERROR", "Could not determine serial number from HDR. Check the HDR file.")
        raise SystemExit(1)

    log("INFO", f"Sensor      : {sensor_code}")
    log("INFO", f"Serial      : {serial_num}")

    # ── Copy and rename ───────────────────────────────────────────────────
    for seq_idx, capture in enumerate(captures, start=1):
        seq           = str(seq_idx).zfill(3)
        original_stem = capture["hdr"].stem
        log("INFO", f"--- Sequence {seq}: {original_stem}")

        files_to_copy = [
            (capture["hdr"],  ".hdr"),
            (capture["data"], capture["data"].suffix),
        ]
        if capture["bmp"]: files_to_copy.append((capture["bmp"], ".BMP"))
        if capture["log"]: files_to_copy.append((capture["log"], ".log"))

        for src_path, ext in files_to_copy:
            dmp_name = build_filename(
                site_id=site_id,
                campaign_id=campaign_id,
                platform=platform,
                sensor=sensor_code,
                serial_number=serial_num,
                sequence=seq_idx,
                level="L0",
                extension=ext,
            )
            dst_path = destination_dir / dmp_name

            shutil.copy2(src_path, dst_path)

            src_md5 = md5(src_path)
            dst_md5 = md5(dst_path)

            if src_md5 != dst_md5:
                log("ERROR", f"CHECKSUM MISMATCH: {dmp_name} — ingestion aborted")
                raise SystemExit(1)

            size_mb = round(src_path.stat().st_size / 1024 / 1024, 2)
            log("INFO", f"  ✓ {dmp_name}  ({size_mb} MB)  md5:{src_md5}")

    # ── campaign_meta.yaml ────────────────────────────────────────────────
    meta_path = campaign_dir / "campaign_meta.yaml"

    if meta_path.exists() and not params.get("overwrite_meta", False):
        log("INFO", "campaign_meta.yaml already exists — skipping")
    else:
        camp_meta                   = campaign_meta_from_hdr(hdr_meta)
        camp_meta.campaign_id       = campaign_id
        camp_meta.site_id           = site_id
        camp_meta.operator          = params.get("operator", "")
        camp_meta.platform          = platform
        camp_meta.target_gas        = params.get("target_gas", "")
        camp_meta.notes             = params.get("notes", "")
        camp_meta.original_filename = captures[0]["hdr"].stem

        write_campaign_meta(camp_meta, meta_path)
        log("INFO", f"campaign_meta.yaml written: {meta_path}")

    log("SUCCESS", f"Campaign folder : {campaign_dir}")
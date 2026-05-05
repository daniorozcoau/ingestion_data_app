"""
utils/meta.py
GHG-MONITOR — Metadata utilities.

Handles three things:
  1. Parsing camera HDR files to extract embedded sensor metadata
  2. Reading and writing campaign_meta.yaml
  3. Reading site_info.yaml

The HDR parser covers the ENVI format produced by the HySpex Mjolnir S-620.

Requires:
    pip install pyyaml
"""

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union, List


# ── Sensor code lookup (from DMP Section 9) ───────────────────────────────────

_SERIAL_TO_SENSOR_CODE = {
    "Mjolnir_S620": "MJL",
    "Mjolnir_S620_SWIR": "MJS",
}

_SERIAL_PREFIX = "S620"  # used to build the full SN segment e.g. S620SN7149


# ── HDR parsing ───────────────────────────────────────────────────────────────

@dataclass
class HDRMetadata:
    """
    Sensor metadata extracted directly from a camera-generated HDR file.
    All fields that can be read automatically from the HDR are populated here.
    Fields the HDR does not contain are left as None.
    """
    # From HDR top-level fields
    acquisition_date: Optional[str] = None
    acquisition_time: Optional[str] = None
    samples: Optional[int] = None
    lines: Optional[int] = None
    bands: Optional[int] = None
    interleave: Optional[str] = None
    data_type: Optional[int] = None
    byte_order: Optional[int] = None
    header_offset: Optional[int] = None
    wavelength_units: Optional[str] = None
    wavelengths: List[float] = field(default_factory=list)
    wavelength_min_nm: Optional[float] = None
    wavelength_max_nm: Optional[float] = None

    # From HDR description block
    integration_time_us: Optional[int] = None
    frame_period_us: Optional[int] = None
    binning: Optional[int] = None
    num_frames: Optional[int] = None
    num_background: Optional[int] = None
    aperture_size: Optional[float] = None
    pixelsize_x: Optional[float] = None
    pixelsize_y: Optional[float] = None
    camera_config: Optional[str] = None
    sensor_id: Optional[str] = None
    serial_number_raw: Optional[str] = None
    scanning_mode: Optional[str] = None

    # Derived / DMP-mapped
    sensor_code: Optional[str] = None
    serial_number_dmp: Optional[str] = None


def parse_hdr(hdr_path: Union[str, Path]) -> HDRMetadata:
    """
    Parse a HySpex Mjolnir HDR file and return an HDRMetadata object.

    Args:
        hdr_path: Path to the .hdr file.

    Returns:
        HDRMetadata populated with all fields found in the file.

    Raises:
        FileNotFoundError if the file does not exist.
        ValueError if the file does not look like an ENVI HDR.
    """
    hdr_path = Path(hdr_path)
    if not hdr_path.exists():
        raise FileNotFoundError(f"HDR file not found: {hdr_path}")

    text = hdr_path.read_text(encoding="utf-8", errors="replace")

    if not text.strip().startswith("ENVI"):
        raise ValueError(f"File does not appear to be an ENVI HDR: {hdr_path}")

    meta = HDRMetadata()

    # ── Top-level key = value fields ──────────────────────────────────────────
    def _get(pattern):
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    meta.acquisition_date = _get(r"^acquisition date\s*=\s*(.+)$")
    meta.acquisition_time = _get(r"^acquisition start time\s*=\s*(.+)$")
    meta.interleave        = _get(r"^interleave\s*=\s*(.+)$")
    meta.wavelength_units  = _get(r"^wavelength units\s*=\s*(.+)$")

    for attr, pattern in [
        ("samples",       r"^samples\s*=\s*(\d+)$"),
        ("lines",         r"^lines\s*=\s*(\d+)$"),
        ("bands",         r"^bands\s*=\s*(\d+)$"),
        ("data_type",     r"^data type\s*=\s*(\d+)$"),
        ("byte_order",    r"^byte order\s*=\s*(\d+)$"),
        ("header_offset", r"^header offset\s*=\s*(\d+)$"),
    ]:
        val = _get(pattern)
        if val is not None:
            setattr(meta, attr, int(val))

    # ── Wavelength array ──────────────────────────────────────────────────────
    wl_match = re.search(r"wavelength\s*=\s*\{([^}]+)\}", text, re.DOTALL | re.IGNORECASE)
    if wl_match:
        meta.wavelengths = [float(w.strip()) for w in wl_match.group(1).split(",") if w.strip()]
        if meta.wavelengths:
            meta.wavelength_min_nm = round(min(meta.wavelengths), 2)
            meta.wavelength_max_nm = round(max(meta.wavelengths), 2)

    # ── Description block ─────────────────────────────────────────────────────
    desc_match = re.search(r"description\s*=\s*\{([^}]+)\}", text, re.DOTALL | re.IGNORECASE)
    if desc_match:
        desc = desc_match.group(1)

        def _desc_get(pattern):
            m = re.search(pattern, desc, re.IGNORECASE)
            return m.group(1).strip() if m else None

        integration  = _desc_get(r"Integration time\s*=\s*(\d+)")
        frame_period = _desc_get(r"Frameperiod\s*=\s*(\d+)")
        binning      = _desc_get(r"Binning\s*=\s*(\d+)")
        num_frames   = _desc_get(r"Number of frames\s*=\s*(\d+)")
        num_bg       = _desc_get(r"Number of background\s*=\s*(\d+)")
        aperture     = _desc_get(r"Aperture size\s*=\s*([\d.]+)")
        px_x         = _desc_get(r"Pixelsize x\s*=\s*([\d.]+)")
        px_y         = _desc_get(r"Pixelsize y\s*=\s*([\d.]+)")

        if integration:  meta.integration_time_us = int(integration)
        if frame_period: meta.frame_period_us = int(frame_period)
        if binning:      meta.binning = int(binning)
        if num_frames:   meta.num_frames = int(num_frames)
        if num_bg:       meta.num_background = int(num_bg)
        if aperture:     meta.aperture_size = float(aperture)
        if px_x:         meta.pixelsize_x = float(px_x)
        if px_y:         meta.pixelsize_y = float(px_y)

        meta.camera_config     = _desc_get(r"Camera configuration[^=]*=\s*(.+)")
        meta.sensor_id         = _desc_get(r"ID\s*=\s*(.+)")
        meta.serial_number_raw = _desc_get(r"Serialnumber\s*=\s*(\d+)")
        meta.scanning_mode     = _desc_get(r"Scanningmode\s*=\s*(.+)")

    # ── Derive DMP fields ─────────────────────────────────────────────────────
    if meta.sensor_id:
        for key, code in _SERIAL_TO_SENSOR_CODE.items():
            if key in meta.sensor_id:
                meta.sensor_code = code
                break

    if meta.serial_number_raw:
        meta.serial_number_dmp = f"{_SERIAL_PREFIX}SN{meta.serial_number_raw}"

    return meta


# ── campaign_meta.yaml ────────────────────────────────────────────────────────

@dataclass
class CampaignMeta:
    """All fields in a campaign_meta.yaml file."""
    # Operator-provided
    campaign_id: str = ""
    site_id: str = ""
    operator: str = ""
    platform: str = ""
    target_gas: str = ""
    white_ref_acquired: str = ""
    dark_ref_acquired: str = ""
    gps_log: str = ""
    notes: str = ""

    # Auto-populated from HDR
    date_utc: str = ""
    time_start_utc: str = ""
    time_end_utc: str = ""
    sensor: str = ""
    serial_number: str = ""
    integration_time_ms: str = ""
    bands: str = ""
    wavelength_range_nm: str = ""
    interleave: str = ""
    samples: str = ""
    lines: str = ""
    camera_config: str = ""
    scanning_mode: str = ""
    binning: str = ""

    # Drone-only (~ for ground campaigns)
    aircraft_type: str = "~"
    flight_altitude_m: str = "~"
    flight_speed_ms: str = "~"

    # Weather
    weather: str = "~"

    # Pipeline bookkeeping
    original_filename: str = ""


def campaign_meta_from_hdr(hdr_meta: HDRMetadata) -> CampaignMeta:
    """
    Build a partially-populated CampaignMeta from parsed HDR metadata.
    Operator-required fields are left empty for the ingestion script to fill.
    """
    meta = CampaignMeta()

    meta.date_utc       = hdr_meta.acquisition_date or ""
    meta.time_start_utc = hdr_meta.acquisition_time or ""
    meta.sensor         = hdr_meta.sensor_id or ""
    meta.serial_number  = hdr_meta.serial_number_dmp or ""
    meta.interleave     = hdr_meta.interleave or ""
    meta.scanning_mode  = hdr_meta.scanning_mode or ""
    meta.camera_config  = hdr_meta.camera_config or ""

    if hdr_meta.integration_time_us is not None:
        meta.integration_time_ms = str(round(hdr_meta.integration_time_us / 1000, 3))
    if hdr_meta.bands is not None:
        meta.bands = str(hdr_meta.bands)
    if hdr_meta.samples is not None:
        meta.samples = str(hdr_meta.samples)
    if hdr_meta.lines is not None:
        meta.lines = str(hdr_meta.lines)
    if hdr_meta.binning is not None:
        meta.binning = str(hdr_meta.binning)
    if hdr_meta.wavelength_min_nm and hdr_meta.wavelength_max_nm:
        meta.wavelength_range_nm = f"{hdr_meta.wavelength_min_nm} - {hdr_meta.wavelength_max_nm}"

    return meta


def write_campaign_meta(meta: CampaignMeta, output_path: Union[str, Path]) -> None:
    """
    Write a CampaignMeta to a campaign_meta.yaml file.

    Args:
        meta:        CampaignMeta dataclass.
        output_path: Path where campaign_meta.yaml will be written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "identifiers": {
            "campaign_id": meta.campaign_id,
            "site_id":     meta.site_id,
        },
        "acquisition": {
            "date_utc":       meta.date_utc,
            "time_start_utc": meta.time_start_utc,
            "time_end_utc":   meta.time_end_utc,
            "operator":       meta.operator,
            "platform":       meta.platform,
            "target_gas":     meta.target_gas,
        },
        "sensor": {
            "sensor":              meta.sensor,
            "serial_number":       meta.serial_number,
            "integration_time_ms": meta.integration_time_ms,
            "bands":               meta.bands,
            "wavelength_range_nm": meta.wavelength_range_nm,
            "interleave":          meta.interleave,
            "samples":             meta.samples,
            "lines":               meta.lines,
            "binning":             meta.binning,
            "camera_config":       meta.camera_config,
            "scanning_mode":       meta.scanning_mode,
        },
        "references": {
            "white_ref_acquired": meta.white_ref_acquired,
            "dark_ref_acquired":  meta.dark_ref_acquired,
            "gps_log":            meta.gps_log,
        },
        "drone": {
            "aircraft_type":     meta.aircraft_type,
            "flight_altitude_m": meta.flight_altitude_m,
            "flight_speed_ms":   meta.flight_speed_ms,
        },
        "weather": meta.weather,
        "pipeline": {
            "original_filename": meta.original_filename,
        },
        "notes": meta.notes,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def read_campaign_meta(meta_path: Union[str, Path]) -> CampaignMeta:
    """
    Read a campaign_meta.yaml file into a CampaignMeta dataclass.

    Args:
        meta_path: Path to campaign_meta.yaml.

    Returns:
        CampaignMeta populated from the file.

    Raises:
        FileNotFoundError if the file does not exist.
    """
    meta_path = Path(meta_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"campaign_meta.yaml not found: {meta_path}")

    with open(meta_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    meta = CampaignMeta()

    meta.campaign_id         = data.get("identifiers", {}).get("campaign_id", "")
    meta.site_id             = data.get("identifiers", {}).get("site_id", "")

    acq = data.get("acquisition", {})
    meta.date_utc            = acq.get("date_utc", "")
    meta.time_start_utc      = acq.get("time_start_utc", "")
    meta.time_end_utc        = acq.get("time_end_utc", "")
    meta.operator            = acq.get("operator", "")
    meta.platform            = acq.get("platform", "")
    meta.target_gas          = acq.get("target_gas", "")

    sen = data.get("sensor", {})
    meta.sensor              = sen.get("sensor", "")
    meta.serial_number       = sen.get("serial_number", "")
    meta.integration_time_ms = sen.get("integration_time_ms", "")
    meta.bands               = sen.get("bands", "")
    meta.wavelength_range_nm = sen.get("wavelength_range_nm", "")
    meta.interleave          = sen.get("interleave", "")
    meta.samples             = sen.get("samples", "")
    meta.lines               = sen.get("lines", "")
    meta.binning             = sen.get("binning", "")
    meta.camera_config       = sen.get("camera_config", "")
    meta.scanning_mode       = sen.get("scanning_mode", "")

    ref = data.get("references", {})
    meta.white_ref_acquired  = ref.get("white_ref_acquired", "")
    meta.dark_ref_acquired   = ref.get("dark_ref_acquired", "")
    meta.gps_log             = ref.get("gps_log", "")

    drone = data.get("drone", {})
    meta.aircraft_type       = drone.get("aircraft_type", "~")
    meta.flight_altitude_m   = drone.get("flight_altitude_m", "~")
    meta.flight_speed_ms     = drone.get("flight_speed_ms", "~")

    meta.weather             = data.get("weather", "~")
    meta.original_filename   = data.get("pipeline", {}).get("original_filename", "")
    meta.notes               = data.get("notes", "")

    return meta


# ── site_info.yaml ────────────────────────────────────────────────────────────

@dataclass
class SiteInfo:
    site_id: str = ""
    site_type: str = ""
    full_name: str = ""
    country: str = ""
    latitude: str = ""
    longitude: str = ""
    elevation_m: str = ""
    target_gases: str = ""
    site_contact: str = ""
    notes: str = ""


def read_site_info(site_info_path: Union[str, Path]) -> SiteInfo:
    """
    Read a site_info.yaml file into a SiteInfo dataclass.

    Args:
        site_info_path: Path to site_info.yaml.

    Returns:
        SiteInfo populated from the file.
    """
    site_info_path = Path(site_info_path)
    if not site_info_path.exists():
        raise FileNotFoundError(f"site_info.yaml not found: {site_info_path}")

    with open(site_info_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    info = SiteInfo()
    info.site_id      = data.get("site_id", "")
    info.site_type    = data.get("site_type", "")
    info.full_name    = data.get("full_name", "")
    info.country      = data.get("country", "")
    info.latitude     = str(data.get("latitude", ""))
    info.longitude    = str(data.get("longitude", ""))
    info.elevation_m  = str(data.get("elevation_m", ""))
    info.target_gases = data.get("target_gases", "")
    info.site_contact = data.get("site_contact", "")
    info.notes        = data.get("notes", "")

    return info


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="GHG-MONITOR | Parse a HySpex HDR file and generate a campaign_meta.yaml"
    )
    parser.add_argument(
        "hdr",
        type=Path,
        help="Path to the camera-generated .hdr file"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Where to write the campaign_meta.yaml (default: same folder as the HDR file)"
    )
    parser.add_argument("--campaign-id",  default="",    help="e.g. 20260422C01")
    parser.add_argument("--site-id",      default="",    help="e.g. LAB_AAR01")
    parser.add_argument("--operator",     default="",    help="Your name")
    parser.add_argument("--platform",     default="GND", help="AIR or GND (default: GND)")
    parser.add_argument("--target-gas",   default="",    help="e.g. CH4")
    parser.add_argument("--time-end",     default="~",   help="End time UTC e.g. 08:10:00")
    parser.add_argument("--white-ref",    default="no",  help="yes or no (default: no)")
    parser.add_argument("--dark-ref",     default="no",  help="yes or no (default: no)")
    parser.add_argument("--gps-log",      default="no",  help="yes or no (default: no)")
    parser.add_argument("--notes",        default="",    help="Free text notes")

    args = parser.parse_args()

    # Parse HDR
    print(f"\nParsing HDR: {args.hdr}")
    hdr_meta = parse_hdr(args.hdr)

    # Resolve output path — default to same folder as the HDR
    output_path = args.output if args.output else args.hdr.parent / "campaign_meta.yaml"

    # Build campaign_meta from HDR
    camp_meta = campaign_meta_from_hdr(hdr_meta)

    # Fill operator fields
    camp_meta.campaign_id        = args.campaign_id
    camp_meta.site_id            = args.site_id
    camp_meta.operator           = args.operator
    camp_meta.platform           = args.platform
    camp_meta.target_gas         = args.target_gas
    camp_meta.time_end_utc       = args.time_end
    camp_meta.white_ref_acquired = args.white_ref
    camp_meta.dark_ref_acquired  = args.dark_ref
    camp_meta.gps_log            = args.gps_log
    camp_meta.notes              = args.notes
    camp_meta.original_filename  = args.hdr.stem

    # Write the file
    write_campaign_meta(camp_meta, output_path)
    print(f"\ncampaign_meta.yaml written to: {output_path.resolve()}")
    print("\n── Output ────────────────────────────────────────────\n")
    print(output_path.read_text())

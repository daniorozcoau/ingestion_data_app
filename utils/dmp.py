"""
utils/dmp.py
GHG-MONITOR Data Management Protocol v1.0
Filename generator, parser, and validator.
"""

import re
from dataclasses import dataclass
from typing import Optional, List

# ── Valid values from DMP ──────────────────────────────────────────────────────

SITE_TYPE_CODES = {"WET", "BIO", "OIL", "AGR", "URB", "LAB"}

SENSOR_CODES = {"MJL", "MJS"}

PLATFORMS = {"AIR", "GND"}

PROCESSING_LEVELS = {"L0", "L1", "L2", "L3"}

VALID_EXTENSIONS = {".img", ".hdr", ".BMP", ".log", ".hyspex"}

# Regex patterns for individual segments
_SITE_ID_RE = re.compile(r"^([A-Z]{3})_([A-Z]{3})(\d{2})$")          # e.g. WET_AAR01
_CAMPAIGN_ID_RE = re.compile(r"^(\d{8})C(\d{2})$")                    # e.g. 20260430C01
_SN_RE = re.compile(r"^S\d+SN\d+$")                                   # e.g. S620SN7149
_SEQ_RE = re.compile(r"^\d{3}$")                                       # e.g. 001


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DMPFilename:
    """Represents a fully parsed DMP-compliant filename."""
    site_id: str          # e.g. WET_AAR01
    campaign_id: str      # e.g. 20260430C01
    platform: str         # AIR or GND
    sensor: str           # e.g. MJL
    serial_number: str    # e.g. S620SN7149
    sequence: str         # e.g. 001
    level: str            # L0, L1, L2, L3
    suffix: Optional[str] # optional, e.g. wref, dref, rad_bsq
    extension: str        # e.g. .img


# ── Core functions ─────────────────────────────────────────────────────────────

def build_filename(
    site_id: str,
    campaign_id: str,
    platform: str,
    sensor: str,
    serial_number: str,
    sequence: int,
    level: str,
    extension: str,
    suffix: Optional[str] = None,
) -> str:
    """
    Generate a DMP-compliant filename.

    Args:
        site_id:       e.g. "WET_AAR01"
        campaign_id:   e.g. "20260430C01"
        platform:      "AIR" or "GND"
        sensor:        e.g. "MJL"
        serial_number: e.g. "S620SN7149"
        sequence:      integer, will be zero-padded to 3 digits
        level:         "L0", "L1", "L2", or "L3"
        extension:     e.g. ".img" or ".hdr"
        suffix:        optional extra tag, e.g. "wref" or "rad_bsq"

    Returns:
        Compliant filename string.

    Raises:
        ValueError if any segment is invalid.
    """
    # Validate
    errors = _validate_segments(
        site_id, campaign_id, platform, sensor, serial_number,
        str(sequence).zfill(3), level, extension
    )
    if errors:
        raise ValueError("Invalid DMP segments:\n" + "\n".join(f"  - {e}" for e in errors))

    seq_str = str(sequence).zfill(3)
    ext = extension if extension.startswith(".") else f".{extension}"

    parts = [site_id, campaign_id, platform, sensor, serial_number, seq_str, level]
    if suffix:
        parts.append(suffix)

    return "_".join(parts) + ext


def parse_filename(filename: str) -> DMPFilename:
    """
    Parse a DMP-compliant filename into its components.

    Args:
        filename: e.g. "WET_AAR01_20260430C01_GND_MJL_S620SN7149_001_L0.img"

    Returns:
        DMPFilename dataclass.

    Raises:
        ValueError if the filename cannot be parsed.
    """
    # Strip extension
    ext_match = re.search(r"\.(img|hdr|BMP|log|hyspex)$", filename)
    if not ext_match:
        raise ValueError(f"Unrecognised or missing extension in: '{filename}'")

    extension = "." + ext_match.group(1)
    base = filename[: -len(extension)]

    parts = base.split("_")

    # site_id is always the first two segments joined: e.g. WET + AAR01
    if len(parts) < 9:
        raise ValueError(
            f"Expected at least 9 underscore-separated segments (including site_id parts), "
            f"got {len(parts)} in: '{filename}'"
        )

    site_id = f"{parts[0]}_{parts[1]}{parts[2]}"   # TYPE_LOC## (3 parts)
    campaign_id = parts[3]
    platform = parts[4]
    sensor = parts[5]
    serial_number = parts[6]
    sequence = parts[7]
    level = parts[8]
    suffix = "_".join(parts[9:]) if len(parts) > 9 else None

    errors = _validate_segments(
        site_id, campaign_id, platform, sensor, serial_number, sequence, level, extension
    )
    if errors:
        raise ValueError(
            f"Filename '{filename}' has invalid segments:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    return DMPFilename(
        site_id=site_id,
        campaign_id=campaign_id,
        platform=platform,
        sensor=sensor,
        serial_number=serial_number,
        sequence=sequence,
        level=level,
        suffix=suffix,
        extension=extension,
    )


def validate_filename(filename: str) -> List[str]:
    """
    Validate a filename against DMP v1.0.

    Returns:
        List of error strings. Empty list means the filename is valid.
    """
    try:
        parse_filename(filename)
        return []
    except ValueError as e:
        return [str(e)]


# ── Internal validation ────────────────────────────────────────────────────────

def _validate_segments(
    site_id: str,
    campaign_id: str,
    platform: str,
    sensor: str,
    serial_number: str,
    sequence: str,
    level: str,
    extension: str,
) -> List[str]:
    errors = []

    if not _SITE_ID_RE.match(site_id):
        errors.append(f"site_id '{site_id}' must match <TYPE>_<LOC3><##> e.g. WET_AAR01")
    else:
        type_code = site_id.split("_")[0]
        if type_code not in SITE_TYPE_CODES:
            errors.append(f"site type '{type_code}' not in {SITE_TYPE_CODES}")

    if not _CAMPAIGN_ID_RE.match(campaign_id):
        errors.append(f"campaign_id '{campaign_id}' must match YYYYMMDDCNN e.g. 20260430C01")

    if platform not in PLATFORMS:
        errors.append(f"platform '{platform}' must be one of {PLATFORMS}")

    if sensor not in SENSOR_CODES:
        errors.append(f"sensor '{sensor}' not in {SENSOR_CODES}")

    if not _SN_RE.match(serial_number):
        errors.append(f"serial_number '{serial_number}' must match S<model>SN<number> e.g. S620SN7149")

    if not _SEQ_RE.match(sequence):
        errors.append(f"sequence '{sequence}' must be 3 digits e.g. 001")

    if level not in PROCESSING_LEVELS:
        errors.append(f"level '{level}' must be one of {PROCESSING_LEVELS}")

    if extension not in VALID_EXTENSIONS:
        errors.append(f"extension '{extension}' must be one of {VALID_EXTENSIONS}")

    return errors


# ── Convenience helpers ────────────────────────────────────────────────────────

def build_filename_pair(
    site_id: str,
    campaign_id: str,
    platform: str,
    sensor: str,
    serial_number: str,
    sequence: int,
    level: str,
    suffix: Optional[str] = None,
) -> tuple:
    """Return the (.img, .hdr) filename pair for a given capture."""
    img = build_filename(site_id, campaign_id, platform, sensor,
                         serial_number, sequence, level, ".img", suffix)
    hdr = build_filename(site_id, campaign_id, platform, sensor,
                         serial_number, sequence, level, ".hdr", suffix)
    return img, hdr


def get_level(filename: str) -> str:
    """Extract the processing level from a filename."""
    return parse_filename(filename).level


def bump_level(filename: str, new_level: str) -> str:
    """
    Return a new filename with the processing level incremented.
    Useful for generating output filenames from input filenames.

    Example:
        bump_level("WET_AAR01_20260430C01_GND_MJL_S620SN7149_001_L0.img", "L1")
        → "WET_AAR01_20260430C01_GND_MJL_S620SN7149_001_L1.img"
    """
    parsed = parse_filename(filename)
    return build_filename(
        site_id=parsed.site_id,
        campaign_id=parsed.campaign_id,
        platform=parsed.platform,
        sensor=parsed.sensor,
        serial_number=parsed.serial_number,
        sequence=int(parsed.sequence),
        level=new_level,
        extension=parsed.extension,
        suffix=parsed.suffix,
    )
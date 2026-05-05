# Hyperspectral Data Ingestion App

Desktop application for ingesting raw hyperspectral data from the HySpex Mjolnir S-620 camera into the GHG-MONITOR data structure.

---

## What it does

- Copies raw camera files (`.hdr`, `.hyspex`) into the GHG-MONITOR folder structure
- Renames files according to the Data Management Protocol (DMP) naming convention
- Verifies file integrity with MD5 checksums
- Automatically generates a `campaign_meta.yaml` from the camera HDR file
- Logs all ingestion steps

---

## Download

Go to the [Releases](../../releases) page and download the latest version for your platform.

| Platform | File |
|----------|------|
| macOS    | `hyperspectral_data_ingestion_mac.zip` |
| Windows  | Coming soon |

---

## Installation & First Run (macOS)

1. Download `hyperspectral_data_ingestion_mac.zip` from the Releases page
2. Double-click the zip to extract it
3. Move `hyperspectral_data_ingestion.app` to your Applications folder (optional)
4. **First time only** — macOS will block the app because it is not signed by an Apple developer:
   - Right-click the `.app` → **Open**
   - Click **Open** in the dialog that appears
   - The app will open and from now on you can double-click it normally

---

## How to use

### Before your first experiment

Create a folder on your computer where all GHG-MONITOR data will be stored. This folder should be **outside** any code or project folders — for example:

```
/Users/yourname/Desktop/ghg-monitor-data
```

### Running an ingestion

1. Transfer the raw files from the camera to your computer (via WiFi, Ethernet, or SD card)
2. Open the app
3. Fill in the form:

| Field | Description |
|-------|-------------|
| **Raw files folder** | The folder containing the `.hdr` and `.hyspex` files from the camera |
| **Data root folder** | Your `ghg-monitor-data` folder |
| **Site ID** | The site identifier e.g. `LAB_AAR01` (see DMP) |
| **Campaign ID** | Leave empty — auto-generated from the HDR acquisition date |
| **Platform** | `GND` for tripod/ground, `AIR` for drone |
| **Operator name** | Your full name |
| **Target gas** | The gas being measured e.g. `CH4` |
| **End time (UTC)** | The time you finished the recording |
| **White reference** | Whether a white reference panel was captured |
| **Dark reference** | Whether a dark reference was captured |
| **GPS log** | Whether a GPS log is available |
| **Notes** | Any relevant observations about the experiment |

4. Click **▶ Run Ingestion**
5. The log output will show progress in real time
6. When complete you will see `=== Ingestion complete ===`

### Output

The app creates the following structure inside your data root folder:

```
ghg-monitor-data/
  sites/
    <SITE_ID>/
      campaigns/
        <CAMPAIGN_ID>/
          campaign_meta.yaml
          raw/
            hyrad/
              <DMP_compliant_filename>.hdr
              <DMP_compliant_filename>.hyspex
          logs/
            ingest_YYYYMMDD_HHMMSS.log
```

---

## Data Management Protocol

File naming and folder structure follow the **GHG-MONITOR Data Management Protocol v1.1**. Contact the project lead for a copy of the protocol document.

---

## Issues

If something goes wrong, check the log output in the app for error messages. For persistent issues, open a GitHub Issue in this repository and include the log output.

---

## For developers

See [`build/build_mac.sh`](build/build_mac.sh) for the Mac build script.

Requirements:
- Python 3.11 (Homebrew: `brew install python-tk@3.11`)
- `pip install pyyaml loguru pyinstaller`

To rebuild the app after changes:
```bash
source ghg-app-tk/bin/activate
bash build/build_mac.sh
```

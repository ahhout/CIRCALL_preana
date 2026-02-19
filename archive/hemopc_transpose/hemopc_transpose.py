#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hemopc_transpose.py

Transposes capture panel data from HemoPC file to cfDNA inventory.
Target columns are now in the 'patients&samples' worksheet.

IMPORTANT: This script preserves all original formatting, comments, colors,
and other Excel features by copying the original file and only updating
specific cell values using openpyxl.

Matches samples between HemoPC and cfDNA inventory using:
1. 5-digit sample code extracted from sample_id/ECHANTILLON

Classifies panels into three categories:
- igtcr: IgTCR panels
- fusion: MLL, Ph, ALK, MYC, Other fusions panels
- mutation: HemoPC version panels (numeric or V-prefixed)

Usage:
    python archive/hemopc_transpose/hemopc_transpose.py \
        --inventory cfDNA_inventaire_2025.xlsx \
        --listfile "archive/hemopc_transpose/Liste patients NGS_panel HemoPC.xlsx" \
        --out cfDNA_inventaire_2025_updated.xlsx
"""

import argparse
import re
import shutil
import unicodedata
from typing import Optional, Tuple, List, Dict

import pandas as pd
from openpyxl import load_workbook

SEPARATOR = ";"  # for concatenation of multiple panels/dates


# ---------- helpers ----------

def strip_accents(s: str) -> str:
    """Remove accents from a string."""
    if not isinstance(s, str):
        return s
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def norm_text(s, keep=None):
    """Normalize text: strip, remove accents, upper/lower case."""
    if pd.isna(s):
        return None
    s = str(s).strip()
    if s == "":
        return None
    s = strip_accents(s)
    s = s.upper() if keep is None else s.lower()
    return s


def first3_letters(s: str) -> Optional[str]:
    """Extract first 3 letters from a string (normalized)."""
    s = norm_text(s)
    if s is None:
        return None
    letters = re.findall(r"[A-Z]", s)
    if not letters:
        return None
    return "".join(letters)[:3]


def first_5_digits_anywhere(s: str) -> Optional[str]:
    """Extract first 5-digit sequence from a string."""
    if pd.isna(s):
        return None
    s = str(s)
    m = re.search(r"(\d{5})", s)
    return m.group(1) if m else None


def classify_panel(panel_raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Classify a panel string into category and normalized panel name.
    
    Returns:
        Tuple of (category, panel_name) where category is one of:
        - 'igtcr': IgTCR panels
        - 'fusion': MLL, Ph, ALK, MYC, Other fusions
        - 'mutation': HemoPC versions (numeric, V-prefixed, LAL)
        - None: unrecognized
    """
    if pd.isna(panel_raw):
        return None, None
    txt = str(panel_raw).strip()
    if txt == "" or txt.lower() == "na":
        return None, None
    txt_up = strip_accents(txt).upper()

    # IGTCR anywhere
    if "IGTCR" in txt_up or ("IG" in txt_up and "TCR" in txt_up):
        return "igtcr", txt

    # Fusion markers
    if (re.match(r"^\s*MLL", txt_up) or
        re.match(r"^\s*PH", txt_up) or
        re.match(r"^\s*ALK", txt_up) or
        re.match(r"^\s*MYC", txt_up) or
        re.search(r"FUSION", txt_up) or
        re.match(r"^\s*RNA", txt_up)):
        return "fusion", txt

    # Mutation panels: starts with digits (HemoPC version) or V/LAL
    m = re.match(r"^\s*(\d+)\b", txt_up)
    if m:
        return "mutation", f"hemoPCv{m.group(1)}"

    if re.match(r"^\s*V", txt_up):
        return "mutation", txt

    if re.match(r"^\s*LAL", txt_up):
        return "mutation", txt

    return None, None


def parse_date_safe(x):
    """Parse a date value safely, returning NaT on failure."""
    if pd.isna(x) or (isinstance(x, str) and x.strip() == ""):
        return pd.NaT
    try:
        return pd.to_datetime(x, errors="coerce", dayfirst=True)
    except Exception:
        return pd.NaT


def unique_preserve_order(seq: List[str]) -> List[str]:
    """Return unique items preserving first-seen order."""
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


# ---------- Column name mappings ----------
# HemoPC column names (as found in the file)
HEMO_COL_NOM = "Nom (vert quand données dispo sur DDE)"
HEMO_COL_ECHANTILLON = "ECHANTILLON"
HEMO_COL_ACIDE = "acide nucléique utilisé (ADN/ARN/lyse/dCNA…)"
HEMO_COL_STATUT = "capture à lancer / capture en cours / analyse technique en cours / analyse technique terminée/ analyse biologique en cours / rendu / terminé / échec / ne pas faire"
HEMO_COL_DATE = "Date de début de la série (fixée). \nEn rouge les séries qui doivent être rendues dans Rubih2 (ouverte le 17/10/2018)"
HEMO_COL_PANEL = "Version du design de capture utilisé (si rien n'est précisé, c'est HemoPC)"

# Status values that indicate failure (skip these)
FAILURE_STATUSES = {"echec", "échec", "ne pas faire"}

# Target columns in inventory (patients&samples sheet)
TARGET_COLS = [
    "igtcr_capture_status", "igtcr_capture_date", "igtcr_capture_panel",
    "fusion_capture_status", "fusion_capture_date", "fusion_capture_panel",
    "mutation_capture_status", "mutation_capture_date", "mutation_capture_panel",
]


def get_column_index(ws, col_name: str) -> Optional[int]:
    """Find column index (1-based) by header name in first row."""
    for col_idx, cell in enumerate(ws[1], start=1):
        if cell.value == col_name:
            return col_idx
    return None


def build_header_map(ws) -> Dict[str, int]:
    """Build a mapping from column name to column index (1-based)."""
    header_map = {}
    for col_idx, cell in enumerate(ws[1], start=1):
        if cell.value:
            header_map[cell.value] = col_idx
    return header_map


# ---------- core ----------

def main(args):
    inventory_path = args.inventory
    listfile_path = args.listfile
    out_path = args.out

    SHEET_PAT_SAMP = "patients&samples"
    SHEET_LIST = "liste patients-HOG"

    print(f"[INFO] Loading inventory: {inventory_path}")
    print(f"[INFO] Loading HemoPC list: {listfile_path}")

    # Step 1: Copy the original file to preserve ALL formatting
    print(f"[INFO] Copying original file to preserve formatting...")
    shutil.copy2(inventory_path, out_path)

    # Step 2: Load the copied workbook with openpyxl (preserves formatting)
    wb = load_workbook(out_path)
    
    if SHEET_PAT_SAMP not in wb.sheetnames:
        raise ValueError(f"Required sheet '{SHEET_PAT_SAMP}' missing in inventory workbook.")

    ws = wb[SHEET_PAT_SAMP]

    # Build header map for the target sheet
    header_map = build_header_map(ws)
    
    # Check required columns exist
    required_cols = ["sample_id"] + TARGET_COLS
    missing_cols = [c for c in required_cols if c not in header_map]
    if missing_cols:
        print(f"[WARN] Missing columns in {SHEET_PAT_SAMP}: {missing_cols}")
        print(f"[INFO] Available columns: {list(header_map.keys())}")

    # Get column indices
    sample_id_col = header_map.get("sample_id")
    if not sample_id_col:
        raise ValueError("Column 'sample_id' not found in patients&samples sheet")

    # Build a map of sample_id -> row number (for updating cells later)
    sample_id_to_row = {}
    for row_idx in range(2, ws.max_row + 1):
        cell_value = ws.cell(row=row_idx, column=sample_id_col).value
        if cell_value:
            sample_5 = first_5_digits_anywhere(str(cell_value))
            if sample_5:
                if sample_5 not in sample_id_to_row:
                    sample_id_to_row[sample_5] = []
                sample_id_to_row[sample_5].append(row_idx)

    print(f"[INFO] Found {len(sample_id_to_row)} unique sample codes in inventory")

    # Step 3: Load HemoPC list with pandas (just for data processing)
    # Only load the columns we need to speed up processing
    needed_cols = [HEMO_COL_NOM, HEMO_COL_ECHANTILLON, HEMO_COL_ACIDE, 
                   HEMO_COL_STATUT, HEMO_COL_DATE, HEMO_COL_PANEL]
    
    df_list = pd.read_excel(
        listfile_path,
        sheet_name=SHEET_LIST,
        header=1,
        usecols=lambda x: x in needed_cols,
    )

    print(f"[INFO] HemoPC list rows: {len(df_list)} (loaded {len(df_list.columns)} columns)")

    # Normalize keys in HemoPC list + classify panels
    df_list["_sample5"] = df_list[HEMO_COL_ECHANTILLON].apply(first_5_digits_anywhere)

    # Classify panels
    if HEMO_COL_PANEL in df_list.columns:
        df_list["_cap_type"], df_list["_cap_panel"] = zip(*df_list[HEMO_COL_PANEL].apply(classify_panel))
    else:
        df_list["_cap_type"] = pd.NA
        df_list["_cap_panel"] = pd.NA

    # Parse dates
    if HEMO_COL_DATE in df_list.columns:
        df_list["_date"] = df_list[HEMO_COL_DATE].apply(parse_date_safe)
    else:
        df_list["_date"] = pd.NaT

    # Parse status and filter out failures
    if HEMO_COL_STATUT in df_list.columns:
        df_list["_status_norm"] = df_list[HEMO_COL_STATUT].apply(lambda x: norm_text(x, keep="lower"))
        mask_ok_status = df_list["_status_norm"].isna() | ~df_list["_status_norm"].isin(FAILURE_STATUSES)
        df_list_filtered = df_list.loc[mask_ok_status].copy()
        print(f"[INFO] After filtering failures: {len(df_list_filtered)} rows (removed {len(df_list) - len(df_list_filtered)})")
    else:
        df_list_filtered = df_list.copy()

    # Keep only rows with recognized panels
    df_list_rec = df_list_filtered[df_list_filtered["_cap_type"].notna()].copy()
    print(f"[INFO] Rows with recognized panels: {len(df_list_rec)}")

    # Show panel classification summary
    print("\n[INFO] Panel classification summary:")
    for cap_type in ["igtcr", "fusion", "mutation"]:
        count = (df_list_rec["_cap_type"] == cap_type).sum()
        print(f"  {cap_type}: {count} rows")

    # Step 4: Build aggregated capture data per sample
    # Group by sample5 and cap_type
    capture_data = {}  # sample5 -> {cap_type -> {panel, date, status}}

    for _, row in df_list_rec.iterrows():
        sample5 = row["_sample5"]
        if pd.isna(sample5):
            continue
        sample5 = str(sample5)
        
        cap_type = row["_cap_type"]
        cap_panel = row["_cap_panel"]
        cap_date = row["_date"]

        if sample5 not in capture_data:
            capture_data[sample5] = {}
        
        if cap_type not in capture_data[sample5]:
            capture_data[sample5][cap_type] = {
                "panels": [],
                "dates": [],
            }
        
        if cap_panel and str(cap_panel) not in capture_data[sample5][cap_type]["panels"]:
            capture_data[sample5][cap_type]["panels"].append(str(cap_panel))
            if pd.notna(cap_date):
                capture_data[sample5][cap_type]["dates"].append(cap_date)
            else:
                capture_data[sample5][cap_type]["dates"].append(None)

    # Aggregate panels and dates
    for sample5, types in capture_data.items():
        for cap_type, data in types.items():
            panels = data["panels"]
            dates = data["dates"]
            
            # Format dates
            date_strs = []
            for i, p in enumerate(panels):
                if i < len(dates) and dates[i]:
                    date_strs.append(dates[i].strftime("%Y-%m-%d"))
                else:
                    date_strs.append("")
            
            data["panel_str"] = SEPARATOR.join(panels)
            data["date_str"] = SEPARATOR.join(date_strs)
            data["status_str"] = SEPARATOR.join(["success"] * len(panels))

    # Step 5: Update the worksheet cells
    print("\n[INFO] Updating cells in worksheet...")

    # Get column indices for target columns
    col_indices = {}
    for col_name in TARGET_COLS:
        idx = header_map.get(col_name)
        if idx:
            col_indices[col_name] = idx
        else:
            print(f"[WARN] Column '{col_name}' not found, skipping")

    updates_count = {ctype: 0 for ctype in ["igtcr", "fusion", "mutation"]}

    for sample5, row_indices in sample_id_to_row.items():
        if sample5 not in capture_data:
            continue
        
        for cap_type in ["igtcr", "fusion", "mutation"]:
            if cap_type not in capture_data[sample5]:
                continue
            
            data = capture_data[sample5][cap_type]
            panel_str = data["panel_str"]
            date_str = data["date_str"]
            status_str = data["status_str"]

            panel_col = col_indices.get(f"{cap_type}_capture_panel")
            date_col = col_indices.get(f"{cap_type}_capture_date")
            status_col = col_indices.get(f"{cap_type}_capture_status")

            for row_idx in row_indices:
                # Only update if cell is currently empty
                if panel_col:
                    current = ws.cell(row=row_idx, column=panel_col).value
                    if not current or str(current).strip() == "":
                        ws.cell(row=row_idx, column=panel_col).value = panel_str
                        updates_count[cap_type] += 1
                
                if date_col:
                    current = ws.cell(row=row_idx, column=date_col).value
                    if not current or str(current).strip() == "":
                        ws.cell(row=row_idx, column=date_col).value = date_str
                
                if status_col:
                    current = ws.cell(row=row_idx, column=status_col).value
                    if not current or str(current).strip() == "":
                        ws.cell(row=row_idx, column=status_col).value = status_str

    # Step 6: Save the workbook (preserves all original formatting)
    print(f"\n[INFO] Saving workbook...")
    wb.save(out_path)
    wb.close()

    print(f"\n[INFO] Wrote: {out_path}")
    print(f"[INFO] Updated rows (non-empty *_capture_panel):")
    for ctype, count in updates_count.items():
        print(f"  {ctype}: {count}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Transpose HemoPC capture data to cfDNA inventory patients&samples sheet")
    ap.add_argument("--inventory", default="cfDNA_inventaire_2025.xlsx",
                    help="Path to cfDNA inventory Excel file")
    ap.add_argument("--listfile", default="archive/hemopc_transpose/Liste patients NGS_panel HemoPC.xlsx",
                    help="Path to HemoPC patient list Excel file")
    ap.add_argument("--out", default="cfDNA_inventaire_2025_updated.xlsx",
                    help="Output file path")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run without writing output file")
    args = ap.parse_args()
    main(args)

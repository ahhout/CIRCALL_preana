#!/usr/bin/env python3
"""
Rewrite sample_id for cfDNA rows and report duplicates.

Usage:
  python rewrite_sample_ids.py
"""

import re
from pathlib import Path
import pandas as pd

in_path = Path("cfDNA_banque_echantillons_2025.xlsx")
out_path = in_path.with_name(in_path.stem + "_cfDNA_ids.xlsx")

if not in_path.exists():
    raise SystemExit(f"input file not found: {in_path}")

# helper: case-/accent-agnostic header lookup
def find_col(cols, candidates):
    norm = {re.sub(r"[^a-z0-9]+","", c.strip().lower()): c for c in cols}
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+","", cand.strip().lower())
        if key in norm:
            return norm[key]
    # fallback: substring match
    for c in cols:
        if any(re.sub(r"[^a-z0-9]+","", cand.strip().lower()) in re.sub(r"[^a-z0-9]+","", c.strip().lower())
               for cand in candidates):
            return c
    return None

# open workbook and pick the first sheet that contains both columns
xls = pd.ExcelFile(in_path)
target_sheet = None
sample_col = None
nuc_col = None
for sh in xls.sheet_names:
    df_probe = pd.read_excel(xls, sheet_name=sh)
    sc = find_col(df_probe.columns, ["sample_id", "sample id", "id_echantillon", "id echantillon"])
    nc = find_col(df_probe.columns, ["nucleic_acid", "nucleic acid", "acide_nucleique", "acide nucleique"])
    if sc and nc:
        target_sheet = sh
        sample_col, nuc_col = sc, nc
        break
if target_sheet is None:
    # fall back to first sheet
    target_sheet = xls.sheet_names[0]
    df_probe = pd.read_excel(xls, sheet_name=target_sheet)
    sample_col = find_col(df_probe.columns, ["sample_id", "sample id", "id_echantillon", "id echantillon"])
    nuc_col = find_col(df_probe.columns, ["nucleic_acid", "nucleic acid", "acide_nucleique", "acide nucleique"])

if not sample_col or not nuc_col:
    raise SystemExit(
        f"could not locate required columns in sheet '{target_sheet}'. "
        f"found: {list(pd.read_excel(xls, sheet_name=target_sheet).columns)}"
    )

# read target sheet
df = pd.read_excel(xls, sheet_name=target_sheet)

# keep original id for traceability
if "_original_sample_id" not in df.columns:
    df["_original_sample_id"] = df[sample_col]

# mask cfDNA rows (exact match to 'cfDNA', case-insensitive, trimmed)
mask_cfdna = df[nuc_col].astype(str).str.strip().str.lower().eq("cfdna")

# append suffix when needed (avoid double-appending)
def append_suffix(val, suffix="_cfDNA"):
    if pd.isna(val):
        return val
    v = str(val)
    return v if v.lower().endswith(suffix.lower()) else v + suffix

df.loc[mask_cfdna, sample_col] = df.loc[mask_cfdna, sample_col].apply(append_suffix)

# duplicate reporting on rewritten sample_id
counts = df[sample_col].astype(str).value_counts()
dup_counts = counts[counts > 1].rename_axis("sample_id").reset_index(name="count")
dup_rows = df[df[sample_col].astype(str).isin(dup_counts["sample_id"])].copy()
dup_rows.insert(0, "row_index", dup_rows.index)

# write output: preserve all sheets, replace only the target
with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    for sh in xls.sheet_names:
        if sh == target_sheet:
            df.to_excel(writer, sheet_name=sh, index=False)
        else:
            pd.read_excel(xls, sheet_name=sh).to_excel(writer, sheet_name=sh, index=False)
    dup_counts.to_excel(writer, sheet_name="duplicate_summary", index=False)
    dup_rows.to_excel(writer, sheet_name="duplicate_rows", index=False)

# console summary (optional)
updated = int(mask_cfdna.sum())
total_dup_ids = int((dup_counts["count"] - 1).sum()) if not dup_counts.empty else 0
print(f"processed sheet: {target_sheet}")
print(f"rows updated with '_cfDNA': {updated}")
if total_dup_ids > 0:
    print(f"warning: {len(dup_counts)} duplicated sample_id values; {total_dup_ids} rows beyond the first.")
    print("see 'duplicate_summary' and 'duplicate_rows' sheets in the output file.")
else:
    print("no duplicated sample_id values after rewrite.")

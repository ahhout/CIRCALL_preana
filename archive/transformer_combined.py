#!/usr/bin/env python3
"""
transformer_combined.py — columns tailored to user's schema

Key points:
- Default input: cfDNA_banque_echantillons_2025.xlsx ; Output: <input>_clean.xlsx
- sample_id rewrite for cfDNA rows: append "_cf" (no double-append). sample_id forced to string.
- anonymization: FIRST3(LAST+FIRST)_<timepoint>_<sample_id>
- dob parsed to true Excel date
- Merge logic auto-maps cfDNA_* to MNC_* for three pairs:
    * extraction_date: cfDNA_extraction_date ↔ MNC_extraction_date
    * tapestation_ng_per_uL: cfDNA_tapestation_ng_per_uL ↔ MNC_tapestation_ng_per_uL
    * elution_volume_uL: cfDNA_elution_volume_uL ↔ MNC_elution_volume_uL
  If an MNC counterpart is missing, that side is treated as empty so cfDNA flows through.
- Merged columns are inserted in-place where the pair used to be; originals are dropped.
- Adds a merge_summary sheet showing which columns were used and counts.
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
import numpy as np
import pandas as pd


# ---------- header lookup ----------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.strip().lower())

def find_col(cols, candidates):
    norm = {_norm(c): c for c in cols}
    for cand in candidates:
        key = _norm(cand)
        if key in norm:
            return norm[key]
    for c in cols:
        if any(_norm(cand) in _norm(c) for cand in candidates):
            return c
    return None


# ---------- helpers ----------
_BLANK_SENTINELS = {"", "?", "na", "n/a", "nan", "none"}  # all lowercase

def is_blankish(x) -> bool:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return True
    s = str(x).strip().lower()  # <-- lowercase once
    return s in _BLANK_SENTINELS

def to_number(x):
    if is_blankish(x):
        return np.nan
    if isinstance(x, str):
        x = x.strip().replace(",", ".")  # FR "3,5" -> "3.5"
    try:
        return float(x)
    except Exception:
        return np.nan

def parse_date_maybe(s, date_formats):
    if is_blankish(s):
        return None
    if isinstance(s, (pd.Timestamp, datetime)):
        return pd.to_datetime(s).date()

    s = str(s).strip()

    # user formats first
    for fmt in date_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass

    # pandas (dayfirst for FR)
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if not pd.isna(dt):
            return dt.date()
    except Exception:
        pass

    return None

def append_suffix(val, suffix="_cf"):
    if is_blankish(val):
        return val
    v = str(val)
    return v if v.lower().endswith(suffix.lower()) else v + suffix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_excel",
        nargs="?", default="cfDNA_banque_echantillons_2025.xlsx",
        help="path to input .xlsx (default: cfDNA_banque_echantillons_2025.xlsx)"
    )
    parser.add_argument("-o", "--output_excel",
                        help="output .xlsx (default: <input>_clean.xlsx)")
    parser.add_argument("--sheet", default=None,
                        help="sheet name (default: auto-detect sample_id/nucleic_acid; else first sheet)")
    parser.add_argument("--prefer", default="cfDNA", choices=["cfDNA", "MNC", "NaN"],
                        help="on conflict, which side to keep (default: cfDNA)")
    parser.add_argument("--num_tol", type=float, default=1e-6,
        help="numeric tolerance (default: 1e-6)")
    parser.add_argument("--date_formats", nargs="*", default=["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"],
        help="date formats to try")
    parser.add_argument("--excel_date_format", default="dd/mm/yyyy",
        help="Excel date display format (default dd/mm/yyyy)")
    parser.add_argument("--suffix", default="_cf",
        help="suffix for cfDNA sample_id (default _cf)")
    args = parser.parse_args()

    in_path = Path(args.input_excel)
    out_path = Path(args.output_excel) if args.output_excel else in_path.with_name(in_path.stem + "_clean.xlsx")
    if not in_path.exists():
        raise SystemExit(f"input file not found: {in_path}")

    xls = pd.ExcelFile(in_path)

    # choose sheet
    if args.sheet:
        sheet = args.sheet
    else:
        detected = None
        for sh in xls.sheet_names:
            probe = pd.read_excel(xls, sh, nrows=5)
            sc = find_col(probe.columns, ["sample_id", "sample id", "id_echantillon", "id echantillon"])
            nc = find_col(probe.columns, ["nucleic_acid", "nucleic acid", "acide_nucleique", "acide nucleique"])
            if sc and nc:
                detected = sh
                break
        sheet = detected if detected else xls.sheet_names[0]

    df = pd.read_excel(xls, sheet_name=sheet)

    # --- sample_id rewrite ---
    sample_col = find_col(df.columns, ["sample_id", "sample id", "id_echantillon", "id echantillon"])
    nuc_col = find_col(df.columns, ["nucleic_acid", "nucleic acid", "acide_nucleique", "acide nucleique"])
    updated_rows = 0
    dup_counts = pd.DataFrame(); dup_rows = pd.DataFrame()

    if sample_col and nuc_col:
        if "_original_sample_id" not in df.columns:
            df["_original_sample_id"] = df[sample_col]
        mask = df[nuc_col].astype(str).str.strip().str.lower().eq("cfdna")
        df.loc[mask, sample_col] = df.loc[mask, sample_col].apply(lambda v: append_suffix(v, args.suffix))
        updated_rows = int(mask.sum())
    else:
        print("warning: could not find both 'sample_id' and 'nucleic_acid'; skipping sample_id rewrite.")

    # ensure sample_id string + duplicates report
    if sample_col:
        df[sample_col] = df[sample_col].astype(str)
        counts = df[sample_col].value_counts()
        dup_counts = counts[counts > 1].rename_axis("sample_id").reset_index(name="count")
        if not dup_counts.empty:
            dup_rows = df[df[sample_col].isin(dup_counts["sample_id"])].copy()
            dup_rows.insert(0, "row_index", dup_rows.index)

    # --- dynamic merge pairs tailored to provided headers ---
    # We'll look for these cfDNA columns and attempt to pair to the MNC_* counterpart.
    targets = [
        ("cfDNA_extraction_date",      "MNC_extraction_date",       False, "extraction_date_merged"),
        ("cfDNA_tapestation_ng_per_uL","MNC_tapestation_ng_per_uL", True,  "tapestation_ng_per_uL_merged"),
        ("cfDNA_elution_volume_uL",    "MNC_elution_volume_uL",     True,  "elution_volume_uL_merged"),
    ]

    # Don't use already-merged columns as sources.
    existing_merged = {c for c in df.columns if c.endswith("_merged")}

    conflict_rows = []
    merge_diag = []
    prefer_lower = args.prefer.lower()

    for cf_col, mnc_col, is_numeric, outcol in targets:
        # exact or fuzzy resolve
        cf_resolved  = cf_col if cf_col in df.columns else find_col(df.columns, [cf_col])
        mnc_resolved = mnc_col if mnc_col in df.columns else find_col(df.columns, [mnc_col])

        # Skip using *_merged columns as sources
        if cf_resolved in existing_merged:
            cf_resolved = None
        if mnc_resolved in existing_merged:
            mnc_resolved = None

        # Build series; if a side is missing, treat as all NaN, so the other side flows through.
        sa = df[cf_resolved] if cf_resolved in df.columns else pd.Series([np.nan]*len(df), index=df.index)
        sb = df[mnc_resolved] if mnc_resolved in df.columns else pd.Series([np.nan]*len(df), index=df.index)

        # If both sides are missing entirely, skip the pair.
        if (cf_resolved is None) and (mnc_resolved is None):
            merge_diag.append({
                "outcol": outcol, "cfDNA_col": None, "MNC_col": None,
                "cfDNA_nonnull": 0, "MNC_nonnull": 0,
                "merged_nonnull": 0, "conflicts": 0, "note": "skipped (no columns)"
            })
            continue

        merged = []
        conflicts = []

        for va, vb in zip(sa, sb):
            a_na = is_blankish(va)
            b_na = is_blankish(vb)

            if a_na and b_na:
                merged.append(np.nan); conflicts.append(False)
            elif not a_na and b_na:
                merged.append(to_number(va) if is_numeric else parse_date_maybe(va, args.date_formats))
                conflicts.append(False)
            elif a_na and not b_na:
                merged.append(to_number(vb) if is_numeric else parse_date_maybe(vb, args.date_formats))
                conflicts.append(False)
            else:
                if is_numeric:
                    na, nb = to_number(va), to_number(vb)
                    if not pd.isna(na) and not pd.isna(nb) and abs(na - nb) <= args.num_tol:
                        merged.append(na); conflicts.append(False)
                    else:
                        conflicts.append(True)
                        merged.append(na if prefer_lower == "cfdna" else nb if prefer_lower == "mnc" else np.nan)
                else:
                    da, db = parse_date_maybe(va, args.date_formats), parse_date_maybe(vb, args.date_formats)
                    if da and db and da == db:
                        merged.append(da); conflicts.append(False)
                    else:
                        conflicts.append(True)
                        merged.append(da if prefer_lower == "cfdna" else db if prefer_lower == "mnc" else np.nan)

        col_values = pd.to_datetime(merged) if not is_numeric else merged

        # Determine insertion index (near cfDNA if available, else near MNC, else at end)
        if cf_resolved in df.columns:
            insert_idx = df.columns.get_loc(cf_resolved)
        elif mnc_resolved in df.columns:
            insert_idx = df.columns.get_loc(mnc_resolved)
        else:
            insert_idx = len(df.columns)

        # Insert merged column before dropping originals (drop outcol first if already exists)
        if outcol in df.columns:
            df = df.drop(columns=[outcol])
        df.insert(insert_idx, outcol, col_values)

        # Conflicts report
        if any(conflicts):
            mask_conf = pd.Series(conflicts, index=df.index)
            tmp = pd.DataFrame({
                "row_index": df.index[mask_conf],
                (cf_resolved or "cfDNA_col"): sa[mask_conf],
                (mnc_resolved or "MNC_col"): sb[mask_conf],
            })
            tmp["merged_column"] = outcol
            conflict_rows.append(tmp.reset_index(drop=True))

        # Drop originals if present
        drop_list = [c for c in (cf_resolved, mnc_resolved) if c in df.columns]
        df = df.drop(columns=drop_list, errors="ignore")

        # Diagnostics row
        merge_diag.append({
            "outcol": outcol,
            "cfDNA_col": cf_resolved,
            "MNC_col": mnc_resolved,
            "cfDNA_nonnull": int(pd.Series(sa).apply(lambda x: not is_blankish(x)).sum()),
            "MNC_nonnull": int(pd.Series(sb).apply(lambda x: not is_blankish(x)).sum()),
            "merged_nonnull": int(pd.Series(col_values).apply(lambda x: not pd.isna(x)).sum()),
            "conflicts": int(sum(conflicts)),
            "note": "" if (cf_resolved or mnc_resolved) else "no sources"
        })

    conflicts_df = pd.concat(conflict_rows, axis=0).reset_index(drop=True) if conflict_rows else pd.DataFrame()
    merge_diag_df = pd.DataFrame(merge_diag)

    # --- DOB column to real excel date if present ---
    dob_col = find_col(df.columns, ["dob", "date_of_birth", "birthdate", "date de naissance"])
    if dob_col:
        parsed_dob = df[dob_col].apply(lambda v: parse_date_maybe(v, args.date_formats))
        df[dob_col] = pd.to_datetime(parsed_dob)

    # --- anonymization column ---
    last_col = find_col(df.columns, ["lastname", "last_name", "nom"])
    first_col = find_col(df.columns, ["firstname", "first_name", "prenom"])
    tp_col = find_col(df.columns, ["treatment_phase", "timepoint", "tp"])

    def make_anonym(row):
        last = "" if not last_col or is_blankish(row.get(last_col, None)) else str(row[last_col])
        first = "" if not first_col or is_blankish(row.get(first_col, None)) else str(row[first_col])
        prefix = (last + first).upper().replace(" ", "")[:3] if (last or first) else "XXX"
        tp = "TP?" if not tp_col or is_blankish(row.get(tp_col, None)) else str(row[tp_col]).strip()
        sid = "NA" if not sample_col or is_blankish(row.get(sample_col, None)) else str(row[sample_col]).strip()
        return f"{prefix}_{tp}_{sid}"

    if last_col or first_col:
        df["anonymization"] = df.apply(make_anonym, axis=1)

    # --- meta information ---
    meta = pd.DataFrame({
        "processed_sheet": [sheet],
        "prefer_param": [args.prefer],
        "numeric_tolerance": [args.num_tol],
        "excel_date_format": [args.excel_date_format],
        "suffix": [args.suffix],
        "timestamp": [pd.Timestamp.now().isoformat()],
        "rows_updated_sample_id": [updated_rows],
        "duplicate_id_groups": [int(len(dup_counts)) if not dup_counts.empty else 0],
    })

    # --- write out ---
    with pd.ExcelWriter(out_path, engine="xlsxwriter", datetime_format=args.excel_date_format) as writer:
        for sh in xls.sheet_names:
            if sh == sheet:
                df.to_excel(writer, sheet_name=sh, index=False)
            else:
                pd.read_excel(xls, sheet_name=sh).to_excel(writer, sheet_name=sh, index=False)

        if not conflicts_df.empty:
            conflicts_df.to_excel(writer, index=False, sheet_name="conflicts")
        else:
            pd.DataFrame(columns=["row_index", "merged_column"]).to_excel(writer, index=False, sheet_name="conflicts")

        if not dup_counts.empty:
            dup_counts.to_excel(writer, index=False, sheet_name="duplicate_summary")
            dup_rows.to_excel(writer, index=False, sheet_name="duplicate_rows")
        else:
            pd.DataFrame(columns=["sample_id", "count"]).to_excel(writer, index=False, sheet_name="duplicate_summary")
            pd.DataFrame(columns=["row_index"]).to_excel(writer, index=False, sheet_name="duplicate_rows")

        if not meta.empty:
            meta.to_excel(writer, index=False, sheet_name="meta")

        if not merge_diag_df.empty:
            merge_diag_df.to_excel(writer, index=False, sheet_name="merge_summary")
        else:
            pd.DataFrame(columns=["outcol","cfDNA_col","MNC_col","cfDNA_nonnull","MNC_nonnull","merged_nonnull","conflicts","note"]) \
              .to_excel(writer, index=False, sheet_name="merge_summary")

    print(f"processed sheet: {sheet}")
    print(f"rows updated with '{args.suffix}': {updated_rows}")
    if not dup_counts.empty:
        total_dup_rows_beyond_first = int((dup_counts['count'] - 1).sum())
        print(f"warning: {len(dup_counts)} duplicated sample_id values; {total_dup_rows_beyond_first} rows beyond the first.")
        print("see 'duplicate_summary' and 'duplicate_rows' sheets in the output.")
    if not conflicts_df.empty:
        print(f"merge conflicts recorded: {len(conflicts_df)} (see 'conflicts' sheet).")
    print(f"wrote: {out_path}")


if __name__ == "__main__":
    main()

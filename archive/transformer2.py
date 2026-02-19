#!/usr/bin/env python3
"""
transformer2.py

Merges these pairs with safeguards and inserts each merged column next to its counterparts:
  - cfD_extraction_date + MNC_extraction_date -> extraction_date_merged
  - cfD_tapestation_ng_per_uL + MNC_tapestation_ng_per_uL -> tapestation_ng_per_uL_merged
  - cfD_elution_volume_uL + MNC_elution_volume_uL -> elution_volume_uL_merged

Features
- On conflict: keep cfDNA (default) or MNC/NaN with --prefer
- Dates written as *real Excel dates* so they are recognized immediately
- Display format of dates controlled with --excel_date_format (default yyyy-mm-dd)
- Original six cfD/MNC columns are dropped; only merged columns remain
- Conflicts sheet lists rows where cfD and MNC disagreed
- Meta sheet documents settings
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
import numpy as np
import pandas as pd


# ---------- helpers ----------
def to_number(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, str):
        x = x.strip().replace(",", ".")
    try:
        return float(x)
    except Exception:
        return np.nan


def _is_junk(s):
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return True
    s = str(s).strip()
    return s in {"", "?", "nan", "none", "NaN", "None", "NONE"}


def parse_date_maybe(s, date_formats):
    """Return date() if parsable, else None."""
    if _is_junk(s):
        return None

    if isinstance(s, (pd.Timestamp, datetime)):
        return pd.to_datetime(s).date()

    s = str(s).strip()

    if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}.*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", s):
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass

    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        pass

    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if not pd.isna(dt):
            return dt.date()
    except Exception:
        pass

    for fmt in date_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue

    return None


def safe_merge(series_a, series_b, *, is_numeric, tol, date_formats, prefer="cfDNA"):
    merged = []
    conflicts = []

    for a, b in zip(series_a, series_b):
        a_na = _is_junk(a)
        b_na = _is_junk(b)

        if a_na and b_na:
            merged.append(np.nan)
            conflicts.append(False)
            continue
        if not a_na and b_na:
            merged.append(a)
            conflicts.append(False)
            continue
        if a_na and not b_na:
            merged.append(b)
            conflicts.append(False)
            continue

        if is_numeric:
            na, nb = to_number(a), to_number(b)
            if not pd.isna(na) and not pd.isna(nb):
                if abs(na - nb) <= tol:
                    merged.append(a)
                    conflicts.append(False)
                else:
                    conflicts.append(True)
                    merged.append(a if prefer.lower() == "cfdna" else b if prefer.lower() == "mnc" else np.nan)
            else:
                conflicts.append(True)
                merged.append(a if prefer.lower() == "cfdna" else b if prefer.lower() == "mnc" else np.nan)
        else:
            da, db = parse_date_maybe(a, date_formats), parse_date_maybe(b, date_formats)
            if (da is not None) and (db is not None) and da == db:
                merged.append(a)
                conflicts.append(False)
            else:
                conflicts.append(True)
                merged.append(a if prefer.lower() == "cfdna" else b if prefer.lower() == "mnc" else np.nan)

    return pd.Series(merged), pd.Series(conflicts)


# ---------- main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_excel", help="path to input .xlsx")
    parser.add_argument("-o", "--output_excel", help="output .xlsx (default: <input>_merged_columns.xlsx)")
    parser.add_argument("--sheet", default=None, help="sheet name (default: first sheet)")
    parser.add_argument("--prefer", default="cfDNA", choices=["cfDNA", "MNC", "NaN"],
                        help="on conflict, which side to keep (default: cfDNA)")
    parser.add_argument("--num_tol", type=float, default=1e-6, help="numeric equality tolerance")
    parser.add_argument("--date_formats", nargs="*", default=["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"],
                        help="extra date formats to try")
    parser.add_argument("--excel_date_format", default="yyyy-mm-dd",
                        help="Excel display format for merged dates (default yyyy-mm-dd)")
    args = parser.parse_args()

    in_path = Path(args.input_excel)
    out_path = Path(args.output_excel) if args.output_excel else in_path.with_name(in_path.stem + "_merged_columns.xlsx")

    xls = pd.ExcelFile(in_path)
    sheet = args.sheet if args.sheet else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet)

    pairs = [
        ("cfD_extraction_date", "MNC_extraction_date", False, "extraction_date_merged"),
        ("cfD_tapestation_ng_per_uL", "MNC_tapestation_ng_per_uL", True, "tapestation_ng_per_uL_merged"),
        ("cfD_elution_volume_uL", "MNC_elution_volume_uL", True, "elution_volume_uL_merged"),
    ]

    conflict_rows = []

    for a, b, is_numeric, outcol in pairs:
        sa = df[a] if a in df.columns else pd.Series([np.nan] * len(df), index=df.index)
        sb = df[b] if b in df.columns else pd.Series([np.nan] * len(df), index=df.index)

        merged_raw, conflicts = safe_merge(sa, sb, is_numeric=is_numeric,
                                           tol=args.num_tol, date_formats=args.date_formats,
                                           prefer=args.prefer)

        if not is_numeric:
            parsed = merged_raw.apply(lambda v: parse_date_maybe(v, args.date_formats))
            df[outcol] = pd.to_datetime(parsed)  # real Excel dates
        else:
            df[outcol] = merged_raw

        if conflicts.any():
            tmp = pd.DataFrame({"row_index": df.index[conflicts], a: sa[conflicts], b: sb[conflicts]})
            tmp["merged_column"] = outcol
            conflict_rows.append(tmp.reset_index(drop=True))

    conflicts_df = pd.concat(conflict_rows, axis=0).reset_index(drop=True) if conflict_rows else pd.DataFrame()

    # drop the originals
    drop_cols = [c for a, b, _, _ in pairs for c in (a, b) if c in df.columns]
    df = df.drop(columns=drop_cols)

    meta = pd.DataFrame({
        "prefer_param": [args.prefer],
        "numeric_tolerance": [args.num_tol],
        "excel_date_format": [args.excel_date_format],
        "timestamp": [pd.Timestamp.now().isoformat()]
    })

    with pd.ExcelWriter(out_path, engine="xlsxwriter", datetime_format=args.excel_date_format) as writer:
        df.to_excel(writer, index=False, sheet_name="data")
        conflicts_df.to_excel(writer, index=False, sheet_name="conflicts")
        meta.to_excel(writer, index=False, sheet_name="meta")

    print(f"wrote: {out_path}")


if __name__ == "__main__":
    main()

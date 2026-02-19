#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import unicodedata
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd

SEPARATOR = ";"  # for concatenation


# ---------- helpers ----------

def strip_accents(s: str) -> str:
    if not isinstance(s, str):
        return s
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def norm_text(s, keep=None):
    if pd.isna(s):
        return None
    s = str(s).strip()
    if s == "":
        return None
    s = strip_accents(s)
    s = s.upper() if keep is None else s.lower()
    return s

def first3_letters(s: str) -> Optional[str]:
    s = norm_text(s)
    if s is None:
        return None
    letters = re.findall(r"[A-Z]", s)
    if not letters:
        return None
    return "".join(letters)[:3]

def first_5_digits_anywhere(s: str) -> Optional[str]:
    if pd.isna(s):
        return None
    s = str(s)
    m = re.search(r"(\d{5})", s)
    return m.group(1) if m else None

def classify_panel(panel_raw: str) -> Tuple[Optional[str], Optional[str]]:
    if pd.isna(panel_raw):
        return None, None
    txt = str(panel_raw).strip()
    if txt == "":
        return None, None
    txt_up = strip_accents(txt).upper()

    # IGTCR anywhere
    if "IGTCR" in txt_up:
        return "igtcr", txt

    # starts with digits (multi-digit) -> mutation, "hemoPCv<digits>"
    m = re.match(r"^\s*(\d+)\b", txt_up)
    if m:
        return "mutation", f"hemoPCv{m.group(1)}"

    # starts with "V" or "LAL" -> mutation (full cell)
    if re.match(r"^\s*V", txt_up) or re.match(r"^\s*LAL", txt_up):
        return "mutation", txt

    # starts with fusion markers
    if (re.match(r"^\s*MLL", txt_up)
        or re.match(r"^\s*PH", txt_up)
        or re.match(r"^\s*ALK", txt_up)
        or re.match(r"^\s*MYC", txt_up)
        or re.match(r"^\s*OTHER\s+FUSIONS", txt_up)):
        return "fusion", txt

    return None, None

def parse_date_safe(x):
    if pd.isna(x) or (isinstance(x, str) and x.strip() == ""):
        return pd.NaT
    try:
        return pd.to_datetime(x, errors="coerce", dayfirst=True)
    except Exception:
        return pd.NaT

def ensure_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df

# tissue equivalences after lowercasing
TISSUE_EQUIV_LOWER = {
    "mnc celdna": "adn",
}

def apply_tissue_mapping(val_norm_lower: Optional[str]) -> Optional[str]:
    if val_norm_lower is None:
        return None
    return TISSUE_EQUIV_LOWER.get(val_norm_lower, val_norm_lower)

def unique_preserve_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def find_status_series(df: pd.DataFrame) -> pd.Series:
    """Return the status column (normalized) or NaNs if none present."""
    for col in df.columns:
        key = strip_accents(str(col)).strip().lower()
        if key in {"status", "statut", "statuts"}:
            return df[col]
    return pd.Series([pd.NA] * len(df), index=df.index)


# ---------- core ----------

def main(args):
    inventory_path = args.inventory
    listfile_path = args.listfile
    out_path = args.out

    SHEET_MANIPS = "manipsNGS"
    SHEET_PAT_SAMP = "patients&samples"
    SHEET_LIST = "liste patients-HOG"

    # Load all sheets to preserve workbook
    xls_all = pd.read_excel(inventory_path, sheet_name=None)
    if SHEET_MANIPS not in xls_all or SHEET_PAT_SAMP not in xls_all:
        raise ValueError("Required sheets missing in inventory workbook.")

    df_mn = xls_all[SHEET_MANIPS].copy()
    df_ps = xls_all[SHEET_PAT_SAMP].copy()

    # Load only needed cols from the big list (status column handled flexibly)
    wanted_base = {"Nom", "ECHANTILLON", "nucleic_acids", "panel", "date"}
    def usecols_filter(col_name: str) -> bool:
        key = strip_accents(str(col_name)).strip().lower()
        return (col_name in wanted_base) or (key in {"status", "statut", "statuts"})
    df_list = pd.read_excel(
        listfile_path,
        sheet_name=SHEET_LIST,
        header=1,
        usecols=usecols_filter,
    )

    # Normalize keys in patients&samples
    for col in ["lastname", "sample_id", "nucleic_acid"]:
        if col not in df_ps.columns:
            raise ValueError(f"Column '{col}' missing in {SHEET_PAT_SAMP}")

    df_ps["_last3"] = df_ps["lastname"].apply(first3_letters)
    df_ps["_sample5"] = df_ps["sample_id"].apply(first_5_digits_anywhere)
    df_ps["_tissue_norm"] = df_ps["nucleic_acid"].apply(lambda x: norm_text(x, keep="lower"))
    df_ps["_tissue_norm"] = df_ps["_tissue_norm"].apply(apply_tissue_mapping)

    # maps for optional sanity cols in manipsNGS
    ps_map_last3 = dict(zip(df_ps["sample_id"], df_ps["_last3"]))
    ps_map_tissN = dict(zip(df_ps["sample_id"], df_ps["_tissue_norm"]))

    # Normalize keys in list + classify
    for col in ["Nom", "ECHANTILLON", "nucleic_acids", "panel", "date"]:
        if col not in df_list.columns:
            raise ValueError(f"Column '{col}' missing in list sheet")

    # status filter: skip rows where status == "échec"
    status_ser = find_status_series(df_list)
    status_norm = status_ser.map(lambda x: norm_text(x, keep="lower"))
    mask_ok_status = status_norm.isna() | (status_norm != "echec")
    df_list = df_list.loc[mask_ok_status].copy()

    df_list["_last3"] = df_list["Nom"].apply(first3_letters)
    df_list["_tissue_norm"] = df_list["nucleic_acids"].apply(lambda x: norm_text(x, keep="lower"))
    df_list["_tissue_norm"] = df_list["_tissue_norm"].apply(apply_tissue_mapping)
    df_list["_cap_type"], df_list["_cap_panel"] = zip(*df_list["panel"].apply(classify_panel))
    df_list["_date"] = df_list["date"].apply(parse_date_safe)

    # keep only recognized panels (i.e., those we actually transpose)
    df_list_rec = df_list[df_list["_cap_type"].notna()].copy()

    # group list by (last3, tissue), then match contains(sample5) within ECHANTILLON
    groups = dict(tuple(df_list_rec.groupby(["_last3", "_tissue_norm"], dropna=False)))
    df_ps_key = df_ps[["_last3", "_sample5", "_tissue_norm", "sample_id"]].dropna(subset=["_last3", "_sample5", "_tissue_norm"]).copy()

    matched_records = []
    for _, r in df_ps_key.iterrows():
        key = (r["_last3"], r["_tissue_norm"])
        s5 = str(r["_sample5"])
        sub = groups.get(key)
        if sub is None:
            continue
        mask = sub["ECHANTILLON"].astype(str).str.contains(s5, regex=False, na=False)
        hits = sub.loc[mask, ["_cap_type", "_cap_panel", "_date"]]
        if hits.empty:
            continue
        for cap_type, cap_panel, dt in hits.itertuples(index=False, name=None):
            matched_records.append({
                "sample_id": r["sample_id"],
                "_cap_type": cap_type,
                "_cap_panel": cap_panel,
                "_date": dt,
            })

    if matched_records:
        df_linked = pd.DataFrame(matched_records)
    else:
        df_linked = pd.DataFrame(columns=["sample_id", "_cap_type", "_cap_panel", "_date"])

    # Aggregate per (sample_id, cap_type): concatenate panels; for each panel keep only its latest date
    def agg_group(sub: pd.DataFrame) -> pd.Series:
        # panels in first-seen order
        panels_order = unique_preserve_order([str(x) for x in sub["_cap_panel"].dropna().tolist()])
        per_panel_dates = []
        for p in panels_order:
            dts = pd.to_datetime(sub.loc[sub["_cap_panel"] == p, "_date"], errors="coerce").dropna()
            if len(dts) == 0:
                per_panel_dates.append("")
            else:
                per_panel_dates.append(dts.max().strftime("%Y-%m-%d"))
        statuses = ["success"] * len(panels_order) if panels_order else []
        return pd.Series({
            "_cap_panel_concat": SEPARATOR.join(panels_order),
            "_date_concat": SEPARATOR.join(per_panel_dates),
            "_status_concat": SEPARATOR.join(statuses) if statuses else pd.NA,
        })

    if not df_linked.empty:
        df_latest = df_linked.groupby(["sample_id", "_cap_type"], as_index=False).apply(agg_group)
    else:
        df_latest = pd.DataFrame(columns=["sample_id", "_cap_type", "_cap_panel_concat", "_date_concat", "_status_concat"])

    # Build wide tables
    captures = {}
    for ctype in ["igtcr", "fusion", "mutation"]:
        sub = df_latest[df_latest["_cap_type"] == ctype].copy()
        if sub.empty:
            captures[ctype] = pd.DataFrame(columns=["sample_id",
                                                    f"{ctype}_capture_panel",
                                                    f"{ctype}_capture_date",
                                                    f"{ctype}_capture_status"])
            continue
        sub.rename(columns={
            "_cap_panel_concat": f"{ctype}_capture_panel",
            "_date_concat": f"{ctype}_capture_date",
            "_status_concat": f"{ctype}_capture_status",
        }, inplace=True)
        for col in [f"{ctype}_capture_panel", f"{ctype}_capture_date", f"{ctype}_capture_status"]:
            if col not in sub.columns:
                sub[col] = pd.NA
        captures[ctype] = sub[["sample_id",
                               f"{ctype}_capture_panel",
                               f"{ctype}_capture_date",
                               f"{ctype}_capture_status"]]

    # Merge per type on sample_id
    df_caps = None
    for ctype in ["igtcr", "fusion", "mutation"]:
        if df_caps is None:
            df_caps = captures[ctype]
        else:
            df_caps = df_caps.merge(captures[ctype], on="sample_id", how="outer")

    if df_caps is None:
        df_caps = pd.DataFrame(columns=["sample_id",
                                        "igtcr_capture_panel","igtcr_capture_date","igtcr_capture_status",
                                        "fusion_capture_panel","fusion_capture_date","fusion_capture_status",
                                        "mutation_capture_panel","mutation_capture_date","mutation_capture_status"])

    # Prepare manipsNGS and join
    fill_cols = [
        "igtcr_capture_status", "igtcr_capture_date", "igtcr_capture_panel",
        "fusion_capture_status", "fusion_capture_date", "fusion_capture_panel",
        "mutation_capture_status", "mutation_capture_date", "mutation_capture_panel",
    ]
    df_mn = ensure_columns(df_mn, fill_cols)

    if "sample_id" not in df_mn.columns:
        raise ValueError(f"'sample_id' required in {SHEET_MANIPS}")

    # optional sanity cols
    df_mn["_last3_from_ps"] = df_mn["sample_id"].map(ps_map_last3)
    df_mn["_tissue_norm_from_ps"] = df_mn["sample_id"].map(ps_map_tissN)

    df_out = df_mn.merge(df_caps, on="sample_id", how="left", suffixes=("", "_new"))

    def coalesce(old, new):
        return np.where(pd.isna(old) | (old == ""), new, old)

    for ctype in ["igtcr", "fusion", "mutation"]:
        for suffix in ["panel", "date", "status"]:
            col = f"{ctype}_capture_{suffix}"
            new_col = f"{col}_new"
            if new_col in df_out.columns:
                df_out[col] = coalesce(df_out[col], df_out[new_col])
                df_out.drop(columns=[new_col], inplace=True, errors="ignore")

    # Write workbook
    xls_all[SHEET_MANIPS] = df_out
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, df_sheet in xls_all.items():
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)

    filled_counts = {
        ctype: int((~pd.isna(df_out[f"{ctype}_capture_panel"]) & (df_out[f"{ctype}_capture_panel"] != "")).sum())
        for ctype in ["igtcr", "fusion", "mutation"]
    }
    print("[INFO] Wrote:", out_path)
    print("[INFO] Filled rows (non-empty *_capture_panel):", filled_counts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="cfDNA_inventaire_2025.xlsx")
    ap.add_argument("--listfile", default="Liste patients NGS_panel HemoPC.xlsx")
    ap.add_argument("--out", default="cfDNA_inventaire_2025.updated.xlsx")
    args = ap.parse_args()
    main(args)

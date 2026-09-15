import argparse
import os
import re
import sys
import unicodedata
import numpy as np
import pandas as pd

# ----------------------------- helpers -----------------------------
def _norm(s: str) -> str:
    """Lowercase, strip accents, remove punctuation (except %) and collapse spaces."""
    s = str(s) if not isinstance(s, str) else s
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9% ]+", " ", s)  # keep %, drop other punctuation
    s = re.sub(r"\s+", " ", s)
    return s


def flatten_cols(mcols):
    """
    Flatten a (possibly MultiIndex) columns object to readable strings
    by joining non-empty parts top→bottom with ' | '.
    """
    flat = []
    for col in mcols:
        parts = col if isinstance(col, tuple) else (col,)
        parts = [str(p).strip() for p in parts
                 if p is not None and str(p).strip() and str(p).lower() != "nan"]
        flat.append(" | ".join(parts))
    return flat

def find_col(cols, patterns, required=True):
    ncols = {c: _norm(c) for c in cols}

    def and_match(nc: str, toks):
        toks = [_norm(t) for t in toks]
        return all(t in nc for t in toks)

    # normalize to list of AND-sets
    if isinstance(patterns, str):
        pattern_sets = [[patterns]]
    elif isinstance(patterns, (list, tuple)) and all(isinstance(p, str) for p in patterns):
        pattern_sets = [list(patterns)]
    else:
        pattern_sets = patterns  # list of lists

    # exact/AND pass
    for c, nc in ncols.items():
        for toks in pattern_sets:
            if and_match(nc, toks):
                return c

    # fallback: best partial score
    best = None
    best_score = -1
    for c, nc in ncols.items():
        score = max(sum(_norm(t) in nc for t in toks) for toks in pattern_sets)
        if score > best_score:
            best, best_score = c, score
    if best_score > 0:
        return best

    if required:
        raise KeyError(
            "Could not find a matching column. Available columns are:\n" +
            "\n".join(f"- {c}" for c in cols)
        )
    return None

def extract_timepoint(cell):
    if not isinstance(cell, str):
        return None
    txt = unicodedata.normalize("NFKD", cell)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch)).lower()
    txt = re.sub(r"\s+", " ", txt)

    if "diag" in txt:
        return "diag"
    if "rechute" in txt:
        return "rechute"
    if "inotuzumab" in txt:
        return "après inotuzumab"

    m = re.search(r"\btp\s*([0-9]+(?:[.,][0-9])?)\b", txt)
    if m:
        val = m.group(1).replace(".", ",")  # normalize to comma
        return f"tp{val}"
    return None


def to_numeric_series(s: pd.Series) -> pd.Series:
    """
    Convert a series to numeric robustly:
      - strip non-numeric except . and ,
      - treat comma as decimal separator
    """
    s2 = s.astype(str).str.replace(r"[^\d,.\-]", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(s2, errors="coerce")


# ------------------------------ main -------------------------------
def main():
    ap = argparse.ArgumentParser(description="Parse cfDNA Excel into a tidy CSV/Parquet.")
    ap.add_argument("--input", default="cfDNA_inventaire_2025.xlsx", help="source Excel")
    ap.add_argument("--out_csv", default="outputs/results/cfdna_parsed.csv", help="output CSV path")
    ap.add_argument("--out_parquet", default=None, help="optional Parquet path")
    ap.add_argument("--header_row", type=int, default=None,
                    help="0-based header row override (skip auto-detect)")
    ap.add_argument("--print_matches", action="store_true",
                    help="print matched headers and timepoint parsing stats")
    ap.add_argument(
        "--mrd_col",
        default=None,
        help="(optional) exact header name for the MRD Ig/TCR column to use; if omitted, the parser auto-selects among MRD-like columns",
    )
    ap.add_argument(
        "--mrd_negative_tokens",
        default="na,negative,neg,n/a",
        help="comma-separated tokens considered MRD-negative after lowercasing/stripping (default: 'na,negative,neg,n/a')",
    )
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)

    # --- detect stacked header rows
    df0 = pd.read_excel(args.input, header=None)
    hdr_row = args.header_row

    if hdr_row is not None:
        if hdr_row < 0 or hdr_row >= len(df0):
            print("header_row is out of range for the input file.", file=sys.stderr)
            sys.exit(1)
    else:
        hdr_row = None

    # Prefer the explicit line (seen in your sheet): "Ordre numérique pour filtre"
    if hdr_row is None:
        for i in range(min(40, len(df0))):
            row_vals = [str(x) for x in df0.iloc[i].tolist()]
            if row_vals and _norm(row_vals[0]).startswith("ordre numerique pour filtre"):
                hdr_row = i
                break

    # Fallback: first line containing "stade" or "stades"
    if hdr_row is None:
        for i in range(min(40, len(df0))):
            row_vals = [str(x) for x in df0.iloc[i].tolist()]
            if any("stade" in _norm(x) or "stades" in _norm(x) for x in row_vals):
                hdr_row = i
                break

    # Fallback: detect a row that looks like a normal header set
    if hdr_row is None:
        header_tokens = {"order", "anonymization", "lastname", "nom", "prenom", "name"}
        for i in range(min(10, len(df0))):
            row_vals = [_norm(x) for x in df0.iloc[i].tolist()]
            hits = sum(1 for x in row_vals if x in header_tokens)
            if hits >= 2:
                hdr_row = i
                break

    if hdr_row is None:
        print("Could not detect header row automatically. Aborting.", file=sys.stderr)
        sys.exit(1)

    # Assume up to 3 header levels above the data row
    levels = [r for r in [hdr_row - 2, hdr_row - 1, hdr_row] if r >= 0]
    df = pd.read_excel(args.input, header=levels)
    df.columns = flatten_cols(df.columns)

    # --- match required columns (robust to wording/accents)
    name_col   = find_col(df.columns, [["nom"], ["lastname"], ["last", "name"]])
    adn_col    = find_col(df.columns, [["type", "adn", "extrait"],
                                       ["type d'adn", "extrait"],
                                       ["type", "adn"],
                                       ["nucleic", "acid"],
                                       ["nucleic_acid"]])
    ttt_col    = find_col(df.columns, [["stades", "echantillons", "cfdna"],
                                       ["stade", "ttt"],
                                       ["stade", "traitement"],
                                       ["treatment", "phase"],
                                       ["treatment_phase"]])
    tube_col   = find_col(df.columns, [["anticoagulant"], ["tube"]], required=False)
    volume_col = find_col(df.columns, [["volume", "recup"],
                                       ["plasma", "extracted"],
                                       ["plasma_extracted", "ml"],
                                       ["plasma", "ml"]])
    cf_col     = find_col(df.columns, [["%", "cfdna"],
                                       ["pourcentage", "cfdna"],
                                       ["pct", "cfdna"],
                                       ["cfdna", "%"],
                                       ["cfdna", "percent"]], required=False)
    ng_col     = find_col(df.columns, [["ADN", "total", "ng"],
                                       ["cfdna", "total", "ng"],
                                       ["cfdna", "total"]])
    dosage_col = find_col(
        df.columns,
        [["tapestation", "ng", "ul"]],
        required=False,
    )

    # Optional identifiers
    sample_id_col = find_col(df.columns, [["sample", "id"], ["sample_id"], ["id", "sample"]], required=False)
    anon_col = find_col(
        df.columns,
        [["anonymisation"], ["anonymization"], ["anonym", "id"], ["anonym", "code"], ["code", "anonym"]],
        required=False,
    )
    genetic_subtype_col = find_col(
        df.columns,
        [["genetic", "subtype"], ["subtype", "genetic"], ["sous", "type", "genet"]],
        required=False,
    )
    tissue_col = find_col(
        df.columns,
        [["tissue"], ["tissu"], ["type", "tissu"], ["sample", "type"]],
        required=False,
    )

    # Optional MRD column (auto-select the most informative candidate unless user overrides)
    def _choose_mrd_col(cols: list[str], df_for_scoring: pd.DataFrame) -> str | None:
        if args.mrd_col is not None:
            if args.mrd_col not in cols:
                raise KeyError(
                    "--mrd_col was provided but not found. Available columns include:\n" +
                    "\n".join(f"- {c}" for c in cols)
                )
            return args.mrd_col

        # Strong preference: if the sheet already has an explicit MRD_IgTCR column, use it.
        # (This matches the downstream expectation and avoids accidentally selecting IgTCR capture metadata.)
        for c in cols:
            if str(c).strip() == "MRD_IgTCR" or _norm(c) == _norm("MRD_IgTCR"):
                return c

        candidates: list[str] = []
        for c in cols:
            nc = _norm(c)
            if "mrd" in nc or "igtcr" in nc or ("ig" in nc and "tcr" in nc):
                candidates.append(c)

        # de-dup keep order
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            return None

        neg_tokens = {t.strip().lower() for t in str(args.mrd_negative_tokens).split(",") if t.strip()}
        missing_tokens = {"", "nan", "none"}

        def score(c: str) -> tuple[int, int, int, int]:
            # Higher is better.
            # 1) non_neg: values that are present and not in negative tokens
            # 2) non_missing: present values (any token)
            # 3) uniq: number of unique present tokens
            # 4) name_bonus: prefer columns that explicitly mention Ig/TCR
            s = df_for_scoring[c].astype(str).str.strip().str.lower()
            s = s.replace({"nan": "", "none": ""})
            present = s[~s.isin(missing_tokens)]
            non_neg = present[~present.isin(neg_tokens)]
            nc = _norm(c)
            name_bonus = 0
            if "mrd" in nc:
                name_bonus += 2
            if "igtcr" in nc or ("ig" in nc and "tcr" in nc):
                name_bonus += 1
            return (int(non_neg.shape[0]), int(present.shape[0]), int(present.nunique()), name_bonus)

        ranked = sorted(((score(c), c) for c in candidates), reverse=True)
        return ranked[0][1]

    mrd_col = _choose_mrd_col(list(df.columns), df)

    if args.print_matches:
        print("matched columns:")
        print(f"  name_col   = {name_col}")
        print(f"  adn_col    = {adn_col}")
        print(f"  ttt_col    = {ttt_col}")
        print(f"  tube_col   = {tube_col}")
        print(f"  volume_col = {volume_col}")
        print(f"  cf_col     = {cf_col}")
        print(f"  ng_col     = {ng_col}")
        print(f"  dosage_col = {dosage_col}")
        print(f"  mrd_col    = {mrd_col}")
        print(f"  sample_id_col = {sample_id_col}")
        print(f"  anon_col      = {anon_col}")
        print(f"  genetic_subtype_col = {genetic_subtype_col}")
        print(f"  tissue_col    = {tissue_col}")

    # --- filter rows to cfDNA and compute fields
    df_f = df[df[adn_col].astype(str).str.contains("cfdna", case=False, na=False)].copy()
    excluded_lcr_rows = 0
    if tissue_col is not None and tissue_col in df_f.columns:
        tissue_norm = df_f[tissue_col].map(_norm)
        is_lcr = tissue_norm == "lcr"
        excluded_lcr_rows = int(is_lcr.sum())
        if excluded_lcr_rows:
            df_f = df_f.loc[~is_lcr].copy()

    # Normalize and parse timepoints
    df_f[name_col] = df_f[name_col].astype(str).str.lower()
    df_f["timepoint"] = df_f[ttt_col].apply(extract_timepoint)

    # Keep all rows where a timepoint was parsed (no hard whitelist)
    df_f = df_f[df_f["timepoint"].notna()]

    # Numeric columns (robust parsing)
    df_f["ml_plasma"] = to_numeric_series(df_f[volume_col])
    df_f["total_ng_dna"] = to_numeric_series(df_f[ng_col])
    df_f["dosage_ng_per_uL"] = (
        to_numeric_series(df_f[dosage_col])
        if dosage_col is not None and dosage_col in df_f.columns
        else np.nan
    )

    # % cfDNA: accept fraction (≤1) or percent (>1), and strings like "12%"
    if cf_col is not None and cf_col in df_f.columns:
        cf_clean = df_f[cf_col].astype(str).str.replace("%", "", regex=False)
        pct_raw = to_numeric_series(cf_clean)
        df_f["pct_cfdna"] = np.where(pct_raw <= 1, pct_raw * 100.0, pct_raw)
    else:
        df_f["pct_cfdna"] = np.nan

    # Derived concentration
    df_f["ng_per_ml"] = np.where(
        df_f["ml_plasma"].gt(0) & df_f["total_ng_dna"].notna(),
        df_f["total_ng_dna"] / df_f["ml_plasma"],
        np.nan
    )

    # Build tidy output
    # Compute per-patient+timepoint MRD status across ALL rows (not only cfDNA), because the MRD
    # result may be recorded on any sample row at that timepoint.
    # IMPORTANT: the 'anonymization' column in this sheet is sample-level (often includes TP and sample_id),
    # so it is NOT a stable patient identifier. We therefore use a stable patient_key derived from names.
    df_all = df.copy()
    df_all[name_col] = df_all[name_col].astype(str).str.lower()
    df_all["timepoint"] = df_all[ttt_col].apply(extract_timepoint)
    df_all = df_all[df_all["timepoint"].notna()].copy()
    if tissue_col is not None and tissue_col in df_all.columns:
        df_all = df_all.loc[df_all[tissue_col].map(_norm) != "lcr"].copy()

    df_all["patient_key"] = df_all[name_col].astype(str).str.strip().str.lower()

    mrd_status_map = None
    if mrd_col is not None and mrd_col in df_all.columns:
        neg_tokens = {t.strip().lower() for t in str(args.mrd_negative_tokens).split(",") if t.strip()}
        missing_tokens = {"", "nan", "none"}

        mrd_raw = df_all[mrd_col].astype(str).str.strip().str.lower().replace({"nan": "", "none": ""})
        df_all["MRD_IgTCR"] = mrd_raw

        def _status_from_values(s: pd.Series) -> str:
            s = s.astype(str).str.strip().str.lower()
            s = s.replace({"nan": "", "none": ""})
            recorded = s[~s.isin(missing_tokens)]
            if recorded.empty:
                return ""
            if recorded.isin(neg_tokens).all():
                return "neg"
            return "pos"

        mrd_status_map = df_all.groupby(["patient_key", "timepoint"], as_index=False).agg(
            MRD_IgTCR_status=("MRD_IgTCR", _status_from_values)
        )

    out = df_f.assign(
        lastname=df_f[name_col],
        patient_key=df_f[name_col].astype(str).str.strip().str.lower(),
        anonymization=(df_f[anon_col] if anon_col is not None and anon_col in df_f.columns else pd.NA),
        genetic_subtype=(
            df_f[genetic_subtype_col]
            if genetic_subtype_col is not None and genetic_subtype_col in df_f.columns
            else pd.NA
        ),
        sample_id=(df_f[sample_id_col] if sample_id_col is not None and sample_id_col in df_f.columns else pd.NA),
        tube=df_f[tube_col] if tube_col is not None and tube_col in df_f.columns else np.nan,
        MRD_IgTCR=(df_f[mrd_col] if mrd_col is not None and mrd_col in df_f.columns else pd.NA),
    )[["lastname", "patient_key", "anonymization", "genetic_subtype", "sample_id", "timepoint", "tube", "ml_plasma", "pct_cfdna", "dosage_ng_per_uL", "total_ng_dna", "ng_per_ml", "MRD_IgTCR"]]

    # Merge MRD status computed across all rows.
    if mrd_status_map is not None and len(mrd_status_map):
        out = out.merge(mrd_status_map, on=["patient_key", "timepoint"], how="left")

    out = out.sort_values(["lastname", "timepoint"], key=lambda s: s.astype(str))

    # Optional debug on timepoints
    if args.print_matches:
        vc = out["timepoint"].value_counts().sort_index()
        print("\nparsed timepoints:")
        for k, v in vc.items():
            print(f"  {k}: {v}")
        missing_vol = out["ml_plasma"].isna().sum()
        missing_ng = out["total_ng_dna"].isna().sum()
        print(f"\nmissing ml_plasma: {missing_vol} | missing total_ng_dna: {missing_ng}")

    # Write outputs
    out.to_csv(args.out_csv, index=False)
    if args.out_parquet:
        out.to_parquet(args.out_parquet, index=False)

    print(f"\nrows written: {len(out)}")
    print(f"excluded rows where tissue == LCR: {excluded_lcr_rows}")
    print(f"saved: {os.path.abspath(args.out_csv)}")
    if args.out_parquet:
        print(f"saved: {os.path.abspath(args.out_parquet)}")

if __name__ == "__main__":
    main()

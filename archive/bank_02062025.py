import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os

# === FILE PATH ===
file_path = "Tableau complet Projet cfDNA.xlsx"

# === DETECT HEADER ROW ===
df_raw = pd.read_excel(file_path, header=None)
header_row = next(
    (i for i in range(10)
     if df_raw.iloc[i].astype(str).str.lower().str.contains("stades").any()),
    0
)

# === LOAD DATA ===
df = pd.read_excel(file_path, header=header_row)
df.columns = [str(col).strip().lower() for col in df.columns]

# === COLUMN IDENTIFIERS ===
name_col   = next(c for c in df.columns if c == "nom")
adn_col    = next(c for c in df.columns if "type d'adn extrait" in c)
ttt_col    = next(c for c in df.columns if "stade de ttt" in c)
tube_col   = next(c for c in df.columns if "anticoagulant pvt initial" in c)
volume_col = next(c for c in df.columns if "volume plasma" in c)
cf_col     = next(c for c in df.columns if "% cf" in c)
ng_col     = next(c for c in df.columns if "quantité total" in c)

allowed_stages = [
    'diag','tp0,5','tp1','tp1,5','tp2','tp3','rechute','après inotuzumab'
]

# === TIMEPOINT NORMALIZATION ===
def extract_timepoint(cell):
    if not isinstance(cell, str):
        return None
    txt = cell.lower().replace(",",".")
    if "diag" in txt:
        return "diag"
    if "rechute" in txt:
        return "rechute"
    if "inotuzumab" in txt:
        return "après inotuzumab"
    m = re.search(r"tp\s*([0-9]+(?:\.[0-9])?)", txt)
    if m:
        val = m.group(1).replace(".",",")
        return f"tp{val}"
    return None

# === FILTER AND PREP ===
df_f = df[
    df[adn_col].astype(str).str.lower().str.contains("cfdna", na=False)
].copy()
df_f[name_col] = df_f[name_col].astype(str).str.lower()
df_f["timepoint"] = df_f[ttt_col].apply(extract_timepoint)
df_f = df_f[df_f["timepoint"].isin(allowed_stages)]

# === NUMERIC COLUMNS ===
df_f["ml plasma"]     = pd.to_numeric(df_f[volume_col], errors="coerce")
df_f["total ng DNA"]  = pd.to_numeric(df_f[ng_col],     errors="coerce")
df_f["ng/ml plasma"]  = df_f.apply(
    lambda r: r["total ng DNA"] / r["ml plasma"]
    if pd.notna(r["total ng DNA"]) and pd.notna(r["ml plasma"]) and r["ml plasma"] > 0
    else np.nan,
    axis=1
)

# === SUMMARY TABLE ===
summary = (
    df_f.groupby("timepoint")
    .agg(
        unique_patient_count    =(name_col,          lambda x: len(set(x))),
        mean_ml_plasma          =("ml plasma",       "mean"),
        mean_total_ng_DNA       =("total ng DNA",    "mean"),
        median_total_ng_DNA     =("total ng DNA",    "median"),
        mean_ng_per_ml          =("ng/ml plasma",    "mean"),
        median_ng_per_ml        =("ng/ml plasma",    "median")
    )
    .reindex(allowed_stages)
    .reset_index()
    .round(2)
)

# === DETAILED TABLE ===
records = []
for _, r in df_f.iterrows():
    ln  = r[name_col]
    tp  = r["timepoint"]
    vol = r["ml plasma"]
    ng  = r["total ng DNA"]
    cfp = pd.to_numeric(r.get(cf_col), errors="coerce") * 100 if pd.notna(r.get(cf_col)) else np.nan

    records.append({
        "lastname":      ln,
        "timepoint":     tp,
        "tube":          r.get(tube_col, np.nan),
        "ml plasma":     vol,
        "% cfDNA":       cfp,
        "total ng DNA":  ng,
        "ng/ml plasma":  ng/vol if pd.notna(ng) and pd.notna(vol) and vol>0 else np.nan
    })

detailed = pd.DataFrame.from_records(records)
detailed = detailed.sort_values(
    by=["lastname","timepoint"], key=lambda c: c.astype(str)
)

# === SAVE TO EXCEL ===
out_excel = "patient_counts_detailed.xlsx"
with pd.ExcelWriter(out_excel, engine='openpyxl') as w:
    summary.to_excel(w, sheet_name='Summary', index=False)
    detailed.to_excel(w, sheet_name='Detailed', index=False)
print(f"✅ Excel saved to: {os.path.abspath(out_excel)}")

# === VIOLIN PLOT OF ALL VALUES COMBINED ===
vals = df_f["ng/ml plasma"].dropna()
plt.figure(figsize=(6,6))
sns.violinplot(y=vals, inner="box", cut=0)
plt.title("Distribution of ng/ml plasma (all cfDNA samples)")
plt.ylabel("ng/ml plasma")
plt.xticks([])  
plt.tight_layout()

out_jpg = "ng_ml_plasma_violin.jpeg"
plt.savefig(out_jpg, format="jpeg")
plt.close()
print(f"🎻 Violin plot saved to: {os.path.abspath(out_jpg)}")

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os
from matplotlib.ticker import LogFormatter
from scipy.stats import ttest_ind

# === STYLE SETTINGS ===
plt.rcParams.update({
    "font.family": "Arial",
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 11
})

# === FILE PATHS ===
file_path = "Tableau complet Projet cfDNA.xlsx"
donor_file = "cfDNA_donors.xlsx"

# === DETECT HEADER ROW ===
df_raw = pd.read_excel(file_path, header=None)
header_row = next(
    (i for i in range(10)
     if df_raw.iloc[i].astype(str).str.lower().str.contains("stades").any()),
    0
)

# === LOAD MAIN DATA ===
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
        "ng/ml plasma":  ng/vol if pd.notna(ng) and pd.notna(vol) and vol > 0 else np.nan
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

# === LOG-SCALE PLOT: INDIVIDUAL POINTS + VALID n COUNT ===
df_donors = pd.read_excel(donor_file, decimal=",")
df_donors.columns = [c.strip().lower() for c in df_donors.columns]
conc_col = next(c for c in df_donors.columns if "conc ng/ml" in c)
df_donors["ng/ml plasma"] = pd.to_numeric(df_donors[conc_col], errors="coerce")
df_donors["timepoint"] = "Control"

df_diag_tp1 = df_f[df_f["timepoint"].isin(["diag", "tp1"])][["timepoint", "ng/ml plasma"]].copy()
df_plot = pd.concat([
    df_donors[["timepoint", "ng/ml plasma"]],
    df_diag_tp1
], ignore_index=True)
df_plot["timepoint"] = pd.Categorical(df_plot["timepoint"], categories=["Control", "diag", "tp1"], ordered=True)

# Filter valid data and count
df_plot_valid = df_plot[df_plot["ng/ml plasma"].notna()]
counts = df_plot_valid["timepoint"].value_counts().to_dict()
label_map = {
    "Control": f"Control (n={counts.get('Control', 0)})",
    "diag": f"Diagnosis (n={counts.get('diag', 0)})",
    "tp1": f"TP1 (n={counts.get('tp1', 0)})"
}

# Plot
plt.figure(figsize=(6.5, 5))
xmap = {"Control": 0, "diag": 1, "tp1": 2}
for label, x in xmap.items():
    yvals = df_plot_valid[df_plot_valid["timepoint"] == label]["ng/ml plasma"]
    plt.scatter([x]*len(yvals), yvals, alpha=0.8)

plt.xticks(
    [0, 1, 2],
    [label_map["Control"], label_map["diag"], label_map["tp1"]]
)
plt.yscale("log")
plt.ylim(1, 1800)
plt.ylabel("ng/ml plasma (log scale)")
plt.title("cfDNA in patients vs healthy donors")
plt.grid(True, which='both', axis='y', linestyle='--', alpha=0.4)
plt.gca().yaxis.set_major_formatter(LogFormatter(labelOnlyBase=True))

plt.tight_layout()
plt.savefig("cfDNA_points_comparison_log.jpeg", format="jpeg", dpi=600)
plt.close()
print(f"📈 Log-scale point plot saved to: {os.path.abspath('cfDNA_points_comparison_log.jpeg')}")

# === T-TESTS BETWEEN GROUPS ===
print("\n=== T-TEST RESULTS ===")
group_data = {
    "Control": df_plot_valid[df_plot_valid["timepoint"] == "Control"]["ng/ml plasma"],
    "Diagnosis": df_plot_valid[df_plot_valid["timepoint"] == "diag"]["ng/ml plasma"],
    "TP1": df_plot_valid[df_plot_valid["timepoint"] == "tp1"]["ng/ml plasma"]
}

for (a, b) in [("Control", "Diagnosis"), ("Control", "TP1"), ("Diagnosis", "TP1")]:
    stat, pval = ttest_ind(group_data[a], group_data[b], equal_var=False)
    if pval < 0.001:
        level = "*** (p < 0.001)"
    elif pval < 0.01:
        level = "** (p < 0.01)"
    elif pval < 0.05:
        level = "* (p < 0.05)"
    else:
        level = "ns (not significant)"
    print(f"{a} vs {b}: t = {stat:.3f}, p = {pval:.4e} → {level}")

#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

def run(cmd, cwd=None):
    print("→", " ".join(map(str, cmd)))
    res = subprocess.run(cmd, cwd=cwd)
    if res.returncode != 0:
        sys.exit(res.returncode)

def main():
    p = argparse.ArgumentParser(description="cfDNA inventory pipeline: parse → analyze")
    p.add_argument("--input", default="cfDNA_inventaire_2025.xlsx", help="source Excel")
    p.add_argument("--donors", default="cfDNA_donors.xlsx", help="donors Excel")
    p.add_argument("--parsed_csv", default="outputs/results/cfdna_parsed.csv", help="output from parser")
    p.add_argument("--parsed_parquet", default=None, help="optional Parquet from parser")
    p.add_argument("--out_excel", default="outputs/results/cfdna_analysis.xlsx", help="analysis workbook (Summary+Detailed)")
    p.add_argument("--plot", default="outputs/results/cfDNA_points_comparison_log.jpeg", help="analysis plot output")
    p.add_argument(
        "--violin_subset",
        default="outputs/results/cfDNA_violin_subset_connected_log_excl_tp0p5.jpeg",
        help="subset violin plot output (Control + selected timepoints; connected per patient)",
    )
    p.add_argument(
        "--violin_subset_unconnected",
        default="outputs/results/cfDNA_violin_subset_log_excl_tp0p5.jpeg",
        help="subset violin plot output without connecting lines (Control + selected timepoints; points only). Use 'none' to disable.",
    )
    p.add_argument(
        "--violin_subset_timepoints",
        default="diag;tp0,5;tp1;tp2",
        help="patient timepoints for subset violin. Prefer ';' as separator (because some timepoints contain ','). Example: 'diag;tp0,5;tp1;tp2'",
    )
    p.add_argument(
        "--violin_subset_connect_lines",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="connect points from the same patient across timepoints in subset violin",
    )
    p.add_argument(
        "--violin_subset_connect_agg",
        default="median",
        choices=["median", "mean", "first"],
        help="aggregation for per-patient subset points/lines when duplicates exist",
    )

    p.add_argument(
        "--pairwise_table",
        default=None,
        help="(optional) output CSV with pairwise statistical comparisons between bins; if omitted only Excel sheet is written",
    )
    p.add_argument(
        "--pairwise_bins",
        default="subset",
        choices=["subset", "all"],
        help="which bins to compare: 'subset' uses Control + violin_subset_timepoints; 'all' uses Control + all patient timepoints",
    )
    p.add_argument(
        "--pairwise_unit",
        default="sample",
        choices=["sample", "patient_median"],
        help="statistical unit: raw samples, or per-patient median within each bin",
    )
    p.add_argument(
        "--pairwise_scale",
        default="log10",
        choices=["log10"],
        help="run tests on log10-transformed values (enforced)",
    )
    p.add_argument(
        "--pairwise_correction",
        default="bh",
        choices=["bh"],
        help="multiple-testing correction across all pairwise comparisons (BH enforced)",
    )

    p.add_argument(
        "--mixed_table",
        default=None,
        help="(optional) output CSV with mixed-effects model timepoint contrasts; if omitted only Excel sheet is written",
    )
    p.add_argument(
        "--mixed_bins",
        default="subset",
        choices=["subset", "all"],
        help="which timepoints to include in the MixedLM: 'subset' uses Control + violin_subset_timepoints; 'all' uses Control + all patient timepoints",
    )
    p.add_argument(
        "--mixed_correction",
        default="bh",
        choices=["bh"],
        help="multiple-comparisons correction for MixedLM contrasts (BH enforced)",
    )

    p.add_argument(
        "--test_outputs_dir",
        default="outputs",
        help="output root directory. Results are written to <root>/results and diagnostics to <root>/diagnostics",
    )

    p.add_argument(
        "--mixed_random_slope_sensitivity",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="run sensitivity MixedLM with random slope over ordered time (patients only)",
    )
    p.add_argument(
        "--mixed_outlier_drop_n",
        type=int,
        default=0,
        help="outlier sensitivity: drop top-N observations by |residual| and refit once (0 disables). Suggested: 1 or 2",
    )
    p.add_argument("--print-matches", action="store_true", help="parser: print matched headers")
    p.add_argument("--skip-parse", action="store_true", help="skip the parse step")
    p.add_argument("--skip-analysis", action="store_true", help="skip the analysis step")
    # --force kept for backward-compat, but parse always overwrites now
    p.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    parse_script = base / "parse.py"
    analyze_script = base / "analysis.py"

    if not args.skip_parse and not parse_script.exists():
        sys.exit(f"missing: {parse_script}")
    if not args.skip_analysis and not analyze_script.exists():
        sys.exit(f"missing: {analyze_script}")

    # step 1 — parse (always overwrite)
    if not args.skip_parse:
        cmd = [
            sys.executable, str(parse_script),
            "--input", args.input,
            "--out_csv", args.parsed_csv,
        ]
        if args.parsed_parquet:
            cmd += ["--out_parquet", args.parsed_parquet]
        if args.print_matches:
            cmd += ["--print_matches"]
        run(cmd, cwd=str(base))

    # step 2 — analyze
    if not args.skip_analysis:
        cmd = [
            sys.executable, str(analyze_script),
            "--parsed", args.parsed_csv,
            "--donors", args.donors,
            "--out_excel", args.out_excel,
            "--plot", args.plot,
            "--violin_subset", args.violin_subset,
            "--violin_subset_unconnected", args.violin_subset_unconnected,
            "--violin_subset_timepoints", args.violin_subset_timepoints,
            "--violin_subset_connect_agg", args.violin_subset_connect_agg,
            "--pairwise_bins", args.pairwise_bins,
            "--pairwise_unit", args.pairwise_unit,
            "--pairwise_scale", args.pairwise_scale,
            "--pairwise_correction", args.pairwise_correction,
            "--mixed_bins", args.mixed_bins,
            "--mixed_correction", args.mixed_correction,
            "--test_outputs_dir", args.test_outputs_dir,
            "--mixed_outlier_drop_n", str(args.mixed_outlier_drop_n),
        ]
        if args.mixed_random_slope_sensitivity:
            cmd += ["--mixed_random_slope_sensitivity"]
        if args.pairwise_table:
            cmd += ["--pairwise_table", args.pairwise_table]
        if args.mixed_table:
            cmd += ["--mixed_table", args.mixed_table]
        if not args.violin_subset_connect_lines:
            cmd += ["--no-violin_subset_connect_lines"]
        run(cmd, cwd=str(base))

    print("✓ pipeline completed")

if __name__ == "__main__":
    main()

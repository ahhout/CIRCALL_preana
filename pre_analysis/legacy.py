#!/usr/bin/env python3
"""Run the existing pre-analysis workflows with explicit inputs and isolated outputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RETROSPECTIVE_COLUMNS = {
    "patient_key", "sample_id", "timepoint", "ml_plasma",
    "dosage_ng_per_uL", "total_ng_dna", "ng_per_ml",
}
CIRCALL_COLUMNS = {
    "circall_id", "sample_id", "timepoint", "compartment", "volume",
    "elution_uL", "dosage_ng/uL", "dosage_ng_total", "dosage_ng/mL_plasma",
}


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def validate_workbook(path, *, sheet=None, columns=()):
    """Validate workbook structure without displaying any patient records."""
    from openpyxl import load_workbook

    if not path.is_file():
        raise ValueError(f"Workbook not found: {path}")
    try:
        book = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        raise ValueError(f"Cannot read Excel workbook: {path}") from None
    try:
        if sheet and sheet not in book.sheetnames:
            raise ValueError(f"Missing required sheet: {sheet}")
        worksheet = book[sheet] if sheet else book.active
        first = next(worksheet.iter_rows(values_only=True), None)
        if not first:
            raise ValueError(f"Empty worksheet in {path.name}")
        if columns:
            headers = {str(value).strip() for value in first if value is not None}
            missing = set(columns) - headers
            if missing:
                raise ValueError(f"Missing required columns in {path.name}: {', '.join(sorted(missing))}")
    finally:
        book.close()


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "retrospective", "bilan"), default="all")
    parser.add_argument("--inventory", type=Path, default=ROOT / "data/retrospective/cfDNA_inventaire_2025.xlsx")
    parser.add_argument("--donors", type=Path, default=ROOT / "data/retrospective/cfDNA_donors.xlsx")
    parser.add_argument("--circall", type=Path, default=ROOT / "data/circall/inventaire_CIRCALL_ano_07092026.xlsx")
    parser.add_argument("--retrospective-workbook", type=Path, help="Required for bilan-only runs")
    parser.add_argument("--output-dir", type=Path, help="New or empty directory; default: outputs/<UTC timestamp>")
    parser.add_argument("--mixed-random-slope-sensitivity", action="store_true", help="Existing optional random-slope diagnostic")
    parser.add_argument("--mixed-outlier-drop-n", type=int, default=0, help="Existing optional outlier diagnostic; 0 disables")
    args = parser.parse_args(argv)
    if args.stage == "bilan" and args.retrospective_workbook is None:
        parser.error("--stage bilan requires --retrospective-workbook")
    if args.stage != "bilan" and args.retrospective_workbook is not None:
        parser.error("--retrospective-workbook is only used with --stage bilan")
    if args.mixed_outlier_drop_n < 0:
        parser.error("--mixed-outlier-drop-n must be nonnegative")
    if args.stage == "bilan" and (args.mixed_random_slope_sensitivity or args.mixed_outlier_drop_n):
        parser.error("Sensitivity options require a retrospective stage")
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.expanduser().resolve())
    if args.output_dir is None:
        args.output_dir = ROOT / "outputs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return args


def prepare_output(path):
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"Output directory must be new or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def save_manifest(path, manifest):
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")


def execute_stage(name, command, expected, *, output, manifest):
    entry = {"stage": name, "command": list(map(str, command)), "status": "running"}
    manifest["stages"].append(entry)
    save_manifest(output / "run_manifest.json", manifest)
    print(f"Running {name}", flush=True)
    log_path = output / "logs" / f"{name}.log"
    log_path.parent.mkdir(exist_ok=True)
    arguments_path = log_path.with_suffix(".arguments.json")
    try:
        with log_path.open("w") as log:
            result = subprocess.run(
                entry["command"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, "MPLBACKEND": "Agg", "PRE_ANALYSIS_ARGUMENTS_FILE": str(arguments_path)}, check=False,
            )
        entry["returncode"] = result.returncode
        if result.returncode:
            raise RuntimeError(f"{name} failed (exit {result.returncode}); see {log_path}")
        missing = [str(path.relative_to(output)) for path in expected if not path.is_file() or path.stat().st_size == 0]
        if missing:
            raise RuntimeError(f"{name} did not produce required artifacts: {', '.join(missing)}")
        entry["status"] = "complete"
    except Exception:
        entry["status"] = "failed"
        raise
    finally:
        if arguments_path.is_file():
            entry["effective_arguments"] = json.loads(arguments_path.read_text())
        save_manifest(output / "run_manifest.json", manifest)


def workflow_steps(args):
    output = args.output_dir
    ret = ROOT / "workflows/retrospective"
    bil = ROOT / "workflows/bilan"
    r = output / "retrospective/results"
    b = output / "bilan"
    def command(script, *options):
        return [sys.executable, str(script), *map(str, options)]
    if args.stage != "bilan":
        yield "parse", command(ret / "parse.py", "--input", args.inventory, "--out_csv", r / "cfdna_parsed.csv"), [r / "cfdna_parsed.csv"]
        options = ["--parsed", r / "cfdna_parsed.csv", "--donors", args.donors,
                   "--test_outputs_dir", output / "retrospective",
                   "--mixed_outlier_drop_n", args.mixed_outlier_drop_n]
        if args.mixed_random_slope_sensitivity:
            options.append("--mixed_random_slope_sensitivity")
        expected = [r / name for name in (
            "cfdna_analysis.xlsx", "cfDNA_pairwise_bins_stats_log10_bh.csv",
            "cfDNA_mixedlm_timepoint_contrasts_log10_bh.csv",
            "cfDNA_points_comparison_log.jpeg", "cfDNA_violin_log.jpeg",
            "cfDNA_violin_total_ng_log.jpeg",
            "cfDNA_violin_subset_connected_log_excl_tp0p5_by_genetic_subtype.jpeg",
            "cfDNA_violin_subset_log_excl_tp0p5_by_genetic_subtype.jpeg",
        )]
        expected.extend(output / "retrospective/diagnostics/mixedlm" / name for name in (
            "mixedlm_resid_qq.png", "mixedlm_resid_vs_fitted.png", "mixedlm_random_effects_hist.png",
        ))
        if args.mixed_random_slope_sensitivity:
            expected.append(r / "cfDNA_mixedlm_random_slope_time_contrasts_log10_bh.csv")
        if args.mixed_outlier_drop_n:
            for suffix in ("removed_observations", "contrasts", "contrasts_vs_base"):
                expected.append(r / f"cfDNA_mixedlm_outlier_drop{args.mixed_outlier_drop_n}_{suffix}.csv")
        yield "analysis", command(ret / "analysis.py", *options), expected
        yield "report", command(ret / "summarize_test_outputs.py", "--parsed", r / "cfdna_parsed.csv",
                                "--donors", args.donors, "--outputs_dir", output / "retrospective",
                                "--mixed_outlier_drop_n", args.mixed_outlier_drop_n), [r / "final_stats_report.xlsx"]
    if args.stage == "retrospective":
        return
    workbook = args.retrospective_workbook if args.stage == "bilan" else r / "cfdna_analysis.xlsx"
    missing_names = ["missing_samples_by_hospital_timepoint.csv", "missing_samples_bias_summary.png",
                     "missing_samples_by_hospital_compartment.csv", "missing_samples_compartment_summary.png"]
    options = []
    for flag, name in zip(("--output", "--table-output", "--compartment-output", "--compartment-table-output"), missing_names):
        options.extend((flag, b / name))
    yield "missing_samples", command(bil / "summarise_missing_samples.py", args.circall, *options), [b / name for name in missing_names]
    yield "csf", command(bil / "summarise_csf_volumes.py", args.circall, "--output", b / "csf_volume_summary.csv",
                         "--plot-output", b / "csf_volume_violin.png"), [b / "csf_volume_summary.csv", b / "csf_volume_violin.png"]
    yield "dosage", command(bil / "summarise_plasma_dosage.py", args.circall, "--retrospective-workbook", workbook,
                            "--output", b / "plasma_dosage_circall_vs_retrospective.csv",
                            "--plot-output", b / "plasma_dosage_violin.png"), [b / "plasma_dosage_circall_vs_retrospective.csv", b / "plasma_dosage_violin.png"]
    plots = [f"circall_{pair}.png" for pair in (
        "plasma_volume_vs_dosage_ng_per_uL",
        "plasma_volume_vs_dosage_ng_total", "elution_volume_vs_dosage_ng_per_uL",
        "elution_volume_vs_dosage_ng_total", "elution_volume_vs_dosage_ng_per_mL_plasma",
    )] + [f"retrospective_plasma_volume_vs_dosage_{unit}.png" for unit in ("ng_per_uL", "ng_total")]
    yield "correlations", command(bil / "analyse_plasma_volume_elution_dosage.py", args.circall,
                                  "--retrospective-workbook", workbook, "--output", b / "plasma_volume_elution_dosage_correlations.csv",
                                  "--plot-output-dir", b), [b / "plasma_volume_elution_dosage_correlations.csv", *[b / name for name in plots]]


def main(argv=None):
    args = arguments(argv)
    inputs = {}
    try:
        if args.stage != "bilan":
            inputs.update(inventory=args.inventory, donors=args.donors)
            for path in inputs.values():
                validate_workbook(path)
        if args.stage != "retrospective":
            inputs["circall"] = args.circall
            validate_workbook(args.circall, sheet="cohorte_lal", columns=CIRCALL_COLUMNS)
        if args.stage == "bilan":
            inputs["retrospective_workbook"] = args.retrospective_workbook
            validate_workbook(args.retrospective_workbook, sheet="Detailed", columns=RETROSPECTIVE_COLUMNS)
        prepare_output(args.output_dir)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
        "code_revision": git.stdout.strip() if git.returncode == 0 else None,
        "code_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in [ROOT / "run.py", *sorted((ROOT / "workflows").rglob("*.py")), *sorted((ROOT / "pre_analysis").glob("*.py"))]},
        "python": sys.version, "executable": sys.executable,
        "environment_lock_sha256": sha256(ROOT / "conda-linux-64.lock"),
        "arguments": vars(args),
        "inputs": {key: {"path": str(path), "sha256": sha256(path)} for key, path in inputs.items()},
        "stages": [],
    }
    try:
        for name, command, expected in workflow_steps(args):
            execute_stage(name, command, expected, output=args.output_dir, manifest=manifest)
            if name == "analysis" and args.stage == "all":
                validate_workbook(args.output_dir / "retrospective/results/cfdna_analysis.xlsx", sheet="Detailed", columns=RETROSPECTIVE_COLUMNS)
        manifest["status"] = "complete"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        print(f"Error: {error}", file=sys.stderr)
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_manifest(args.output_dir / "run_manifest.json", manifest)
    if manifest["status"] != "complete":
        return 1
    print(f"Completed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

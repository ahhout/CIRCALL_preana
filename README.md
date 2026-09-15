cfDNA_inventory — pipeline README

Overview

This repository parses a cfDNA inventory Excel, produces publication-ready plots, and runs statistical analyses comparing healthy donors (controls) and patient timepoints. The pipeline is designed for reproducibility: outputs are written under a single `outputs/` root, statistics are run on log10(cfDNA) with BH correction, and sensitivity diagnostics (random-slope and outlier-drop) are included.

Quick summary

- Parse source Excel -> tidy CSV: outputs/results/cfdna_parsed.csv
- Analyze: plots, pairwise Welch tests (descriptive), mixed-effects model contrasts (primary), diagnostics -> outputs/results/ and outputs/diagnostics/
- Consolidated report: outputs/results/final_stats_report.xlsx

Prerequisites

- Linux workstation (tested here)
- Conda with the environment defined in `env.yml` (use conda only per repository conventions)

Install the environment

```bash
conda env create -f env.yml -n cfDNA_inventory
conda activate cfDNA_inventory
```

Quick run (end-to-end)

```bash
# parse -> analyze -> summarize using the default inputs in this repo
conda run -n cfDNA_inventory python main.py --test_outputs_dir outputs
conda run -n cfDNA_inventory python summarize_test_outputs.py --outputs_dir outputs
```

Files and scripts

- `main.py` — high-level pipeline driver (parse → analyze); accepts CLI flags to control parsing, analysis, and outputs root.
- `parse.py` — robust Excel parser that auto-detects messy headers and extracts `ng_per_ml` and `timepoint` into a tidy CSV.
- `analysis.py` — plotting and statistics orchestrator that writes:
  - results (tables + plots) to [outputs/results](outputs/results)
  - diagnostics (assumption + sensitivity plots) to [outputs/diagnostics](outputs/diagnostics)
- `stats_reporting.py` — statistical routines (pairwise Welch tests on log10 with BH; MixedLM contrasts on log10 with BH; diagnostics and sensitivity helpers).
- `summarize_test_outputs.py` — builds `final_stats_report.xlsx` in [outputs/results](outputs/results) that contains the primary MixedLM table, pairwise checks, paired counts, and sensitivity columns.

Outputs layout (what to expect)

- outputs/results/
  - `cfdna_parsed.csv` — tidy parsed observations (patient samples)
  - `cfdna_analysis.xlsx` — Summary + Detailed workbook
  - `cfDNA_pairwise_bins_stats_log10_bh.csv` — Welch (sample-level) descriptive comparisons
  - `cfDNA_mixedlm_timepoint_contrasts_log10_bh.csv` — MixedLM contrasts (primary inferential table)
  - `final_stats_report.xlsx` — consolidated report (PrimaryMixed, AllMixed, PairwiseSample, PairwisePatientMedian, PairedCounts, TimepointCounts)
  - PNG/JPEG plotting artifacts (violin + scatter plots)
- outputs/diagnostics/
  - `pairwise_log10/` — per-bin histogram + Q–Q plots (log10 distribution checks)
  - `mixedlm/` — residual Q–Q, residual vs fitted, random-intercept histogram
  - `mixedlm_sensitivity/` — random-slope + outlier-drop diagnostic plots when enabled

Statistical choices & interpretation notes

- All inferential tests are run on `log10(ng_per_ml)`.
- Multiple-testing correction uses Benjamini–Hochberg (BH) throughout.
- Primary inference: mixed-effects model (`MixedLM`) with `log10_cfdna ~ 0 + C(timepoint)` and a random intercept per patient. Pairwise contrasts from that model (with CI and fold-change) are the preferred results.
- Pairwise Welch t-tests are kept as descriptive cross-checks; prefer the `PairwisePatientMedian` sheet (per-patient medians) when you want to avoid pseudo-replication.
- Sensitivity checks included by pipeline:
  - Random-slope time sensitivity: `(1 + ordered_time | patient)` as a qualitative trend check (not primary inference).
  - Outlier-drop sensitivity: drop the top-N observations by absolute residual and refit once; outputs removed samples and contrast deltas.

Practical recommendations (for reporting)

- Use `PrimaryMixed` (sheet in `final_stats_report.xlsx`) as the result table for manuscripts.
- Mark `tp0,5` contrasts as exploratory if paired support is small — consult `PairedCounts`.
- Keep sensitivity outputs in appendices; do not remove observations from main results unless there is a documented data-quality reason.

Running with custom options

- To change the outputs root (default `outputs/`):

```bash
python main.py --test_outputs_dir my_outputs
python summarize_test_outputs.py --outputs_dir my_outputs
```

- To enable sensitivity checks during analysis (within `analysis.py` / `main.py`):
  - `--mixed_random_slope_sensitivity` (boolean flag)
  - `--mixed_outlier_drop_n N` (integer; suggested 1–2)

Reproducibility / provenance

- The pipeline logs and Excel workbook contain the summary and detailed tables.
- The `env.yml` file tracks the Conda environment used to run analyses; recreate it for reproducibility.
- The `final_stats_report.xlsx` puts the primary table and sensitivity columns side-by-side for traceability.

Data safety and sharing

- `outputs/results/*` and `outputs/diagnostics/*` may contain patient identifiers (the outlier removal CSV contains `patient` and `sample_id`). Before sharing, either remove or redact identifying columns.
- The repository `.gitignore` currently excludes common binary outputs (CSV/XLSX/PNG/JPEG); keep outputs out of git by default.

Developer notes

- Code is structured so statistical logic lives in `stats_reporting.py` and IO/plot orchestration in `analysis.py`.
- If you change thresholds or add alternative corrections, update `stats_reporting.py` and re-run the pipeline; avoid silent parameter changes — prefer CLI flags.

Troubleshooting

- MixedLM can show warnings about singular random-effect covariances; these are handled by optimizer fallbacks but inspect diagnostics (`outputs/diagnostics/mixedlm`) and consider simplifying random structure if warnings persist.
- If `parse.py` fails to auto-detect columns for donors, open `cfDNA_donors.xlsx` and ensure a numeric concentration column exists; `parse.py` and `summarize_test_outputs.py` use heuristics to find it.

Contact / next steps

- If you want, I can (1) add a de-identification utility that strips patient/sample IDs from sensitivity outputs, (2) add a small README under `outputs/` summarizing the recent run, or (3) produce publication-ready CSVs with selected columns.

License / attribution

- No license file is included. If this repository will be shared externally, add an appropriate `LICENSE` file and ensure donor data sharing policies are followed.

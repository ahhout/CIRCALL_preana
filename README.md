# Pre-analysis

Retrospective cfDNA inventory analysis and CIRCALL inventory summaries in one repository. The original calculations remain in two script-based workflows. The runner explicitly passes the retrospective analysis workbook to the CIRCALL comparison scripts.

## Environment

Use Conda. Recreate the recorded Linux environment with:

```bash
conda create --name pre_analysis --file conda-linux-64.lock
conda activate pre_analysis
```

Alternatively, `conda env create -f env.yml` resolves the same declared dependencies using currently available versions; use the lock file for migration-equivalent results. Optional Parquet export still requires an additional Parquet engine, as in the original project; it is not used by the default pipeline.

## Inputs and local files

The local migration copied these inputs without changing their contents:

| Input | Repository-relative location |
| --- | --- |
| Retrospective inventory | `data/raw/retrospective/cfDNA_inventaire_2025.xlsx` |
| Healthy donors | `data/raw/retrospective/cfDNA_donors.xlsx` |
| CIRCALL inventory | `data/raw/circall/inventaire_CIRCALL_ano_07092026.xlsx` |

`data/` and `outputs/` are ignored by Git. A code-only clone needs its own copies of the input workbooks. Historical workbooks and auxiliary files are under `data/archive/<source-project>/`; historical results are under `outputs/legacy/<source-project>/`. These historical outputs are not used as inputs by a full run. Caches and Excel lock files were not migrated.

## Run the complete workflow

From the repository:

```bash
conda run --no-capture-output -n pre_analysis python run.py
```

This creates a fresh `outputs/<UTC-timestamp>/` directory and runs:

1. Retrospective inventory parsing.
2. Retrospective plots, statistics, and diagnostics.
3. Consolidated statistical workbook.
4. Missing-sample summaries, CSF volumes, plasma dosage comparisons, and volume/dosage correlations.

Inputs can be overridden with `--inventory`, `--donors`, and `--circall`. Default input locations are relative to the repository; explicit relative paths are resolved from the directory where the command is invoked. The runner can therefore also be invoked by its absolute path from elsewhere.

```bash
python run.py --output-dir outputs/my_run
python run.py --inventory /path/to/inventory.xlsx --donors /path/to/donors.xlsx --circall /path/to/circall.xlsx
python run.py --stage retrospective --output-dir outputs/retrospective_run
python run.py --stage bilan \
  --retrospective-workbook outputs/retrospective_run/retrospective/results/cfdna_analysis.xlsx \
  --output-dir outputs/bilan_run
```

A custom output destination must be new or empty. The runner refuses reuse, stops on a failed stage or missing required artifact, and leaves incomplete results available for inspection. Choose a new directory to retry. In `all` mode, both comparison scripts always receive the workbook generated in that run. Bilan-only runs require an explicit workbook.

## Outputs and provenance

```text
outputs/<run-id>/
  retrospective/
    results/
      cfdna_parsed.csv
      cfdna_analysis.xlsx
      final_stats_report.xlsx
      ... statistical CSVs and plots
    diagnostics/
      pairwise_log10/
      mixedlm/
      ... optional sensitivity diagnostics
  bilan/
    ... five summary CSVs and eleven plots
  logs/
    ... per-stage logs and resolved arguments
  run_manifest.json
```

The retrospective workbook's `Detailed` sheet is the interface to bilan. It preserves `patient_key`, `sample_id`, `timepoint`, `ml_plasma`, `dosage_ng_per_uL`, `total_ng_dna`, and `ng_per_ml`, along with existing additional columns. The runner validates the CIRCALL `cohorte_lal` headers and the workbook handoff.

The manifest records input SHA-256 hashes, resolved runner and stage arguments, commands, code revision and file hashes, Python executable/version, environment-lock hash, timestamps, and stage outcomes. Logs report aggregate volume diagnostics without patient names. Data tables and figures can contain clinical identifiers and remain local and Git-ignored.

## Scientific behaviour

Both original parsers remain in use. Cohort membership, units, timepoint mappings, missing-value rules, and filters are preserved; samples are not newly joined across cohorts. The retrospective parser retains its existing LCR exclusion and MRD parsing rules. Bilan retains its compartment-specific selection and existing timepoint exclusions.

Retrospective inference remains on log10 concentration with BH correction and the existing patient random-intercept MixedLM. Sample-level Welch comparisons, patient-median checks, Mann–Whitney summaries, plots, and diagnostics remain available. The default statistical subset includes `diag;tp0,5;tp1;tp2`; the subset violin plots exclude `tp0,5`, as before. MRD status continues to control the existing point markers.

Sensitivity analyses remain opt-in:

```bash
python run.py --mixed-random-slope-sensitivity --mixed-outlier-drop-n 2
```

`--mixed-outlier-drop-n` defaults to `0` (disabled). It only controls the existing sensitivity refit, not the primary analysis. The report now selects the matching requested outlier count instead of assuming 2. The individual report CLI retains its legacy default of 2 when no count is supplied. Model convergence warnings should be assessed in the diagnostic logs; a missing required model result makes the combined run fail.

## Individual scripts

Scripts remain under `workflows/retrospective/` and `workflows/bilan/`, with their existing CLI options. Use `--help` for all analysis settings. Direct-script defaults write to `outputs/manual/retrospective/` or `outputs/manual/bilan/`; they retain legacy overwrite behaviour, so use the runner for isolated runs.

```bash
python workflows/retrospective/main.py --test_outputs_dir outputs/manual/retrospective
python workflows/retrospective/summarize_test_outputs.py --outputs_dir outputs/manual/retrospective
python workflows/bilan/summarise_missing_samples.py data/raw/circall/inventaire_CIRCALL_ano_07092026.xlsx
python workflows/bilan/summarise_csf_volumes.py data/raw/circall/inventaire_CIRCALL_ano_07092026.xlsx
python workflows/bilan/summarise_plasma_dosage.py --retrospective-workbook outputs/manual/retrospective/results/cfdna_analysis.xlsx
python workflows/bilan/analyse_plasma_volume_elution_dosage.py --retrospective-workbook outputs/manual/retrospective/results/cfdna_analysis.xlsx
```

The retrospective output-root option now redirects every default artifact, including parsed data and all plots. Explicit per-file overrides remain supported. Bilan's standalone workbook autodetection is limited to non-temporary workbooks in `data/raw/circall`; multiple candidates require an explicit input.

## Validation

Synthetic tests create temporary workbooks and require no clinical data:

```bash
conda run --no-capture-output -n pre_analysis python -m unittest discover -s tests -v
```

To compare fresh outputs against isolated source runs:

```bash
python tests/compare_outputs.py \
  --baseline-retrospective /path/to/baseline/cfDNA_inventory/outputs \
  --baseline-bilan /path/to/baseline/bilan/output \
  --candidate outputs/my_run \
  --report outputs/comparison.json
```

Comparison checks filenames, ordered sheets/columns/rows and categorical values, numeric values with `rtol=1e-9, atol=1e-12`, and exact image pixels. Failure reports contain filenames rather than patient records. See [MIGRATION.md](MIGRATION.md) for validation evidence and rollback.

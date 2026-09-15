# Pre-analysis

One canonical preparation and analysis workflow for retrospective and CIRCALL patient cohorts. Each cohort is analysed separately against a pooled reference of existing donors and pediatric CIRCALL controls. The primary endpoint is **unadjusted total extracted DNA divided by initial plasma volume**.

## Setup

Use the existing Conda environment, or recreate the locked Linux environment:

```bash
conda create --name pre_analysis --file conda-linux-64.lock
conda activate pre_analysis
```

`conda env create -f env.yml` is an alternative that resolves currently available dependency versions. The unchanged lock file is preferred for reproducing the migration validation.

## Canonical inputs

| Source | Default file | Sheet |
| --- | --- | --- |
| Retrospective patients | `cfDNA_inventaire_retrospective.xlsx` in the repository root | `Inventaire` |
| CIRCALL patients | `inventaire_CIRCALL_15092026.xlsx` in the repository root | `cohorte_lal` |
| Pediatric controls | Same CIRCALL file | `cohorte_control` |
| Existing donors | `data/retrospective/cfDNA_donors.xlsx` | First worksheet |

Workbooks and results remain Git-ignored. A code-only clone needs these local input files. Both control sources are prepared even when selecting a single patient cohort.

## Run

From the repository:

```bash
conda run --no-capture-output -n pre_analysis python run.py
```

Canonical mode, both cohorts, and all investigations are the defaults. Other examples:

```bash
python run.py --cohort circall
python run.py --analysis inventory
python run.py --analysis volumes --output-dir outputs/volume_review
python run.py --analysis yield
python run.py --analysis longitudinal --mixed-outlier-drop-n 2
python run.py --analysis longitudinal --mixed-random-slope-sensitivity
python run.py --inventory /path/to/retrospective.xlsx --circall /path/to/circall.xlsx --donors /path/to/donors.xlsx
```

`--analysis` accepts `all`, `inventory`, `volumes`, `yield`, or `longitudinal`. `--cohort` accepts `all`, `retrospective`, or `circall`. Sensitivity options require `all` or `longitudinal`.

Defaults are resolved relative to the repository. Explicit relative paths are resolved from the caller's directory, so the runner also works when invoked by absolute path from elsewhere. The default output is a fresh `outputs/<UTC timestamp>/`; an explicit output directory must be new or empty.

## Preparation and QC rules

The canonical Excel reader loads cached cell values and formula metadata without changing or recalculating the source workbooks. Header mappings are explicit and duplicate/missing required headers fail clearly.

Retrospective tube rows are expanded into compartment records. Their `MNC_*` fields produce a linked cell/pellet record with assay-specific quantities; plasma volume is never copied into that record. Source tissue, extraction type, original measurement cells, and source-row references are retained. The different MNC assays are not silently collapsed into a generic concentration. CIRCALL compartment rows retain their existing organisation. Known-patient scheduled rows remain in inventory; empty template people do not become patients.

The endpoint is computed from `dna_total_ng / volume_ml` for plasma records with usable total DNA and positive volume. Existing donors use their supplied ng/mL endpoint. `cfDNA_fraction` remains a 0–1 fraction and does not multiply the primary endpoint. Percentage-adjusted `cfDNA_*` values are retained as additional measurements.

Numeric parsing follows CIRCALL conventions: decimal commas and scientific notation are accepted; units, qualifiers, nonfinite numbers, missing markers, and technician notes such as `SK` are not converted into exact measurements. No arbitrary characters are stripped to extract a number.

| Condition | Behaviour |
| --- | --- |
| Formula-generated zero total with missing concentration/elution | Total and its dependent ng/mL are unavailable |
| Numeric zero with valid inputs | Retained; question-specific log rules determine eligibility |
| Missing/nonpositive plasma volume | ng/mL unavailable; usable total DNA and concentration remain available |
| Expected Excel errors | Affected measurements unavailable, without a discrepancy hold |
| Contradictory numeric total or ng/mL | Record held from quantitative analyses; inventory and discrepancy record retained |

QC compares total DNA with concentration × elution and recorded ng/mL with total DNA ÷ volume using `rtol=1e-9`, `atol=1e-12`. It does not invent missing operands or edit source values. Formula metadata and raw mapped measurements are available for review.

Patient grouping preserves the existing within-cohort identity basis. Internal patient keys include a source namespace and a digest, keeping names out of tables and logs. These are internal pseudonymous keys, not a claim of anonymisation. Source sample identifiers and clinical measurements remain local.

## Investigations

| Investigation | Outputs and behaviour |
| --- | --- |
| Inventory | Coverage by cohort, compartment, hospital, and timepoint; unique patients/samples; distinct present, na-coded, and blank IDs |
| Volumes | Overall and per-timepoint counts, sums, mean, sample SD, quartiles, range, and compartment figures for recorded fluid, blood, elution, and MNC counts |
| Yield | Unadjusted plasma concentration/yield summaries; side-by-side cohort means/medians and descriptive differences; separate MNC assay summaries; all five existing volume/elution correlation pairs for each cohort |
| Longitudinal | Sample and patient-median Welch checks, patient-median Mann–Whitney, separate patient random-intercept MixedLM fits, paired counts, diagnostic figures, and subtype/MRD-marked plots |

Inventory coverage is independent of measurement availability. CIRCALL missingness rates use explicit `na` IDs divided by nonblank assessed IDs, as before. No retrospective expected-collection denominator is inferred. Distinct inventory records, samples, and patients are reported separately.

Retrospective quantitative plasma analyses retain the cfDNA extraction and parsed-timepoint rules. Sample IDs remain optional for retrospective longitudinal analyses and required for dosage/correlations. CIRCALL dosage/correlation/longitudinal analyses require a present sample ID and timepoint. Retrospective correlations retain the post-inotuzumab exclusion. All policies are recorded in the run manifest.

Model timepoints remain `diag;tp0,5;tp1;tp2` for retrospective patients and `diag;d4;d8;d15;tp1;tp2` for CIRCALL. Retrospective subset plots still omit `tp0,5`; those observations remain in the statistical model. No day/TP equivalence is inferred. Subtype source labels are retained; case-only variants share a display colour. Different spellings/languages are not assigned new biological annotations.

Methods retain existing transformations: positive log10 concentrations for inference, log10(1+x) descriptive violins, log10 concentration or log10(1+total DNA) for correlations. Overall correlations require 3 pairs and timepoint-specific correlations 5; unavailable/constant groups are labelled explicitly. BH correction remains within each cohort/test family. The descriptive cohort-comparison table matches timepoint labels only and does not assert equivalent collection windows. No new cross-cohort model or cross-cohort hypothesis test is introduced. Cross markers denote controls or postdiagnosis MRD-negative observations; CIRCALL patient markers do not infer MRD status.

Sensitivity analyses are opt-in. Outlier-drop refits retain the requested count. Random-slope sensitivity uses the legacy numeric TP scale for the retrospective cohort; CIRCALL is explicitly unavailable because no common numeric mapping of its day and TP labels has been agreed. CIRCALL MRD annotations are also unavailable: assay availability fields are not MRD results.

## Results and provenance

```text
outputs/<run-id>/
  prepared/
    inventory.csv
    pooled_controls.csv
    measurement_availability.csv
    discrepancies.csv
    eligibility.csv
    endpoint_basis.csv
    reconciliation.json
    summary.json
    source_mappings.json
    source_headers.json
  inventory/                # CSV, Excel, coverage figure
  volumes/                  # summaries and compartment figures
  yield/                    # summaries, both cohorts' correlations and figures
  longitudinal/
    retrospective/          # statistics workbook, CSVs, diagnostics
    circall/                # statistics workbook, CSVs, diagnostics
    subtypes.png
    trajectories.png
  analysis_status.csv
  run_manifest.json
  logs/
```

The manifest contains input hashes, runtime code hashes/revision, environment-lock hash, effective arguments, policies, stages, and analysis outcomes. `reconciliation.json` explains the intentional measurement-basis, control-pooling, parsing, and missingness changes. `endpoint_basis.csv` compares unadjusted and percentage-adjusted quantities within the current sources; it is not presented as an old-versus-new file comparison.

An unsupported analysis is labelled `unavailable`. A failed model is labelled `failed` and causes a nonzero overall exit, while the other cohort can still finish. Convergence and small-sample warnings remain in the logs. Inspect paired counts and diagnostics when interpreting results.

## Legacy mode and rollback

```bash
python run.py --workflow legacy
python run.py --workflow legacy --stage retrospective --output-dir outputs/legacy_ret
python run.py --workflow legacy --stage bilan \
  --retrospective-workbook outputs/legacy_ret/retrospective/results/cfdna_analysis.xlsx
```

Legacy mode uses the preserved old workbooks under `data/retrospective/` and `data/circall/`, with the old scripts, output layout, and calculations. `--stage` and `--retrospective-workbook` belong to legacy mode; `--cohort` and `--analysis` belong to canonical mode. Individual legacy scripts remain runnable with their existing flags; direct-script defaults retain legacy overwrite behaviour.

Rollback is an explicit legacy-mode invocation or reversal of the canonical-default commit. The original projects and historical results remain intact. [MIGRATION.md](MIGRATION.md) records the earlier repository merge; [CANONICAL_VALIDATION.md](CANONICAL_VALIDATION.md) records reconciliation validation.

## Tests

```bash
conda run --no-capture-output -n pre_analysis python -m unittest discover -s tests -v
python tests/validate_canonical.py --run-dir outputs/canonical_validation/release_final
```

Unit tests use synthetic data. The second command is a migration-specific integration audit against the current source workbooks, including the five corrected samples and thirteen identified formula-zero records. It requires the local source files and validation hash snapshot; future source revisions can legitimately require updated migration expectations.

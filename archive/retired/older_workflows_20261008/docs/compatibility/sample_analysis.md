# Canonical compatibility analysis

This is the retained `canonical` compatibility guide. Select the former combined
run explicitly with `python run.py --config configs/pipeline_all.json`; plain
`python run.py` now runs Layers 1–4. The [coverage map](../replacement_coverage.md)
identifies capabilities retained here pending validated layered migration.

This guide describes the canonical preparation and analysis workflow for retrospective and CIRCALL patient cohorts. Each cohort is modelled separately; existing donors and pediatric CIRCALL controls form a descriptive reference only. Its primary endpoint is **unadjusted total extracted DNA divided by initial plasma volume**. The independent `cfdna_associations` workflow uses the recorded cfDNA endpoint and retains its own preparation; see the [project workflow guide](../layers/advanced_analysis.md).

Environment setup is maintained in [README](../../README.md#setup).

## Canonical inputs

| Source | Default file | Sheet |
| --- | --- | --- |
| Retrospective patients | `input/cfDNA_inventaire_retrospective.xlsx` | `Inventaire` |
| CIRCALL patients | Required `--circall PATH`; no default | `cohorte_lal` |
| Pediatric controls | Same CIRCALL file | `cohorte_control` |
| Existing donors | `input/cfDNA_donors.xlsx` | First worksheet |

Workbooks and results remain Git-ignored. A code-only clone needs these local input files. Both control sources are prepared even when selecting a single patient cohort, so `--circall PATH` is required for every canonical invocation. The October 1 workbook in the examples is explicitly selected; no replacement for the former September 15 default is inferred.

Confirmed plasma protocols are loaded from `configs/sample_analysis/extraction_protocols.json` (override
with `--extraction-protocols PATH`). CIRCALL patient plasma uses Maxwell: maximum
5 mL per well, 50 or 60 µL eluate per well, with larger samples split across wells.
Retrospective patient plasma was extracted manually, with all plasma processed at once.
These protocol labels are separate from the preserved source `extraction_method` field;
control and non-plasma workflows are not inferred. Recorded elution volume is not treated
as a per-well setting, and neither well count nor combined-well results are inferred.
The configuration and its hash are recorded in each run, with an `extraction_protocols`
worksheet in all three reports. The simplified inference plan is recorded in the scientific contract. The basis of
CIRCALL recorded results and the choice of 50 versus 60 µL per well remain unresolved.

## Run

The former combined default selects canonical analysis plus compatibility
associations, using their explicit profile sources:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_all.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_all.json
```

For canonical analysis alone, from the repository:

```bash
conda run --no-capture-output -n pre_analysis python run.py --circall input/inventaire_CIRCALL_01102026.xlsx
```

For this compatibility command, canonical mode, both cohorts, and all investigations
are the defaults. Plain `python run.py` selects the layered pipeline. Other compatibility examples:

```bash
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --cohort circall
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis inventory
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis volumes --output-dir output/volume_review
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis yield
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis longitudinal --mixed-outlier-drop-n 2
python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis longitudinal --mixed-random-slope-sensitivity
python run.py --inventory /path/to/retrospective.xlsx --circall /path/to/circall.xlsx --donors /path/to/donors.xlsx
```

`--analysis` accepts `all`, `inventory`, `volumes`, `yield`, `longitudinal`, `mrd`, or `kinetics`. `--cohort` accepts `all`, `retrospective`, or `circall`. Sensitivity options require `all` or `longitudinal`. `--workflow cfdna_associations` is separate and is not part of canonical `--analysis all`.

Defaults are resolved relative to the repository. Explicit relative paths are resolved from the caller's directory, so the runner also works when invoked by absolute path from elsewhere. The default output is a fresh `output/run_<date>_<time>_UTC/`; an explicit output directory must be new or empty.

## Consolidated kinetics

Use the [kinetics guide](blast_kinetics.md) for the focused recorded-count/MRD
profile, count source schema and figure names. It also documents the separate
optional normalized model. MRD interpretation for canonical analysis is below.

For direct canonical count selection, supply `--retrospective-blasts PATH` and
`--retrospective-blast-unit 'x10^9/L'` together with `--cohort all|retrospective`
and `--analysis all|kinetics`. Without that explicit source, the direct command
retains its CIRCALL-only count behavior; integrated count profiles supply both options.

## Preparation and QC rules

The canonical Excel reader loads cached cell values and formula metadata without changing or recalculating the source workbooks. Header mappings are explicit and duplicate/missing required headers fail clearly.

Retrospective tube rows are expanded into compartment records. Their `MNC_*` fields produce a linked cell/pellet record with assay-specific quantities; plasma volume is never copied into that record. Source tissue, extraction type, original measurement cells, and source-row references are retained. The different blood-pellet assays are not silently collapsed into a generic concentration. CIRCALL compartment rows retain their existing organisation. Known-patient scheduled rows remain in inventory; empty template people do not become patients.

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

For a pedagogical explanation of each current test, see
[What question does each statistical output answer?](statistical_questions.md).
That guide describes the approved reduced analysis and its interpretation limits.

| Investigation | Outputs and behaviour |
| --- | --- |
| Inventory | Coverage by cohort, compartment, hospital, and timepoint; unique patients/samples; distinct present, na-coded, and blank IDs |
| Volumes | Overall and per-timepoint counts, sums, mean, sample SD, quartiles, range, and compartment figures for recorded fluid volumes and CIRCALL elution volume; CSV and Excel tables only |
| Yield | Unadjusted plasma concentration/yield summaries; side-by-side cohort means/medians and descriptive differences; blood-pellet summaries selected by compartment in both cohorts, with separate assay measures; volume correlations in both cohorts and elution correlations in CIRCALL only |
| Longitudinal | Patient-only random-intercept MixedLM per cohort; planned diagnosis contrasts, paired counts, variance diagnostics, and descriptive trajectories |

The [scientific contract](../workflow_contracts.md#approved-statistical-simplification--october-1-2026)
records the planned contrasts, descriptive visits, corrections and rationale.
Use `--longitudinal-followups` to select planned comparisons and
`--longitudinal-descriptive-visits` to record visits omitted from inference.
Controls remain in figures and counts. The full and longitudinal JSON profiles enable
exploratory pooled plasma comparisons at the investigator’s request. Direct canonical
CLI runs require `--pool-cohorts`; set `pool-cohorts` false in a profile to disable it.
The pooled model has no cohort adjustment and retains the configured descriptive-visit exclusions.

Inventory coverage is independent of measurement availability. For the ongoing CIRCALL cohort, sample ID `na` means the sample was not received; a blank ID means the timepoint has not yet been reached. The table reports `not_received_records` and `timepoint_not_yet_reached_records`. Missingness is not received / (present IDs + not received); future timepoints are excluded from this denominator. Coverage is exported only as CSV and Excel tables, with no coverage PNGs. No retrospective expected-collection denominator is inferred. Distinct inventory records, samples, and patients are reported separately.

Retrospective quantitative plasma analyses retain the cfDNA extraction and parsed-timepoint rules. Sample IDs remain optional for retrospective longitudinal analyses and required for dosage/correlations. CIRCALL dosage/correlation/longitudinal analyses require a present sample ID and timepoint. Retrospective correlations retain the post-inotuzumab exclusion. All policies are recorded in the run manifest.

Descriptive timepoints remain cohort-specific; the model omits configured descriptive-only visits. Plots show only available canonical timepoints, ordered Control, D1, D4, D8, D15, TP1 (D29), TP2 (D71). Diagnosis (`diag`) is displayed as D1 by default, as confirmed by the study owner. `--no-plot-diagnosis-as-d1` explicitly disables that display mapping. Diagnosis remains in the statistical models in either case. The TP1 and TP2 day annotations are display labels requested for these plots, not a conversion of the recorded times. Recorded observations outside the model timepoints remain in descriptive tables where eligible. Both cohorts share axes, with adjacent boxes and one pooled control group. Additional `_pooled.png` versions use one box per timepoint across both patient cohorts, with points colored by cohort. Longitudinal pooled boxes combine patient medians; descriptive yield boxes combine sample observations. Cohorts remain separate in statistical models, and assay-specific blood-pellet measurements are not pooled across different assays. Subtype colors and the subtype legend are removed; colors identify cohorts. Correlation scatter plots overlay the cohorts on shared numerical axes. Coverage and volume tables retain all recorded timepoints. Residual diagnostics and model_diagnostics.csv describe the fitted patient-only models; numerical warnings require review.

Methods retain existing transformations: positive log10 concentrations for inference, log10(1+x) descriptive box plots, log10 concentration or log10(1+total DNA) for correlations. Overall correlations require 3 pairs and timepoint-specific correlations 5; unavailable/constant groups are labelled explicitly. BH correction covers the available planned mixed-model contrasts within each cohort; correlations are descriptive Pearson/Spearman coefficients without p-values. The descriptive cohort-comparison table matches timepoint labels only and does not assert equivalent collection windows. No new cross-cohort model or cross-cohort hypothesis test is introduced. All DNA plot observations use circle markers, without MRD status encoding. `na` and `n/a` are missing MRD information, never negative results. Only concordant explicit positive/negative labels produce categorical source annotations; numeric values await a separate MRD analysis with confirmed units and detection limits.

Sensitivity analyses are opt-in. Outlier-drop refits retain the requested count. Random-slope sensitivity uses the legacy numeric TP scale for the retrospective cohort; CIRCALL is explicitly unavailable because no common numeric mapping of its day and TP labels has been agreed. CIRCALL MRD is read separately from the explicit `MRD_TP1` and `MRD_TP2` columns; it is not inferred from assay availability.

Blood-pellet plots show individual canonical timepoints on a linear measurement scale. Blood-pellet DIN, tube-count, and aliquot-count summaries and figures are excluded; raw source measurements remain in preparation records.

Blood-volume analyses and retrospective elution-volume analyses are excluded at user request. Source fields and elution-based source-consistency checks remain available for provenance and QC. Compartments are never plotted against one another. Blood-pellet tables use `blood_pellet_` measurement names for the retrospective assays; original `MNC_*` workbook column names and record identifiers remain in source provenance. CIRCALL blood-pellet concentration and total DNA come from its standard DNA fields on `compartment = blood pellet` records; these are not relabelled as the retrospective Vario or albumin assays.

## Additional longitudinal trend figures

The approved descriptive method is recorded in the
[scientific contract](../workflow_contracts.md#descriptive-longitudinal-trend-figures--october-1-2026).
The joint `longitudinal/trendlines.png` and each cohort's `trendlines.png` supplement
the existing figures. Cohort trends are separate, with patient/visit dots and counts;
CIRCALL TP2 has no shaded interval. The retained engine directory contains aggregate
`longitudinal/trendline_summary.csv` and `trendline_settings.json` with interval
omissions and valid/empty bootstrap draw counts. Settings also enter the run manifest.

Use the focused profile with explicitly selected source workbooks, first validating
and then running to a fresh destination:

```bash
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_longitudinal.json --validate-only
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_longitudinal.json --output-dir output/<fresh-longitudinal-run>
```

The `trend-bootstrap-resamples`, `trend-bootstrap-seed`, and
`trend-bootstrap-method` profile keys also have corresponding `--` CLI flags for
canonical runs. Statistical testing now follows the approved simplification in the scientific contract.

Validation of the first trend run used these commands (report destinations must
be fresh when repeating validation):

```bash
conda run --no-capture-output -n pre_analysis python -m unittest discover -s tests/sample_analysis -v
conda run --no-capture-output -n pre_analysis python -m unittest discover -s tests/orchestration -v
conda run -n pre_analysis python -m analysis.validation.validate_canonical --run-dir output/longitudinal_trends_20261001 --output output/longitudinal_trends_source_validation_20261001.json
conda run -n pre_analysis python -m analysis.validation.validate_longitudinal_trends --reference-run output/run_2026-10-01_11-08-13.824502_UTC --run-dir output/longitudinal_trends_20261001 --output output/longitudinal_trends_validation_20261001.json
```

All 108 tests passed. The [source check](../../archive/results/compatibility_20261007T073346593956Z/longitudinal_trends_source_validation_20261001.json)
verified 401 endpoint records. The [equivalence/provenance check](../../archive/results/compatibility_20261007T073346593956Z/longitudinal_trends_validation_20261001.json)
verified nine medians/counts, exact bootstrap reproducibility, 54 unchanged
longitudinal artifacts, seven unchanged pooled statistical tables, all 278 original
and 134 new indexed artifacts, and 22 publication hashes. Three new figures were
visually inspected. Existing model warnings remain; these checks establish software
and provenance consistency, not scientific validity or absence of follow-up bias.

The scoped pre-change snapshot is
`archive/migrations/longitudinal_trends_20261001T114535Z/`. Its after-hashes and
new-file list support reviewed rollback of only these code/documentation additions;
preserve original and new result directories and any subsequent edits.

## CIRCALL MRD plot

`--analysis all` includes the CIRCALL MRD plot when CIRCALL is selected. Run only this investigation with:

```bash
conda run -n pre_analysis python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --cohort circall --analysis mrd --mrd-unknown-level 1e-6 --mrd-negative-level 1e-8
```

The input is `cohorte_lal`, columns `circall_id`, `MRD_TP1`, and `MRD_TP2`. Repeated patient-level annotations are counted once per patient/timepoint; contradictory entries cause a failure. Blank/`na`/`n/a` entries remain missing. Numeric values are interpreted as residual clone fractions relative to diagnostic baseline 1 (100%). D1 is a normalisation reference, not a measured MRD result.

At the study owner's request, `unknown significance` is displayed at 1e-6 and `negative` at 1e-8. These are assigned display levels, not quantitative measurements or inferred assay detection limits. The two CLI options expose these conventions and the run records them. Measured values and assigned positions are separate columns in the observations table.

The figure shows D1, TP1 (D29), and TP2 (D71), with a single logarithmic y-axis showing residual clone fractions in scientific notation (D1 = 1). Points show the reported category, and dotted trajectory segments touch assigned categorical levels. The plot includes only patients with at least one follow-up MRD result. No violin density is estimated from these categorical positions or the small number of quantified observations. Retrospective MRD uses its own phase-paired source and figure, described below.

Outputs: `mrd/circall_mrd_trajectories.png`, summary and patient-level CSVs, an Excel workbook, and `plot_settings.json`.

## Retrospective MRD

`--analysis mrd`, `all`, and `kinetics` include retrospective MRD when that cohort
is selected. `input/cfDNA_inventaire_retrospective.xlsx`, sheet `Inventaire`, supplies
`MRD_IgTCR`; **pair each entry with its row's `treatment_phase` (`tp1` or `tp2`)**.
Only `tissue = Moelle` rows are selected (trimmed, case-insensitive match); the
`--retrospective-mrd-tissue` option records this selection. Other phases are outside
this module. Existing retrospective surname-based identity
is reused; no cross-cohort matching, inferred calendar day, or normalized D1 is added.
The investigator corrected the initial TP1-only description before any MRD results
were generated. The scientific rules are in the
[contract](../workflow_contracts.md#retrospective-mrd-by-treatment-phase--october-1-2026).

The numeric scale is the same residual fraction used in CIRCALL; e.g. 0.001 is a
3-log reduction, not a literal 0.001-log reduction. `pos NQ <10-4` and `pos NQ
<5.10-5` retain positive-nonquantifiable status and the reported upper bound. Bounds
are not substituted for measured values or interpreted as assay detection limits.
Identical annotations within a patient/visit collapse; different TP1 and TP2 values
are legitimate. The investigator approved numeric > pos NQ > negative within each
retrospective patient/visit, with the highest numeric fraction or highest pos NQ
bound retained within a category. Bounds are never substituted for measurements.
Resolved disagreements are counted in summaries and settings. Use
`--retrospective-mrd-duplicate-policy error` for the earlier strict behavior.
CIRCALL retains its existing duplicate rules.

```bash
conda run -n pre_analysis python run.py --analysis mrd --cohort retrospective --inventory input/cfDNA_inventaire_retrospective.xlsx --circall input/inventaire_CIRCALL_01102026.xlsx
```

The general canonical preparation still requires the configured CIRCALL/control
sources. Integrated full/kinetics profiles validate both MRD cohorts before execution.
The four previously discordant TP1 groups are now resolved by the approved priority.
The [earlier cell-reference review](../../archive/results/compatibility_20261007T073346593956Z/retrospective_mrd_moelle_conflicts_20261001.csv)
is retained audit evidence; the authoritative workbook was not overwritten. A change to the association catalog-pinned workbook
must also follow the existing source-selection/hash-verification rules.

Successful runs publish `kinetics/mrd/retrospective_mrd_summary.csv`
and `retrospective_mrd_trajectories.png`, and add an `mrd_summary` sheet to the
retrospective statistics workbook. Patient-level retrospective MRD stays in memory.
Summary denominators count identified patients with recorded rows at each selected
phase, not an inferred expected-visit population. The figure joins quantified pairs
only. Positive NQ without a bound is counted without inventing a numeric position.
The existing negative display level is a plotting convention, not a measurement.

## Figure legends

All figure legends are placed below the plotting area, axis labels and any explanatory
notes. PNG and PDF exports include the full legend; labels, colors, data and statistical
results are unchanged. Multi-panel legends are stacked to prevent overlap.

## Results and provenance

Visible workbooks and selected figures/tables are under `<run>/sample_analysis/`.
The following is the **native evidence** layout beneath the hidden audit directory;
see the [publication guide](../audit_guide.md#locations-and-ownership) for the mapping:

```text
<run>/.audit/workflows/sample_analysis/
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
  inventory/                # coverage table: CSV and Excel only
  volumes/                  # summary tables only; no PNGs
  yield/                    # summaries, both cohorts' correlations and figures
  longitudinal/
    retrospective/          # statistics workbook, CSVs, diagnostics
    circall/                # statistics workbook, CSVs, diagnostics
    boxplots.png
    trajectories.png
  analysis_status.csv
  run_manifest.json
  logs/
```

`reconciliation.json` explains the intentional measurement-basis, control-pooling, parsing, and missingness changes. `endpoint_basis.csv` compares unadjusted and percentage-adjusted quantities within the current sources; it is not presented as an old-versus-new file comparison.

An unsupported analysis is labelled `unavailable`. A failed model is labelled `failed` and causes a nonzero overall exit, while the other cohort can still finish. Convergence and small-sample warnings remain in the logs. Inspect paired counts and diagnostics when interpreting results.

## Historical reproduction and rollback

Legacy execution has been retired. Sources and completed historical runs remain local.
See [cleanup and rollback](../history/repository_cleanup.md) for the scoped code snapshot.

## Tests

Use `tests/sample_analysis` and `tests/orchestration` with the
[central validation commands](../audit_guide.md#validation-commands). That guide also
owns canonical source-cell validation and reviewed baseline-expectation handling.
Dated validation commands elsewhere on this page record the original acceptance;
they are not a substitute for selecting explicit current run paths.

## Pooled MRD plots

`--pool-mrd` adds descriptive pooled trajectories and 100% stacked patient-status
bars when both cohorts are selected. The full, kinetics, and focused MRD profiles
enable this separately from plasma pooling. For a focused, audited MRD run:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_mrd.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_mrd.json --output-dir output/pooled_mrd_review
```

The new directory must not exist. Figures `pooled_mrd_trajectories.png` and
`pooled_mrd_status_stacked.png`, aggregate `pooled_mrd_summary.csv`, and
`pooled_mrd_settings.json` are published under `sample_analysis/kinetics/mrd/`.
Diagnosis is an assumed disease-positive reference, not measured blast-cell
percentage. Each bar uses the same included-patient denominator; missing/unrecorded
follow-up is a separate segment. Source categories and bounds retain their meaning;
see the [pooled MRD contract](../workflow_contracts.md#approved-descriptive-pooled-mrd--october-1-2026).

Validation for this addition used:

```bash
conda run --no-capture-output -n pre_analysis python -m pytest tests/sample_analysis/test_pooled_mrd.py tests/sample_analysis/test_mrd.py tests/sample_analysis/test_retrospective_mrd.py tests/orchestration -q
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_mrd.json --validate-only
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_mrd.json --output-dir output/pooled_mrd_20261001_final
```

The test suite passed 55 tests and 34 subtests; the four pooled-MRD tests were
rerun successfully after label/spacing adjustments. Integrated preflight and the
final run completed. Both final PNGs were visually inspected; all 10 published
artifact hashes matched their audit sources, input and executed-code hashes were
verified, and pooled status percentages summed to 100 at each visit. The selected
input hashes also matched the referenced `run_2026-10-01_14-20-31.113783_UTC`.
These checks establish execution and display integrity, not scientific validity.

### Automatic pooled longitudinal trendline

Full and longitudinal profiles with `pool-cohorts: true` and both cohorts now
publish `sample_analysis/longitudinal/trendlines_pooled.png` automatically.
Its aggregate summary and settings are retained under the canonical engine's
`longitudinal/pooled_trendline_summary.csv` and `pooled_trendline_settings.json`.
`--no-pool-cohorts` or selecting one cohort omits this pooled companion.
The approved scientific rules are in the [contract](../workflow_contracts.md#canonical-pooled-longitudinal-trendline--october-1-2026).

### Canonical yield/WBC two-panel figure

The full profile automatically publishes `sample_analysis/longitudinal/yield_wbc_panels.png`
and `.pdf`: pooled yield on top, CIRCALL WBC below. Both longitudinal and kinetics
tasks, both cohorts, and cohort pooling must be selected. Focused longitudinal-only
or kinetics-only runs omit this composite. The existing individual figures remain.
See the [panel contract](../workflow_contracts.md#canonical-yieldwbc-panels--october-1-2026).

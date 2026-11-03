# Consolidated kinetics guide

The default four-layer pipeline uses [Layer 4 disease tracking](../layers/disease_modeling.md).
The retained compatibility kinetics workflow is the canonical blood-count/MRD analysis, with
results under `sample_analysis/kinetics/`. It combines retrospective and CIRCALL
blast counts on the confirmed ×10⁹/L scale, keeps cohort identities separate, and
retains patient trajectories, the diagnostic-baseline convention and separate
CIRCALL WBC/MRD plots.
The normalized blast model is excluded from default runs. See the
[scientific contract](../workflow_contracts.md#kinetics-consolidation--october-1-2026)
for the approved rules and unresolved source-merging questions.

Run only the consolidated analysis from the repository root:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_kinetics.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_kinetics.json --output-dir output/kinetics_review
```

Blood-count figures use a logarithmic y-axis and linear time. Measured zeros appear
in a labeled strip below the axis; trajectories break at zero. Counts and summaries
retain their original values. Use `--kinetics-y-scale linear` (or the profile option)
for linear display. MRD keeps its existing logarithmic display.

Use a fresh destination. The profile explicitly selects
`input/retrospective_blast_count_01102026.xlsx` (`blast`, `blast_count_x10*9/L`) for
retrospective counts and `input/CIRCALL_wbc_blast_count_01102026.xlsx` (`blast`, `wbc`)
for CIRCALL. Existing canonical preparation also reads the selected inventories,
donor workbook and extraction metadata. Main outputs include:

- `blast_cohort_overlay.png` / `.pdf`: both cohorts' blast trajectories over the diagnostic-to-day-8 display window.
- `blast_trajectories_by_cohort.png`: separate cohort panels on a common count scale, retaining their full recorded day ranges.
- `retrospective_blast_trajectories.png` and `blood_count_summary.csv`: retrospective trajectories and cohort-labeled aggregate counts.
- Existing CIRCALL blast/WBC figures and `mrd/circall_mrd_trajectories.png`.

Full engine evidence remains under `.audit/workflows/sample_analysis/`. The
retrospective loader preserves trimmed, case-sensitive surname grouping within its
source and writes no row-level table or subject labels. No WBC values are inferred
from blast percentages. See the contract for the descriptive eligibility change
from the former normalized analysis and the count/fraction discrepancy limitation.

## Retrospective workbook layout

The active `blast` worksheet uses `tt_d1_date`, `num_date`, `day` and
`blast_count_x10*9/L`, matching CIRCALL count/date headers. `lastname` remains the
existing identity field; no new subject IDs or matching rules are introduced.
`percent_blast`, treatment/subtype fields, names, `num_log` and source notes are
preserved locally. The original unheaded notes column is named `source_note`.
Original formulas and their cached results are retained with remapped column
references. `source_test` retains the unused original test sheet and is not an
analysis input. `README` explains field provenance. No WBC sheet is fabricated.

## Explicit normalized-model compatibility workflow

The remainder of this guide documents the preserved opt-in implementation.
Run commands from the repository root. Layout 2 puts final results in the
run’s `blast_kinetics/` directory and internal files in `.audit/workflows/blast_kinetics/`.
See the [audit guide](../audit_guide.md) for output ownership and replacement rules.

## Normalized kinetics pipeline

This workflow analyzes repeated numeric measurements over time. The included
`blast_kinetics` profile normalizes blast counts to each patient's day-1 value,
plots observed kinetics with a bootstrap confidence interval, and fits the
configured random-intercept time model.

## Run the optional normalized model

Use the shared environment from [README setup](../../README.md#setup), from the repository root:

```bash
conda run -n pre_analysis python -m analysis.blast_kinetics --config configs/blast_kinetics/blast_kinetics.yml --validate-only
conda run -n pre_analysis python -m analysis.blast_kinetics --config configs/blast_kinetics/blast_kinetics.yml
```

The validation command reads the complete dataset, applies cohort rules, and fits
the enabled model, but writes nothing. A successful run creates
`output/blast_kinetics/`. If that run already exists, review it first and rerun
with `--force` only when replacement is intentional.

Use `tests/blast_kinetics` with the [central validation commands](../audit_guide.md#validation-commands);
that guide distinguishes portable checks from the local-workbook suite.

## Inputs and configuration

The pipeline accepts Excel or CSV tables. Each row is one subject at one time point.
The YAML profile maps source headers onto four generic fields:

- `subject`: stable subject identifier (required)
- `time`: numeric time value (required)
- `value`: numeric measurement analyzed in this run (required)
- `group`: optional category used for colors and legends

Subject identifiers are used in memory but are never written to logs or summaries.
Duplicate subject/time rows are rejected.

All scientific and presentation choices live in the YAML profile. Important sections
include the time window, minimum measurements, normalization, group aliases/colors,
bootstrap settings, winsorization, mixed model, axes, labels, and output location.
Relative paths are resolved from the profile's directory.

To analyze another measurement:

1. Copy `configs/blast_kinetics/raw_measurement_example.yml`.
2. Give `run.name` a unique value.
3. Set `input` and `columns.value` to the new table and measurement column.
4. Choose `normalization.mode: none` or `percent_of_baseline`.
5. Update the measurement name/unit, grouping rules, model, and plot axes.
6. Run `--validate-only` before generating results.

The supported model is deliberately constrained to a random-intercept linear time
effect, optionally fitted after winsorization and a log-offset transformation. YAML
does not accept arbitrary statistical formulas.

## Outputs

Final results are published atomically inside `output/<run-name>/blast_kinetics/`:

- `scatter.png`: observations and the daily median bootstrap interval
- `mixed_model.png`: observations and model trend, when enabled
- `model_summary.txt`: fitted model summary, when enabled
- `cohort_summary.json`: anonymized filtering and group counts

The complete native output, including `resolved_config.yml`, `run_metadata.json`,
and `run.log`, remains in `.audit/workflows/blast_kinetics/` within the run root.

The pipeline never replaces an existing run without `--force`, and it refuses to
touch a run directory containing files it does not own.

The [audit guide](../audit_guide.md#locations-and-ownership) owns provenance fields,
source rechecks and publication verification. `--output-dir PATH` selects an
explicit destination without changing profile-relative input resolution.
No subject-level tables are added.

`configs/pipeline_all.json` deliberately excludes this normalized model. To use
it in a custom integrated profile, retain the supported entry
`{"name": "blast_kinetics", "profile": "<path-to-yaml>"}`; profile paths resolve
relative to that JSON. The coordinator preserves its scientific settings.

The [coverage map](../replacement_coverage.md#entry-point-and-profile-disposition)
owns entrypoint retention; the [archival audit](../history/archival_audit.md) and
[source relocation record](../history/integration_validation_20261001.md#retrospective-source-relocation-and-reformat--october-1-2026)
locate historical implementations and source evidence.

## Troubleshooting

- **Missing column:** compare `columns` in the YAML with the input headers exactly.
- **No eligible subjects:** inspect the configured time window, baseline policies,
  and minimum measurement count.
- **Unknown group color:** add an alias/color or deliberately select
  `grouping.unknown_policy: auto`.
- **Log-scale error:** use a linear axis or correct negative values; explicit zeros
  are displayed at the configured detection limit.
- **Existing output:** choose a new `run.name`, or inspect the old run and use
  `--force` intentionally.

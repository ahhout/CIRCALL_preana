# Diagnosis cfDNA associations

## Layer 3: harmonized diagnosis associations

The read-only `advanced_analysis` workflow independently reads the explicitly
selected October 5 inventories through the shared raw/cached cell reader. It
does not consume Layer 2 summaries or change the older `cfdna_associations`
preparation described below. Its scientific decisions and mappings are in the
[Layer 3 contract](workflow_contracts.md#layer-3-diagnosis-cfdna-associations--october-6-2026)
and [versioned definitions](../configs/definitions/advanced_analysis.json).

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_advanced_analysis.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_advanced_analysis.json
```

Equivalent standalone command with the shipped scientific settings:

```bash
conda run -n pre_analysis python -m analysis.advanced_analysis \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --circall input/inventaire_CIRCALL_05102026.xlsx \
  --donors input/cfDNA_donors.xlsx --cohort all --include-controls \
  --rules configs/definitions/data_integrity.json \
  --definitions configs/definitions/advanced_analysis.json \
  --predictors peripheral_blast_percent --retrospective-wbc-unit 'x10^9/L' \
  --spearman-sensitivity --pool-cohorts
```

Use `--output-dir` only with a nonexistent destination. `--cohort retrospective`
or `circall` selects one patient source; `--no-include-controls` removes controls
from integrity, and `--no-pool-cohorts` disables pooled descriptions. Omitted
donors are not selected implicitly. `--predictors` selects a nonempty regression
family while all six predictors remain described. Retrospective WBC defaults to
an unconfirmed unit in the standalone CLI; the shipped profile explicitly confirms
the unit and enables compatible pooled WBC descriptions. `--validate-only` checks
configuration and prepares a source preview without fitting models or publishing;
whole-cohort integrity gates run during execution. Preparation problems remain in
the preview and subsequently produce blocked/error reports, allowing an independent
cohort to finish.

```text
outputs/layer3_advanced_analysis/run_<timestamp>/
├── retrospective/
│   ├── associations.xlsx
│   └── figures/<clinical_comparison>/*.png, *.pdf
├── circall/
├── pooled/
└── .audit/workflows/03_advanced_analysis/
```

Single-layer standalone/master runs expose the cohort folders directly. A mixed
integrated run groups these under `03_advanced_analysis/`. Each workbook has
Summary, Coverage, Associations, Descriptions, Diagnostics and Definitions tabs.
Coverage distinguishes available positive pairs, the actual per-predictor analysis
population, contributing outcome samples and clinical source records, nonpositive
pairs, and selected versus descriptive status. Summary contains selection
exclusions, missing outcomes, integrity reviews, repeat counts and retrospective
categorical discordance counts when present. Descriptions retain genuine zero
medians on the original outcome scale; logarithmic models and figures require
positive medians. A plasma row can contribute a clinical predictor independently
of whether its cfDNA measurement is available.

Continuous coefficients describe change in log10(cfDNA); fold changes use ten
percentage points for blast predictors and one recorded unit otherwise. Ordinary
95% intervals are not corrected for multiple testing. Selected categorical tests
are omnibus questions. Descriptive correlations use log10(cfDNA), with no
correlation hypothesis tests. Peripheral-blast Spearman sensitivity is explicitly
secondary and unadjusted. Pooled descriptions require comparable data in both
cohorts for each predictor; sex and age currently remain retrospective-only.
Extraction protocols and participant composition still limit pooled interpretation.

Main figures show recorded ng/mL on logarithmic y-axes.
WBC (`cfDNA_ng_per_mL_vs_gb_per_l`) and marrow blast percentage
(`cfDNA_ng_per_mL_vs_tumor_fraction_percent`) comparisons also use logarithmic
x-axes; nonpositive predictor values are omitted and counted for display only,
retained in tables/models. Models continue to use recorded WBC and percentage
points, without a log-predictor transformation.
Fits and confidence limits
are calculated on log10(cfDNA), then back-transformed. Categorical boxes retain
their historical log10 calculation scale; their displayed median can therefore
differ from the original-scale median in Descriptions. Sparse or constant models
retain available points and a fit-unavailable explanation. Absent variables receive
coverage entries without fabricated figures.

Definite integrity errors, invalid selected clinical values or conflicting CIRCALL
metadata block that cohort; reviews alone permit execution. Valid reports for
blocked and independent completed scopes publish before a nonzero final exit.
Unavailable predictors and unestimable fits are analytical limitations and do not
fail execution. Controls never enter patient models or pooled descriptions.
Row evidence contains hashed cohort identities, numeric measurement states and
source coordinates under `.audit`; residual plots and influence evidence remain
there. Names, DOB, sample IDs and unrestricted notes never enter result frames.
The shared publisher indexes verified copies and rechecks source/rule hashes.

The [October 6 acceptance record](layer3_validation_20261006.md) gives exact commands,
current-source coverage, standalone/master comparison results and remaining limits.

## Compatibility association workflow

This workflow compares **diagnostic cfDNA with diagnosis metadata**, separately
from longitudinal yield, MRD and kinetics. The explicit `pipeline_all.json` profile selects both
retrospective and CIRCALL inventories and adds compatible pooled descriptive views.

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_all.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_all.json
```

Run just these associations with both explicitly selected inventories:

```bash
conda run -n pre_analysis python run.py --workflow cfdna_associations --circall input/inventaire_CIRCALL_01102026.xlsx
```

Omitting `--circall` retains the retrospective-only interface. The retrospective
source is hash-pinned in `configs/source_catalog.json`; `--inventory PATH` explicitly
overrides it and records the actual hash. A changed pin fails preflight clearly.
Neither loader chooses a workbook by modification time. Both input hashes and
executed code/settings are recorded; sources are never modified.

The [scientific contract](workflow_contracts.md#diagnosis-associations-across-cohorts--october-1-2026)
contains all eight requested variable mappings, units, eligibility and pooling rules.
Only rows labelled `diag` contribute diagnosis measurements. Missing sex/age or
absolute-count sources are skipped; blood/marrow absolute blast counts are not
computed from percentages. In the legacy profile's source, five WBC patients
and no marrow-blast-percentage patients remain eligible at diagnosis. TP1 values
are not used to restore the earlier larger diagnostic dataset.

Outputs with both cohorts selected:

```text
cfdna_associations/
  diagnosis_availability.csv   # all eight variables, counts and reasons for skips
  diagnosis_settings.json     # units, source mappings and analysis scope
  retrospective/              # diagnosis views and selected tests
  circall/                    # diagnosis views and selected tests
  pooled/                     # comparable descriptive views, colored by cohort
```

Each cohort retains the peripheral-blast regression as its selected hypothesis
test, with HC3 uncertainty, effect size/CI and BH correction across selected tests.
`--predictors` changes the testing selection, not the scope of descriptive views.
Other available variables retain scatter plots/trends or categorical distributions
and summaries. `--no-pool-cohorts` disables pooled diagnosis views. The full and focused association profiles now confirm retrospective WBC as ×10⁹/L
using `retrospective-wbc-unit`, enabling the pooled WBC view. Without that explicit
unit setting, pooled WBC remains skipped. Absolute blast counts remain unavailable
and are not derived. Association folders and figure filenames explicitly distinguish peripheral blood
from bone marrow; see the output naming table below. Pooled outputs
have no hypothesis p-values; differing extraction protocols and cohort composition
still limit interpretation. Unavailable metadata have explicit coverage entries;
no borrowed follow-up measurements or invented numeric values are used.

All legends remain below the plotting area. Audit data and residual diagnostics
remain under `.audit/workflows/cfdna_associations/`; only reviewed aggregate tables
and main plots are published. Previous result folders are retained unchanged.

```bash
conda run -n pre_analysis python -m pytest -q tests/cfdna_associations tests/orchestration
```

The engine originated in `multivariate_analysis_retrospective` revision
`81f14d045c02410e587ed239d62c6588d841ae95`. Import hashes and its original snapshot
are recorded in `analysis/cfdna_associations/import_provenance.json`.
The earlier import comparison remains at
`output/cfdna_migration_validation_20261001/comparison/comparison.json`.

The following comparison documents the historical imported engine. It is not an
equivalence validator for the revised scientific plan and will detect intentional
model/output changes. Use the focused suites and source checks for current runs.
Historical comparison commands (fresh destinations only):

```bash
conda run -n pre_analysis python run.py --workflow cfdna_associations --output-dir output/new_associations_check
conda run -n pre_analysis python -B -m tests.validation.validate_associations \
  --original ../multivariate_analysis_retrospective/analyze_blast_cfdna.py \
  --inventory input/cfDNA_inventaire_retrospective.xlsx \
  --integrated-run output/new_associations_check \
  --output-dir output/new_associations_comparison
```

The comparison checks membership, predictor observations, CSV values and missingness
without printing clinical rows. It writes original-engine results only to the
comparison destination. Numerical tolerances remain rtol=1e-10 and atol=1e-12.

## Tissue-explicit association filenames

New runs use these folders within each available cohort scope:

| Comparison | Folder | Figure |
| --- | --- | --- |
| Peripheral blood WBC | `cfDNA_vs_peripheral_blood_wbc_count/` | `log10_cfDNA_ng_per_mL_vs_peripheral_blood_wbc_count.png` |
| Peripheral blood blast percentage | `cfDNA_vs_peripheral_blood_blast_percent/` | `log10_cfDNA_ng_per_mL_vs_peripheral_blood_blast_percent.png` |
| Bone marrow blast percentage | `cfDNA_vs_bone_marrow_blast_percent/` | `log10_cfDNA_ng_per_mL_vs_bone_marrow_blast_percent.png` |

This naming-only change leaves CLI/config predictor names (`gb_per_l`,
`peripheral_blast_percent`, `tumor_fraction_percent`) and all calculations intact.
Predictor metadata records the figure name for validation and publication;
historical runs retain their original filenames and metadata.

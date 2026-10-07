# Layer 3 implementation acceptance — October 6, 2026

The harmonized `advanced_analysis` workflow completed independently and through
the master runner, with the explicitly selected October 5 patient inventories
and retrospective donor workbook. The named runs are
`outputs/layer3_advanced_analysis/run_20261006T102847Z_standalone/` and
`outputs/layer3_advanced_analysis/run_20261006T102847Z_master/`.
The [aggregate verification record](../outputs/layer3_advanced_analysis/validation_20261006T102847Z.json)
passed. No clinical input, existing legacy scientific engine, existing default
profile, dependency definition or environment lock was changed.

## Commands actually executed

All Python execution used the existing `pre_analysis` Conda environment. A writable
Matplotlib cache was explicitly selected with `MPLCONFIGDIR=/tmp/pre_analysis_matplotlib`
for the commands below; this does not change analytical settings.

```bash
conda run --no-capture-output -n pre_analysis python -m pytest -q \
  tests/advanced_analysis tests/cfdna_associations tests/sample_statistics \
  tests/orchestration tests/validation tests/sample_analysis tests/blast_kinetics \
  --ignore=tests/blast_kinetics/test_workbook_integration.py

conda run --no-capture-output -n pre_analysis python -m pytest -q tests/advanced_analysis

./run_all_layers.sh --validate-only

conda run --no-capture-output -n pre_analysis python run.py \
  --config configs/pipeline_advanced_analysis.json --validate-only

conda run --no-capture-output -n pre_analysis python -m analysis.advanced_analysis \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --circall input/inventaire_CIRCALL_05102026.xlsx \
  --donors input/cfDNA_donors.xlsx --cohort all --include-controls \
  --rules configs/definitions/data_integrity.json \
  --definitions configs/definitions/advanced_analysis.json \
  --predictors peripheral_blast_percent --retrospective-wbc-unit 'x10^9/L' \
  --spearman-sensitivity --pool-cohorts \
  --output-dir outputs/layer3_advanced_analysis/run_20261006T102847Z_standalone

conda run --no-capture-output -n pre_analysis python run.py \
  --config configs/pipeline_advanced_analysis.json \
  --output-dir outputs/layer3_advanced_analysis/run_20261006T102847Z_master

conda run --no-capture-output -n pre_analysis python -m tests.validation.validate_advanced_analysis \
  --standalone outputs/layer3_advanced_analysis/run_20261006T102847Z_standalone \
  --master outputs/layer3_advanced_analysis/run_20261006T102847Z_master \
  --report outputs/layer3_advanced_analysis/validation_20261006T102847Z.json

bash -n run_all_layers.sh
git diff --check
```

The broader regression command passed 293 tests and 81 subtests, with two existing
Matplotlib boxplot deprecation warnings. After the final Layer 3 source reconciliation
and figure-scale checks were added, the focused suite passed all 40 tests.
It passed again after explicit zero-count reporting was added for discordance
and outcome availability states. The
broader count predates those last two test additions; these counts overlap and must
not be added. All three layer profiles passed preflight; both final Layer 3 commands
and the acceptance validator exited zero. The full Layer 1/2 clinical executions
and normalized kinetics local-workbook tests were not rerun for this increment.

## Current-source coverage

Counts are predictor-specific complete positive cfDNA/predictor pairs, rather
than the legacy engine's global blood/marrow completeness denominator.

| Predictor | Retrospective | CIRCALL | Compatible pooled descriptions |
| --- | ---: | ---: | ---: |
| Sex | 73 | Unavailable | Unavailable |
| Age at diagnosis | 73 | Unavailable | Unavailable |
| Genetic subtype | 73 | 17 | 90 |
| Peripheral blood blast percentage | 55 | 17 | 72 |
| Peripheral blood WBC | 48 | 17 | 65 |
| Bone marrow blast percentage | 67 | 17 | 84 |

Retrospective preparation retains 76 eligible plasma sample rows from 74 patients,
with 75 numeric outcomes and one intentional empty outcome, leaving 73 patients
with positive numeric medians. Two patients have repeated eligible samples.
CIRCALL retains 21 eligible plasma rows/patients, 17 numeric outcomes and four
intentional empty outcomes; two diagnosis plasma rows have unavailable sample IDs
and are excluded from outcomes. No current patient median is nonpositive; synthetic
tests cover genuine zeros, repeated zero/positive samples and zero medians.
Neither cohort has a categorical metadata conflict under the implemented rules.

Controls were included only in integrity. Both patient cohorts have zero integrity
errors. One retrospective-scope review is trailing whitespace in donor-sheet
`Feuil1` header B1; source bytes remain unchanged. The retrospective unused cytospin
annotation at X521 has numeric cytology in the same row, so the established primary
cytology rule applies. No annotation is converted into a numerical measurement.
Absolute blast counts and hematocrit remain unavailable, without derived substitutes.

The selected peripheral-blast HC3 regressions use 55 and 17 patients. Retrospective
fold change per the contracted increment is 1.0514 (ordinary 95% CI 0.9344–1.1830;
primary/BH p=0.3978). CIRCALL is 1.0303 (0.7463–1.4224; p=0.8462). The secondary
unadjusted Spearman results are rho=0.1103, p=0.4228 and rho=0.2010, p=0.4392,
respectively. These are unadjusted observational associations, not evidence of an
independent or causal relationship. Pooled results contain no inference.

## Verification and limits

The final named runs have 14 identical native numerical evidence files, three
matching six-tab workbooks and 20 pixel-identical PNGs (14 main figures plus six
audit diagnostic plots). Each run has 88 verified indexed artifact hashes and
31 verified visible/native publication hashes: three workbooks and 14 PNG/PDF
pairs. All 69 executed Python code hashes, the scientific contract, rule/definition
inputs, environment lock and selected source bytes were verified. Clinical source
hashes also match the explicitly named initial development run
`acceptance_standalone_20261006`, which remains retained evidence.

Source preparation was reconstructed to reconcile hashed patient medians, source
coordinates and measurement availability states with audit observations; statistical
recalculation and workbook reconciliation passed. Per run, 27 workbook/text exports
passed comparisons against source identifying values held in memory. Synthetic
privacy sentinels and figure text/coordinate checks passed; published artifacts
contain aggregate reports and main clinical figures only. Real sample IDs never
enter the legacy fitting/export tables. Fresh-destination refusal, blocked report
publication, unavailable controls, independent execution failures, compatible
pooling, correction families, estimability and sensitivity behavior are tested.

Main PNGs were visually inspected, including the primary retrospective comparison
and pooled genetic-subtype view; legends lie outside data regions and widened
categorical spacing prevents the initial overlap. PNGs decode successfully; PDF
headers, page declarations, xref offsets and EOF markers are valid. Excel/LibreOffice
and a full PDF rendering engine are unavailable, so native application rendering
remains unverified. Sources are observational, model pairs differ by predictor,
and pooled units do not establish protocol equivalence. These checks establish
implementation behavior, not scientific validity or equivalence to older clinical
outputs prepared with different identities and eligibility rules.

The [Layer 3 contract](workflow_contracts.md#layer-3-diagnosis-cfdna-associations--october-6-2026)
records approved rules and the scoped rollback snapshot. Existing edits and
historical runs are preserved; nothing was staged or committed.

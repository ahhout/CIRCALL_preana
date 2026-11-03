# Layer 4 disease tracking acceptance

The linked aggregate verification JSON is currently absent at its recorded local path.
The original acceptance claim and executed commands below are retained as historical
evidence; no substitute result has been selected.

October 6, 2026. The self-contained descriptive Layer 4 release completed report
publication standalone and through the master on the explicitly selected current
workbooks. The investigator chose to keep unsupported CIRCALL MRD annotations
blocked pending source review. Both clinical commands therefore returned the
expected exit code 1 after publishing valid retrospective and blocked reports;
this is a data-quality outcome, not a software acceptance failure.

Final named runs:

- `outputs/layer4_disease_modeling/run_20261006T142704Z_standalone/`
- `outputs/layer4_disease_modeling/run_20261006T142704Z_master/`

The [aggregate verification record](../../outputs/layer4_disease_modeling/validation_20261006T142704Z.json)
passed: four matching workbooks, six identical aggregate evidence files, and three
pixel-identical main PNGs. Each run has 30 verified indexed artifact hashes, 10
verified visible/native publication pairs, 19 privacy-checked workbook/text exports
and 19 verified retained-code hashes. Source observations were reconstructed in
memory to reconcile the reports. There are no clinical patient tables, including
hashed tables under audit.

## Current coverage and source hold

Retrospective inventory MRD retains 62 patients across 77 represented TP1/TP2
patient visits. Count identity is a separate surname-based source population and
must not be combined with these patient IDs.

| Retrospective MRD visit | Represented patients | With clinical result | Quantified | Positive NQ | Negative | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TP1 | 48 | 45 | 8 | 31 | 6 | 3 |
| TP2 | 29 | 27 | 1 | 21 | 5 | 2 |

All positive NQ results in these selected visits have reported upper bounds. One
TP2 group has a resolved disagreement under the approved worst-outcome rule;
no bound becomes a quantified value. Retrospective count preparation retains 224
recorded measurements in 34 source subjects, with 63 genuine zeros and recorded
days from −8 through 29. Diagnostic display selection retains 170 observations
in the full-range view and 117 in the early-window view, both with 34 represented
subjects. Their log figures omit/count 58 and 18 zeros respectively; stored counts
and source-wide summaries retain them all.

Inventory integrity has no definite errors in either cohort; the retrospective
scope has one donor-header whitespace review. CIRCALL's additional MRD check
fails at `cohorte_lal!R2`, outside the retained category scope. The investigator
explicitly declined a new CIRCALL positive-nonquantifiable mapping. The CIRCALL
workbook records the MRD component, sheet and cell. Under the shipped all-components
whole-cohort policy, CIRCALL counts are also held, pooled MRD is blocked and joint
count comparisons are unavailable. Their workbooks contain reasons without
fabricated clinical observations or figures. Sources were not edited.

## Commands actually executed

Python commands used the existing `pre_analysis` Conda environment. Matplotlib's
writable cache was selected with `MPLCONFIGDIR=/tmp/pre_analysis_matplotlib`; it
does not change scientific settings.

```bash
conda run --no-capture-output -n pre_analysis python -m pytest -q \
  tests/disease_modeling tests/orchestration tests/validation tests/sample_statistics \
  tests/advanced_analysis tests/cfdna_associations tests/sample_analysis tests/blast_kinetics \
  --ignore=tests/blast_kinetics/test_workbook_integration.py

conda run --no-capture-output -n pre_analysis python -m pytest -q \
  tests/disease_modeling tests/orchestration/test_run_all_layers.py

./run_all_layers.sh --validate-only

conda run --no-capture-output -n pre_analysis python run.py \
  --config configs/pipeline_disease_modeling.json --validate-only

conda run --no-capture-output -n pre_analysis python -m analysis.disease_modeling \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --circall input/inventaire_CIRCALL_05102026.xlsx \
  --blood-counts input/CIRCALL_wbc_blast_count_01102026.xlsx \
  --retrospective-blasts input/retrospective_blast_count_01102026.xlsx \
  --donors input/cfDNA_donors.xlsx --cohort all --analysis all \
  --blood-count-unit 'x10^9/L' --retrospective-blast-unit 'x10^9/L' \
  --include-controls --pool-mrd \
  --rules configs/definitions/data_integrity.json \
  --definitions configs/definitions/disease_modeling.json \
  --baseline-day-max 1 --baseline-selection latest --overlay-max-day 8 \
  --kinetics-y-scale log --mrd-negative-level 1e-8 --mrd-unknown-level 1e-6 \
  --mrd-positive-nq-level 1e-6 --retrospective-mrd-duplicate-policy worst \
  --jitter-seed 42 \
  --output-dir outputs/layer4_disease_modeling/run_20261006T142704Z_standalone

conda run --no-capture-output -n pre_analysis python run.py \
  --config configs/pipeline_disease_modeling.json \
  --output-dir outputs/layer4_disease_modeling/run_20261006T142704Z_master

conda run --no-capture-output -n pre_analysis python -m tests.validation.validate_disease_modeling \
  --standalone outputs/layer4_disease_modeling/run_20261006T142704Z_standalone \
  --master outputs/layer4_disease_modeling/run_20261006T142704Z_master \
  --report outputs/layer4_disease_modeling/validation_20261006T142704Z.json

bash -n run_all_layers.sh
git diff --check
```

The broad suite passed 344 tests and 81 subtests, with two existing Matplotlib
boxplot deprecation warnings. After the final workbook-format check was added,
the focused suite passed all 43 tests. These counts overlap. The focused suite
includes standalone and master execution from a temporary retained repository
copy physically lacking `sample_analysis`, `blast_kinetics`, `cfdna_associations`,
`advanced_analysis` and `sample_statistics`. It exercises MRD, both count sources,
pooling, comparison reports and publication in that copy, without old helper imports.

Layer 1/2/3 preflights passed. Layer 4 validate-only and the all-layers preflight
returned the expected nonzero result for the current CIRCALL hold, creating no
execution outputs. Final standalone/master publication completed with that same
explicit quality hold; the comparison validator exited zero. The complete
all-layers clinical execution was not run past this failing preflight, and
normalized-model local-workbook tests were not rerun.

## Method and archival verification

The numeric reference was generated from the existing MRD/count methods using
only explicitly synthetic data, then saved as
`tests/fixtures/synthetic_disease_methods_reference.json`. Its original method
hashes and outcomes are retained in the fixture and Layer 4 method provenance;
new tests compare those numbers without importing the original modules. Identical
prepared clinical observations reproduce annotation/bound handling, count and
baseline-selection summaries and pooled status denominators. Approved identity,
harmonized-field, unknown/cache and presentation differences have separate tests;
equivalence to older clinical outputs with different sources or grouping is not claimed.

Layer 4's standalone completion validator is local. Its scientific implementation
does not import old sample-analysis, association or normalized-kinetics helpers.
Shared workbook, integrity, layout, publication and provenance modules remain
explicit dependencies; master dispatch remains part of the retained infrastructure.
The [archival boundary](../replacement_coverage.md#active-execution-and-dependencies)
lists the files to keep. No existing scientific directory or clinical source was
moved or deleted as part of this implementation.

During this work the environment definition and Linux lock were externally moved
from `environments/pre_analysis/` to `environments/`. Both hashes match the
pre-change checkpoint exactly. Active path references were updated without
dependency changes or lock resolution/export. All new execution records preserve
the same lock hash and actual environment package versions.

## Presentation and remaining limits

All three current retrospective figures were visually inspected. The full-range
count axis includes late visits containing only zero counts; zeros break log lines
without acquiring artificial positions. The retrospective MRD plot has no invented
diagnosis point or empty diagnosis-reference axis range. Legends lie below the
data/notes. Workbook tiny fractions and assigned levels use scientific notation
instead of formatting visually as zero; stored literal numbers are reconciled.

PNG decoding and PDF header/page/xref/EOF structure checks passed. Excel/LibreOffice
and full PDF rendering are unavailable, so application rendering is unverified.
Recorded count grouping retains the retrospective surname-collision limitation;
MRD visit populations differ by cohort, and categorical plotting levels do not
establish assay detection limits or measured disease changes. Statistical and
publication checks establish implementation behavior, not scientific validity.
Normalized modeling is disabled in this descriptive release and remains a later
explicitly selected, self-contained increment.

The rollback checkpoint is
`archive/migrations/layer4_before_20261006T134427Z/implementation_before.tar.gz`.
Existing edits, sources, failed/development runs and acceptance evidence remain
preserved. No files were staged or committed.

# Integration and source-relocation evidence — October 1, 2026

Historical executed commands and findings; use the current README for new runs.

## Migration checkpoint and rollback

The pre-migration working tree, including untracked code and configuration, is
retained under `archive/migrations/repository_layout_20261001T094022Z/` with a source
archive, file hashes, Git patch/status and relocation map. Validation uses the
investigator-selected October 1 blood-count workbook in both the reference and new
runs. Conda locks and scientific settings were retained.

Restore only migration-owned code/configuration after checking the saved after
hashes against the current files. Preserve subsequent edits, clinical inputs,
validation outputs, and historical archives. Do not use a repository-wide reset
or clean to roll back this migration.

## Migration validation — October 1, 2026

All 161 tests passed: 57 sample-analysis, 31 orchestration/publication, 14 historical
runner, 6 validation-tool, 15 association, 35 synthetic kinetics and 3 local-workbook
kinetics checks. All three active workflows completed both standalone and together.
Preflight also passed when the root runner was launched from `/tmp`.

The [reference comparison](../../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/comparison_final.json)
and [standalone/integrated comparison](../../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/comparison_standalone.json)
both passed: 74 table/workbook files, 53 worksheets, 103 pixel-identical images,
two nonempty PDFs and the identical normalized model summary. Biological input
hashes and normalized scientific settings matched for all three workflows.

[Source-cell validation](../../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/source_validation.json)
passed for 401 endpoint records, and workbook rebuilding succeeded from the hidden
audit CSVs. [Artifact integrity checks](../../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/audit_integrity.json)
verified 278 indexed hashes, all 64 visible/audit copies, unchanged environment
definitions/locks, and agreement between executed code hashes and current files.
The [final results](../../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/final) demonstrate
the clean output layout. Historical reproduction was covered by synthetic runner
tests; the full historical clinical workflow was not rerun for this migration.

## Two-cohort kinetics consolidation — October 1, 2026

The investigator-selected retrospective and CIRCALL count sources now run through
canonical descriptive kinetics. The [validated result](../../archive/results/compatibility_20261007T073346593956Z/kinetics_consolidated_20261001/sample_analysis/kinetics)
contains cohort-labeled blast figures, the existing CIRCALL WBC/MRD figures and
aggregate summaries. The separate normalized model is excluded from default runs.

Validation performed in `pre_analysis`:

```bash
conda run -n pre_analysis python -m pytest -q tests/orchestration tests/sample_analysis tests/blast_kinetics --ignore=tests/blast_kinetics/test_workbook_integration.py
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_kinetics.json --validate-only
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_kinetics.json --output-dir output/kinetics_consolidated_20261001
conda run --no-capture-output -n pre_analysis python run.py --validate-only
```

The tests passed: 132 tests and 63 subtests, with nine numerical/deprecation warnings.
Both preflights passed and the focused integrated run completed. All 16 publication
hashes, selected source hashes and executed code hashes were verified. The five
existing CIRCALL PNGs and blood-count summary are byte-identical to the prioritized
`run_2026-10-01_11-08-13.824502_UTC` artifacts. The new cohort overlay was visually
inspected; large retrospective counts compress smaller values on its linear axis,
so the existing cohort-specific figures remain useful. See the
[aggregate verification record](../../archive/results/compatibility_20261007T073346593956Z/kinetics_consolidation_validation_20261001.json).

The broader unrelated analyses and normalized-engine local-workbook tests were not
rerun. These checks establish implementation behavior, not biological equivalence
or the validity of pooling the cohorts. Input count/fraction discrepancies remain
unresolved; supplied counts are retained without deriving replacements.

## Retrospective source relocation and reformat — October 1, 2026

The authorized source migration created
`input/retrospective_blast_count_01102026.xlsx` and retired the former top-level
folder to `archive/retired/blast_kinetics_workflow_20261001/`. All 24 archived files
retain their original hashes. Old manifests still identify the original locations;
use `archive/migrations/retrospective_input_20261001/relocation.json` to resolve them.
The original workbook remains there byte-for-byte. The separate code-only snapshot
is `archive/migrations/retrospective_input_20261001/code_before.tar.gz`.

Reformatting used the reviewed helper below. To reproduce, use fresh output/report
paths; the example source is now the retained original:

```bash
conda run -n pre_analysis python -m analysis.sample_analysis.migrate_retrospective_blasts --source archive/retired/blast_kinetics_workflow_20261001/data/blast_kinetics_data.xlsx --output input/retrospective_blast_count_review.xlsx --report output/retrospective_reformat_review.json
```

The helper retains every mapped source value, remaps formula references and restores
numeric XML/caches that openpyxl would otherwise discard or round. All 5,948 mapped
value/formula checks passed; 448 active-sheet and 52 unused-sheet formula caches
were preserved. An interrupted first attempt left three new files empty; the
original source was hash-verified before recovery, and the empty workbook/report
were retained with `interrupted_empty_` names in the migration evidence directory.

Validation actually performed:

```bash
conda run -n pre_analysis python -m pytest -q tests/sample_analysis tests/orchestration tests/blast_kinetics
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_kinetics.json --validate-only
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_kinetics.json --output-dir output/kinetics_reformatted_input_20261001
conda run --no-capture-output -n pre_analysis python run.py --validate-only
conda run -n pre_analysis python output/retrospective_input_validation_20261001/verify.py --root /home/arnohoutman/projects/pre_analysis --output output/retrospective_input_validation_20261001/report.json
```

All 140 tests and 63 subtests passed (nine existing numerical/deprecation warnings).
Both preflights passed and the focused integrated run completed. Eight kinetics
PNGs and two summary CSVs are byte-identical to the prior consolidated run. All 16
publication hashes, current source hashes and executed code hashes were checked.
The normalized-model prepared frame matches the original source exactly, and its
refitted summary matches the original October 1 run. PDFs were validated as
artifacts, not compared byte-for-byte. Excel/LibreOffice rendering was unavailable;
workbook values, formulas, headers and format settings were checked programmatically.
See the [verification record](../../archive/results/compatibility_20261007T073346593956Z/retrospective_input_validation_20261001/report.json)
and [new results](../../archive/results/compatibility_20261007T073346593956Z/kinetics_reformatted_input_20261001/sample_analysis/kinetics).

For rollback, compare `after.sha256` against current files before restoring only
affected code/configuration/documents from `code_before.tar.gz`; new helper/test
files are listed separately. The original folder can be relocated back only if
its former path is free. Preserve the reformatted workbook and new results as
migration evidence. No repository-wide reset, deletion, or clinical overwrite is
part of rollback.

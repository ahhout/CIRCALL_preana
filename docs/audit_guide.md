# Auditing and validating layout 2 runs

## Unified layered runs

Both `python run.py` and `./run_all_layers.sh` invoke the integrated runner with
`configs/pipeline_layers.json`. New combined runs live under
`outputs/layered/run_<timestamp>/`, with four numbered workflow directories and
one root `.audit/`. The root manifest records `pipeline_kind: layered`, a unique
`run_id`, explicit `failure_policy`, execution timestamps and per-layer states.
It hashes the launcher as well as Python code; the combined profile is the hashed
configuration, and each layer retains its source, settings and environment evidence.
Its settings match the four standalone profiles through a configuration parity test.

Execution completion and data quality remain distinct. A layer can have
`status: complete` because its reports were validated while `quality_status:
errors_found` describes blocked cohorts. The overall run then has `status: failed`
and exit 1. Use each layer's provenance/cohort records and local log to interpret
the cause. The [unified contract](workflow_contracts.md#unified-layered-orchestration--october-6-2026)
defines continuation, preflight, interruption and changed-source handling.

```bash
./run_all_layers.sh --validate-only
./run_all_layers.sh --output-dir outputs/<fresh-combined-run>
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/orchestration
```

The launcher no longer treats a known clinical quality hold as a reason to skip
all full execution. The current CIRCALL MRD hold is preserved. Validate-only still
publishes nothing and returns nonzero for that hold. Since October 7, plain
`python run.py` selects the same layered profile. The former combined default
remains explicit through `--config configs/pipeline_all.json`; individual-layer
output roots and historical runs remain unchanged.

The unified launcher passed 391 portable tests and 81 subtests on October 6,
including real shell invocations on synthetic successful and blocked sources.
The real-source validate-only check returned the expected Layer 4 quality hold;
full clinical execution and local-workbook kinetics tests were not rerun.
Exact validation commands and the rollback checkpoint are in the
[unified orchestration validation record](../archive/migrations/unified_layers_before_20261006T152102522851Z/validation.json).

The October 7 default cutover passed 392 portable tests and 81 subtests. The
synthetic success case exercises plain `python run.py` without `--config`;
explicit compatibility dispatch remains tested. Real-source default preflight
retained the expected CIRCALL hold. The
[default cutover validation record](../archive/migrations/layered_default_before_20261007T065636726624Z/validation.json)
records exact commands, scope and rollback evidence; no full clinical execution
or local-workbook kinetics tests were rerun.

## Layer 4 disease tracking

Layer 4 has local preparation/method/reporting code and retains only shared reading,
integrity, publication and provenance infrastructure. See the
[Layer 4 guide](disease_modeling.md#files-to-retain-when-archiving-old-workflows) for
the explicit archival boundary. Standalone and master execution are tested in a
temporary repository copy without any legacy scientific workflow directory.
The numeric reference fixture contains only synthetic outcomes and original method
hashes, so new tests do not import old scientific helpers.

Only aggregate reports, source-cell findings, workbooks and figures are exported;
patient-level MRD/count tables are not retained under `.audit`. Completion reconstructs
source observations in memory and reconciles the aggregate reports and workbook
values. Both visible and native copies have verified publication checksums.
Unsupported CIRCALL MRD annotations remain blocked at the investigator's request;
full Layer 4 execution publishes valid retrospective and blocked reports before
its expected nonzero quality exit. Validate-only and the all-layers preflight stop
on that quality failure without generating results.

```bash
conda run -n pre_analysis python -m pytest -q tests/disease_modeling tests/orchestration
conda run -n pre_analysis python run.py --config configs/pipeline_disease_modeling.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_disease_modeling.json
```

## Layer 3 diagnosis associations

Layer 3 uses `analysis/association_methods.py`, shared with the compatibility
association entrypoint through re-exported imports. Preparation, workbook reading
and older row-export paths remain separate. The extraction retains identical
method definitions; `tests/fixtures/synthetic_association_methods_reference.json`
records pre-extraction results for all six predictors with complete, missing,
small and constant-predictor populations. Layer 1–3 source-state helpers live in
`analysis/source_state.py`; duplicate-key parsing lives in
`analysis/configuration.py`. Layer-specific scientific definition checks are unchanged.

Check the numerical reference and execute all four layers standalone and together
in a temporary repository copy without the older scientific packages:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/advanced_analysis/test_methods_reference.py tests/orchestration/test_layer_dependencies.py
```

The isolation test removes older packages only by excluding them from its temporary
copy. It does not move repository files or clinical data. Compatibility execution
and validators remain required for capabilities not yet migrated.

The October 6 dependency extraction passed 378 portable tests and 81 subtests,
including all-layer standalone/integrated execution with older packages absent.
The 24 frozen numerical cases and three unchanged diagnostic PNGs check the
method boundary. Current-source preflight passed Layers 1–3 and retained the
expected Layer 4 CIRCALL hold; no full clinical execution was rerun. Exact commands,
hash checks and rollback evidence are in the
[dependency validation record](../archive/migrations/dependency_boundary_before_20261006T150804113789Z/validation.json).

Layer 3 uses the same publication and source-verification mechanism as Layers 1
and 2. A single-layer run publishes direct cohort folders; a mixed run groups
them under `03_advanced_analysis/`. Full native evidence is retained under
`.audit/workflows/03_advanced_analysis/`: aggregate result JSON, hashed prepared
patient observations, diagnosis source rows with measurement states and source
coordinates, integrity findings, residual/influence tables and diagnostic plots.
Only the six-tab aggregate workbooks and main PNG/PDF clinical comparisons are
published. Unavailable fits are not execution failures. Cohort gate failures
publish blocked reports and permit independent scopes before the final nonzero
quality exit; both cohorts must complete for compatible pooled descriptions.

```bash
conda run -n pre_analysis python -m pytest -q tests/advanced_analysis tests/cfdna_associations tests/sample_statistics tests/orchestration tests/validation
conda run -n pre_analysis python run.py --config configs/pipeline_advanced_analysis.json --validate-only
./run_all_layers.sh --validate-only
```

The shared completion validator checks artifact hashes, workbook reconciliation,
PNG decoding, PDF header/page/xref/EOF structure, source-derived patient medians
and per-predictor statistical recalculation before publication. It rechecks source
hashes after execution and validates literal workbook strings to avoid accidental
Excel formula interpretation. Excel/LibreOffice rendering and a full PDF rendering
engine are not available in the current environment; main PNG figures are reviewed
visually, with matching PNG/PDF figure content generated from the same Matplotlib
figure. Software checks do not establish scientific validity.

Compare explicitly named standalone/master runs using:

```bash
conda run -n pre_analysis python -m tests.validation.validate_advanced_analysis \
  --standalone outputs/layer3_advanced_analysis/<standalone-run> \
  --master outputs/layer3_advanced_analysis/<master-run> \
  --report outputs/layer3_advanced_analysis/<fresh-validation>.json
```

The validator checks native numerical evidence, workbook content, PNG pixels,
publication/index/code/source hashes, and privacy of workbook/text exports against
identifying values held only in memory from the selected patient/control sources.
It emits counts and error types without clinical values. It does not compare these
new preparation rules to older clinical results. The approval, limitations and
rollback snapshot are in the [Layer 3 contract](workflow_contracts.md#layer-3-diagnosis-cfdna-associations--october-6-2026).

Layer 1 is available as the explicitly selected `data_integrity` workflow through
`configs/pipeline_integrity.json`. It publishes cohort Excel reports under
`01_data_integrity/` and retains complete sanitized findings under
`.audit/workflows/01_data_integrity/`. Its report completion and data quality are
separate: data errors produce exit code 1 after valid reports are published.
See the [integrity guide](data_integrity.md). Compatibility profile settings and
the `canonical`, `cfdna_associations` and `blast_kinetics` workflow names remain supported.

## Locations and ownership

A run root has visible result folders and a hidden `.audit/` directory:

```text
.audit/
├── run_manifest.json
├── resolved_config.json
├── artifact_index.json
├── logs/
└── workflows/
    ├── 01_data_integrity/
    ├── 02_sample_statistics/
    ├── 03_advanced_analysis/
    └── 04_disease_modeling/
```

Default runs select `data_integrity`, `sample_statistics`, `advanced_analysis`
and `disease_modeling`. Explicit `configs/pipeline_all.json` runs select `canonical`
and `cfdna_associations`, retaining their `sample_analysis/` and
`cfdna_associations/` directories. `configs/pipeline_kinetics.json` selects only canonical
kinetics, published in `sample_analysis/kinetics/`. The separate `blast_kinetics`
engine is retained for explicit normalized-model compatibility runs.

Only selected workflow directories exist; explicit normalized compatibility runs
publish under `blast_kinetics/`. Root metadata records
`output_layout_version: 2`. Inner engines preserve their native output structure
and version-1 scientific provenance. Use the root manifest to determine publication
success; native engine success alone does not prove successful publication.

`publications` maps each visible file to its audit source and SHA-256. Both copies
must match. The index includes hidden audit evidence and excludes disposable
caches, temporary publication files, and the index itself. Its ownership lists
also record cache paths and directories for strict replacement checks. Code hashes
cover Python files recursively under `analysis/` and `run.py`; environment locks,
actual package versions, source hashes, and resolved scientific settings remain
recorded. The root manifest lists unavailable analyses and independent failures.

Engine results are validated before copying reviewed deliverables to a temporary
folder. An atomic rename exposes the completed visible workflow folder. Copy or
validation failures leave audit evidence and fail the run. New artifact names are
audit-only until added to the publication contract in `analysis/outputs.py`.
Diagnostic plots and prepared row-level data remain local inside the audit tree;
hiding files is an organizational convention, not access control.

Canonical final reports flatten the old `spreadsheet/` folder. Association results
flatten the engine's repeated `cfdna_associations/` wrapper. Topic and predictor
subfolders are preserved. Workbook contents still reference the retained engine
CSVs, and the workbook's source-run field identifies the audit engine directory.

## Existing outputs and replacement

The investigator archived all historical `output/` contents on October 7 while
retaining every layered `outputs/` result. The
[relocation record](../archive/migrations/archival_cleanup_20261007T073346593956Z/relocation.json)
maps original paths into `archive/results/compatibility_20261007T073346593956Z/`.
Pass the mapped run path explicitly to historical validators and report helpers;
use a fresh destination for generated reports. Recorded commands and immutable
manifests below retain their original paths as historical evidence. Documentation
links to existing results have been updated; no automatic path alias is installed.

Old runs retain their internal layouts and metadata; archived paths are listed
in the relocation record. Workbook rebuilding, source-cell
validation, and integrated comparison accept old native roots and new run roots;
workbook rebuilding also accepts the visible `sample_analysis/` directory.

Integrated runs never overwrite existing paths. Normalized kinetics retains its
explicit `--force` option, limited to a complete layout-2 standalone kinetics run
with a matching ownership index. Unknown files/directories, symlinks and modified
indexed artifacts are refused. The previous run is retained in a hidden sibling
`.NAME.previous-*/run`; on failure it is restored and the failed attempt is retained
beside that backup. Historical flat outputs are not replaced by the new CLI.

## Commands

Run from the repository root. Rebuild workbooks from retained CSVs into a fresh
folder, without rerunning any statistical analysis:

```bash
conda run -n pre_analysis python -m analysis.sample_analysis.stats_workbooks --run-dir output/<run> --output-dir output/<new-report-folder>
```

Compare a reference run (old integrated, old standalone collection, or layout 2)
with a new run. The comparison traverses the complete native evidence, including
hidden prepared tables and diagnostics, rather than only the visible copies:

```bash
conda run -n pre_analysis python -m tests.validation.compare_integrated --standalone-dir output/<reference> --integrated-run output/<new-run> --report output/<fresh-comparison>.json
conda run -n pre_analysis python -m tests.validation.validate_canonical --run-dir output/<new-run> --output output/<fresh-source-validation>.json
```

Biological source hashes must match. Resolved scientific settings must match after
normalizing output locations and replacing relocated source/configuration paths
with their verified input hashes. A relocated kinetics profile can have a different
file hash; all of its resolved scientific settings are still compared. Workbook
comparison normalizes only the source-run location. Numeric tolerances remain
rtol=1e-9 / atol=1e-12 for canonical and kinetics and rtol=1e-10 / atol=1e-12 for
associations. CSV ordering, missingness, workbook sheets and image pixels remain
checked. Existing manifests and reports are never rewritten for comparison.

Run all portable suites in the consolidated environment:

```bash
conda run -n pre_analysis python -m unittest discover -s tests/sample_analysis -v
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -v
conda run -n pre_analysis python -m unittest discover -s tests/validation -v
conda run -n pre_analysis python -m pytest -q tests/cfdna_associations
conda run -n pre_analysis python -m pytest -q tests/blast_kinetics --ignore=tests/blast_kinetics/test_workbook_integration.py
```

The separate local-workbook checks require the original configured kinetics data:

```bash
conda run -n pre_analysis python -m pytest -q tests/blast_kinetics/test_workbook_integration.py
```

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

The [reference comparison](../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/comparison_final.json)
and [standalone/integrated comparison](../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/comparison_standalone.json)
both passed: 74 table/workbook files, 53 worksheets, 103 pixel-identical images,
two nonempty PDFs and the identical normalized model summary. Biological input
hashes and normalized scientific settings matched for all three workflows.

[Source-cell validation](../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/source_validation.json)
passed for 401 endpoint records, and workbook rebuilding succeeded from the hidden
audit CSVs. [Artifact integrity checks](../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/audit_integrity.json)
verified 278 indexed hashes, all 64 visible/audit copies, unchanged environment
definitions/locks, and agreement between executed code hashes and current files.
The [final results](../archive/results/compatibility_20261007T073346593956Z/layout_validation_20261001T094022Z/final) demonstrate
the clean output layout. Historical reproduction was covered by synthetic runner
tests; the full historical clinical workflow was not rerun for this migration.

## Two-cohort kinetics consolidation — October 1, 2026

The investigator-selected retrospective and CIRCALL count sources now run through
canonical descriptive kinetics. The [validated result](../archive/results/compatibility_20261007T073346593956Z/kinetics_consolidated_20261001/sample_analysis/kinetics)
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
[aggregate verification record](../archive/results/compatibility_20261007T073346593956Z/kinetics_consolidation_validation_20261001.json).

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
See the [verification record](../archive/results/compatibility_20261007T073346593956Z/retrospective_input_validation_20261001/report.json)
and [new results](../archive/results/compatibility_20261007T073346593956Z/kinetics_reformatted_input_20261001/sample_analysis/kinetics).

For rollback, compare `after.sha256` against current files before restoring only
affected code/configuration/documents from `code_before.tar.gz`; new helper/test
files are listed separately. The original folder can be relocated back only if
its former path is free. Preserve the reformatted workbook and new results as
migration evidence. No repository-wide reset, deletion, or clinical overwrite is
part of rollback.

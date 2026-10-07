# Layer 1 — data integrity

Layer 1 checks the explicitly selected harmonized inventories without changing
them. It creates one Excel workbook per cohort, with CIRCALL patient and control
sheets kept distinct. It does not fit models, normalize identifiers, merge samples,
recalculate Excel or apply analytical exclusions.

Current extraction and annotation rules follow the
[October 7 shared amendment](workflow_contracts.md#shared-sample-annotations-and-receipt-revision--october-7-2026):
derive yes/no from `dna_id`; use canonical literal `na`; blank sample IDs mean
receipt unclassified; available volume applies only to plasma/CSF. Earlier
acceptance sections describe their historical source/rule versions.

## Commands and selection

Use the existing Conda `pre_analysis` environment. Each Layer 1 invocation creates
a fresh run under `outputs/layer1_data_integrity/run_<timestamp>/`:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json
```

The dedicated profile selects `input/cfDNA_inventaire_retrospective_05102026.xlsx`
and `input/inventaire_CIRCALL_05102026.xlsx`. Profile paths are relative to the
profile. No workbook version is selected by modification time.

The independent entrypoint uses exactly the same rules, reports and audit helpers:

```bash
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --circall input/inventaire_CIRCALL_05102026.xlsx --cohort all
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --cohort retrospective
conda run -n pre_analysis python -m analysis.data_integrity --circall input/inventaire_CIRCALL_05102026.xlsx --cohort circall --no-include-controls
```

`python run.py --workflow data_integrity` accepts the same source/cohort options.
Controls are included by default for CIRCALL; the shipped profile also explicitly
selects retrospective donors. Standalone retrospective controls require --donors.
The patient sheets are `Inventaire` and `cohorte_lal`; controls use `cohorte_control`
and donor sheet `Feuil1`. Templates and count workbooks are outside
this version. `--rules PATH` selects an explicit versioned rules JSON.
Explicit CLI `--output-dir` overrides a profile destination; a profile
`output-dir` overrides the default. The new default applies to standalone Layer 1
and integrity-only master profiles; other workflow defaults are unchanged.

Integrity preflight checks runnable configuration and captures source availability;
it does not assert that a workbook is valid. Missing files, missing sheets, broken
workbooks and data defects are findings in the subsequent report. The selected
source state is checked again during execution. A source changing mid-run invalidates
acceptance. A missing cohort source does not block reports for independent sources.

## Excel output and occurrence counting

```text
outputs/layer1_data_integrity/run_<timestamp>/
  01_data_integrity/
    retrospective/integrity_report.xlsx
    circall/integrity_report.xlsx
  .audit/
    run_manifest.json
    artifact_index.json
    workflows/01_data_integrity/
      run_manifest.json
      retrospective/findings.json
      circall/findings.json
```

Only selected cohorts appear. Native copies of the Excel files also remain under
the workflow audit directory; publication records verify both copies by hash.

| Tab | Contents |
| --- | --- |
| Summary | Data-quality and report-generation outcomes, source path/hash, inspected rows, error/review occurrences, unique affected data rows, sheet breakdown and native Excel chart |
| Issues | One group per source workbook, sheet, field, rule and severity; occurrence count, references when fewer than ten, suggested action, stable rule ID, category and aggregate context |
| Coverage | Assessed and unavailable/not-applicable observations with reasons, including unknown semantic fields and deferred identifier checks |
| Definitions | Field meanings, units, rule severities, calculations, tolerances and counting convention |

A distinct affected cell counts once within its group. Repeated detections do not
inflate the count. Different rules affecting one cell count separately. Unique
affected-row counts deduplicate those findings and exclude the header row.
Structural problems without a cell count once per distinct scope/field and have
no fabricated coordinates. Zero-occurrence groups are omitted.

All cell references are shown for **1–9 occurrences**, sorted by row and column.
For **10 or more**, the reference cell is blank. No other Excel tab circumvents
this limit. Complete findings remain in the audit JSON for reproducibility.
Errors sort before review findings, followed by descending occurrence counts and
stable source/sheet/field/rule order. Reports use Excel 2021-compatible filters,
frozen panes, wrapped text and an embedded chart.

Summary additionally shows distinct affected cells, distinct error/review cells
and distinct error/review rows. These reconcile repeated rule detections without
hiding any finding. Categories distinguish Structure, Formula, Logic, Formatting
and Interpretation. Context counts describe, for example, how many occurrences
are on blank-sample-ID future rows under the CIRCALL convention. Context neither
changes severity nor adds a new grouping key or extra cell references.

Source values, names, dates of birth and identifier values are never copied to
reports or logs. Unknown headers are represented by column position to prevent
accidental header content from leaking into reports. Known field names and source
locations identify issues for local workbook review.

## Rules and limitations

The authoritative rule configuration is
[`data_integrity.json`](../configs/definitions/data_integrity.json); the approved
decisions are in the [scientific contract](workflow_contracts.md#layer-1-integrity-contract--october-5-2026).
The common reader preserves raw cells, formulas, cache types, formats and coordinates.
It checks headers before forming field mappings and retains formula-only rows.
Formatting-only rows are ignored.

The ten extraction/DNA headers are required, but measurements are not required on
every row. Missing inputs and scheduled future observations do not automatically
constitute errors. Recorded numeric zero remains a measurement. A formula returning
an intentionally empty string is distinguished from an absent saved result.

Decimal-comma numeric text is interpretable, but still reported because Excel's
`ISNUMBER` does not accept text cells. Qualifications, multiple-volume annotations
and text dates remain review findings. Dates are never guessed from ambiguous
strings. Unassessed clinical fields are identified explicitly in Coverage.

Historical `?` inputs remain readable as explicit unknowns; adopted October 7
sources standardize that literal marker to `na`. Original distinctions survive
in the source backups. DNA-ID-derived extraction state **no** makes calculations inapplicable.
Recorded numbers or methods on those rows produce findings without being discarded.
Under the investigator's subsequent clarification, these contradictions are
classified as **logic errors**, while retaining the numbers
and leaving the correct replacement unresolved. Historically, the initial status migration moved 51 explicit date notes
into this column, cleared incompatible text, and preserved all 13 conflicting
numeric volumes for manual review. Current extraction status is yes for an actual
filled DNA ID and no for a blank/missing DNA ID; unavailable columns, formula IDs
and errors remain unassessed. Measurements do not establish extraction.

Future-visit formula defects remain errors. Their row context explains why results
are unavailable; it does not excuse artificial zeros, division errors or incorrect
identifier references. Recognized workflow notes in dates/measurements, aliquot
counts supplied in volume fields and written-unit measurements receive specific
review reasons and actions. They are not generically labelled malformed values.
Cross-row day references remain review findings even when current dates match.

Formula inspection recognizes direct A1 references and ranges, broken references,
self references and identifier dependencies in measurement formulas. Cross-row or
cross-sheet references require review. Indirect references and unsupported named
references are marked unassessed rather than evaluated. This is not a complete
Excel calculation engine or a proof that all cached results are current.

## Exit status and audit

Execution completion and data quality are separate. Native `status=complete`
means the report artifacts were generated and validated; `quality_status` is
`no_issues_detected`, `review_needed` or `errors_found`. Independent report-generation
failures are recorded per cohort, while successful reports can still be published.

Warnings alone return exit code 0. Definite data errors or execution failures
return exit code 1. For an integrated run, data errors make the overall run status
`failed`, with completed report publications retained. For standalone runs, root
report completion is retained alongside the quality status and nonzero exit.
Inspect the manifests rather than interpreting an exit code as missing reports.

The existing audit records capture explicit sources, hashes, resolved rules, code,
package versions, environment lock, command and ISO execution times. No source
files are saved. Prior results are never overwritten; use another destination.

## Verification

Targeted and orchestration checks:

```bash
conda run -n pre_analysis python -m unittest discover -s tests/validation -v
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -v
```

Tests cover rule behavior, the 0/1/9/10/11 occurrence boundaries, stable counts,
identifier suppression, formula caches, source preservation, independent cohorts,
partial report generation, standalone/master equivalence and output safety.
Software checks establish these behaviors, not scientific validity of the data.
Excel structure/chart objects are checked programmatically; local Excel rendering
is needed to confirm appearance on the investigator's machine.

## Acceptance run — October 5, 2026

Implemented Layer 1 was run on both adopted workbooks, including CIRCALL controls.
The 28 validation tests and 35 orchestration tests passed (63 total). The validation
suite includes 17 Layer 1 tests. Orchestration tests emitted a Matplotlib cache
fallback warning; no additional dependency installation was needed.

Commands actually run at the original locations (subsequently relocated below):

```bash
conda run -n pre_analysis python -m unittest discover -s tests/validation -v
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -v
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --output-dir output/layer1_integrity_20261005
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --circall input/inventaire_CIRCALL_05102026.xlsx --cohort all --output-dir output/layer1_integrity_standalone_20261005
conda run -n pre_analysis python output/layer1_integrity_validation_20261005/verify.py --root . --integrated output/layer1_integrity_20261005 --standalone output/layer1_integrity_standalone_20261005 --output output/layer1_integrity_validation_20261005/verification.json
```

Both full inspections returned the intended exit code 1 for definite source errors
after publishing both cohort reports. Retrospective: 0 errors and 103 review
occurrences across 61 affected rows. CIRCALL: 404 error and 2 review occurrences
across 140 affected rows, all on the patient sheet. These are rule occurrences,
not patient counts; multiple findings can refer to the same cell or sample.

The [verification record](../outputs/layer1_data_integrity/validation/verification_20261005/verification.json)
confirms identical standalone/integrated findings and Excel tab values, 20 artifact
hashes, four visible/native publication pairs, unchanged input hashes and matching
executed code hashes. The reports are available under
[`outputs/layer1_data_integrity/run_20261005/01_data_integrity/`](../outputs/layer1_data_integrity/run_20261005/01_data_integrity).
The real workbooks were never saved or recalculated. The other scientific
workflows were not rerun; they still require separate migration to the new schema.

At the investigator's request, the accepted run, standalone comparison run and
verification evidence were relocated under `outputs/layer1_data_integrity/`.
All file hashes were preserved. Historical manifests retain their execution-time
paths; use the [relocation record](../archive/migrations/layer1_output_location_20261005/relocation.json)
to resolve them. The output-default change is covered by the additional targeted
default/override test; it does not change the historical run's issue counts.

## Extraction-state and contextual reporting acceptance — October 5, 2026

Following the approved source correction, 51 explicit not-extracted notes now live
in `extraction_status`; incompatible text fields were cleared. The 13 numeric
contradictions were preserved and independently compared with the archived source.
All four active/archive source hashes match the correction relocation record.

The reporting revision retains future-row formula errors, classifies extraction
contradictions as logic errors, recognizes explicit unknowns, and distinguishes
workflow notes, aliquot-count annotations and written-unit measurements. Summary
shows rule occurrences separately from distinct cells and rows. The grouped Issues
tab adds categories/context without changing the fewer-than-ten reference rule.

Validation performed:

```bash
conda run -n pre_analysis python -m unittest discover -s tests/validation -q
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -q
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --output-dir outputs/layer1_data_integrity/run_20261005_logic_review
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --circall input/inventaire_CIRCALL_05102026.xlsx --cohort all --output-dir outputs/layer1_data_integrity/validation/logic_review_standalone_20261005
conda run -n pre_analysis python outputs/layer1_data_integrity/validation/verification_20261005/verify.py --root . --integrated outputs/layer1_data_integrity/run_20261005_logic_review --standalone outputs/layer1_data_integrity/validation/logic_review_standalone_20261005 --output outputs/layer1_data_integrity/validation/logic_review_verification_20261005.json
```

All 34 validation and 35 orchestration tests passed (69 total). Both inspections
published both reports and returned the expected exit code 1 for source errors.
Retrospective: 13 error occurrences on 13 distinct cells/rows, plus 13 review
occurrences. CIRCALL: 404 error occurrences on 403 distinct cells across 138 rows,
plus two review occurrences. These counts describe the corrected source versions.

The [verification record](../outputs/layer1_data_integrity/validation/logic_review_verification_20261005.json)
confirms identical standalone/master findings and Excel tab values, 20 artifact
hashes, four publication pairs and current source/rule/code hashes. Reports are
under [`run_20261005_logic_review`](../outputs/layer1_data_integrity/run_20261005_logic_review/01_data_integrity).
Previous reports remain intact. Excel was checked programmatically; visual
rendering was unavailable. No scientific models were run.

Single-layer integrity runs now publish `retrospective/` and `circall/` directly
inside the run folder. `.audit/` is retained for provenance and validation. Mixed
workflow runs retain their workflow directories; other historical runs keep their
original layout. The explicitly requested `run_20261005` was relocated with a
verified migration record under `archive/migrations/flatten_layer1_20261006/`.


Retrospective controls were added on October 6: the profile explicitly selects
`--donors input/cfDNA_donors.xlsx`, sheet `Feuil1`. Its findings appear within the
retrospective report with source workbook and sheet distinguished, and its hash
is recorded separately. The sparse donor schema requires Donor and the supplied
plasma ng/mL endpoint, not patient-inventory columns. Numeric/reference/cache checks
apply; the fixed-volume conversions lack independent protocol metadata, so those
arithmetic checks are explicitly unavailable. `--no-include-controls` excludes
both cohorts' control sources.

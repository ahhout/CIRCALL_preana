# Layer 1 — data integrity

Layer 1 checks the explicitly selected harmonized inventories without changing
them. It creates one Excel workbook per cohort, with CIRCALL patient and control
sheets kept distinct. It does not fit models, normalize identifiers, merge samples,
recalculate Excel or apply analytical exclusions.

Current extraction and annotation rules follow the
[October 7 shared amendment](../workflow_contracts.md#shared-sample-annotations-and-receipt-revision--october-7-2026):
derive yes/no from `dna_id`; use canonical literal `na`; blank sample IDs mean
receipt unclassified; available volume applies only to plasma/CSF. Earlier
acceptance sections describe their historical source/rule versions.

## Selection and report scope

Use the [README pipeline commands](../../README.md#run) and
[master configuration](../../configs/pipeline_layers.json) for current sources and
settings. Layer 1 runs internally on every full execution; direct layer commands
and the former integrity selector profile are retired.

The patient sheets are `Inventaire` and `cohorte_lal`; controls use `cohorte_control`
and donor sheet `Feuil1`. Controls are included by default, but retrospective
controls require an explicit donor source. `--no-include-controls` excludes both
cohorts' control sources. Templates and count workbooks are outside this inspection.
`--rules PATH` selects a versioned rules JSON.

Source availability and report completion are distinct; missing/broken workbooks,
missing sheets and data defects become report findings without preventing reports
for independent sources. See [preflight and completion](../audit_guide.md#preflight-and-completion)
for the shared execution and exit policy.

## Excel output and occurrence counting

Paths below are relative to the layer's visible results directory, located as
shown in [README](../results.md):

```text
retrospective/integrity_report.xlsx
circall/integrity_report.xlsx
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
[`data_integrity.json`](../../configs/definitions/data_integrity.json); the approved
decisions are in the [scientific contract](../workflow_contracts.md#layer-1-integrity-contract--october-5-2026).
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

## Quality and verification

The report's `quality_status` is `no_issues_detected`, `review_needed` or
`errors_found`. Missing reports and generated reports containing errors are
different outcomes; inspect cohort report-generation status and the
[audit manifests](../audit_guide.md#preflight-and-completion).

The `tests/data_integrity` and `tests/orchestration` suites cover rule behavior, the
0/1/9/10/11 occurrence boundaries, stable counts, identifier suppression, formula
caches, source preservation, independent cohorts, partial report generation and
standalone/master equivalence. Use the [central validation commands](../audit_guide.md#validation-commands).
Excel structure/chart objects are checked programmatically; local Excel rendering
is needed to confirm appearance. These checks do not establish scientific validity.

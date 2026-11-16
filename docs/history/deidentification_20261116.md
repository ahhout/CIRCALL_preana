# Working-input deidentification acceptance — November 16, 2026

Five pseudonymised working copies passed package checks, integrated preflight and
a complete four-layer comparison against their original sources. Original files,
default source selection, scientific definitions and scientific engine code were
preserved. The [operational guide](../deidentification.md) owns current commands;
the [contract amendment](../workflow_contracts.md#pseudonymised-working-inputs--november-16-2026)
records the investigator-approved privacy rules and retained identification risks.

## Checkpoint and execution

Pre-change HEAD was `90954b1780be9acba3af631fe9557132e85f965a`, with a clean working
tree, recorded in `.maintenance/deidentification_20261116/prechange.json`.
Git retains the original code/configuration/documentation state; neither Git nor
that small record contains clinical inputs or a private mapping.

Environment: existing `pre_analysis` Conda environment on Ubuntu-24.04 WSL2.
The source master was `configs/pipeline_layers.json`. Original/copy acceptance
masters were saved explicitly in `.maintenance/deidentification_20261116/`,
with identical options, seeds and assessment time `2026-11-16T12:00:00+01:00`.

```bash
python3 run.py --config .maintenance/deidentification_20261116/baseline_master.json --validate-only
python3 run.py --config .maintenance/deidentification_20261116/baseline_master.json --output-dir outputs/layered/deidentification_baseline_20261116
conda run --no-capture-output -n pre_analysis python -B -m analysis.deidentify_workbooks --config configs/pipeline_layers.json --output-dir input/deidentified_20261116_ready --private-dir input/private/deidentification_20261116_ready --group-map input/private/deidentification_20261116/retrospective_count_groups.json
python3 run.py --config .maintenance/deidentification_20261116/candidate_master.json --validate-only
python3 run.py --config .maintenance/deidentification_20261116/candidate_master.json --output-dir outputs/layered/deidentification_candidate_20261116
conda run --no-capture-output -n pre_analysis python -B .maintenance/deidentification_20261116/compare.py
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/test_deidentification.py tests/orchestration/test_launcher.py tests/orchestration/test_master_configuration.py
python3 run.py --config input/deidentified_20261116_ready/master.json --validate-only
```

The first two package attempts stopped on unsupported XML fragment handling
before accepting any workbook. Their failed reports and private mapping were
retained in the original fresh destinations. Worksheet revision namespaces,
self-closing formatting-only cells and prefixed worksheet namespaces were then
covered by regression tests. No original was overwritten or repaired. The accepted
bundle reused the first private alias map and was written to a third fresh folder.

## Package and scientific checks

| Check | Result |
| --- | --- |
| Original files | All five SHA-256 values unchanged |
| Formula/cache cells | 8,149 preserved byte-for-byte: inventory 3,155; CIRCALL 4,363; donors 36; CIRCALL counts 95; retrospective counts 500 |
| Privacy cell operations | Inventory DOB 631; CIRCALL DOB 702, first names 739, surnames 739, a2g_id 702; retrospective count first names 250, surname aliases 250, source notes 2. Counts include populated missing markers, not distinct people. |
| Count aliases | 34 distinct trimmed, case-sensitive surname groups; group membership/collisions preserved across both source sheets; no inventory linkage |
| Other cells and styles | Identical logical values and cell positions except approved edits; formula XML/caches exact; styles and unedited package parts preserved |
| Metadata | Properties, comments and comment drawings/relationships removed; unused shared strings eliminated; zero known-name matches in remaining XML |
| Formula dependencies | Independent all-workbook audit found zero references to cleared columns, including ranges/cross-sheet references, and zero INDIRECT/OFFSET references |
| Access | Bundle/private directories 0700; new workbooks and private mapping 0600; originals retain their permissions |
| Full runs | Both complete; all four layers complete with unchanged `review_needed` flags |
| Scientific evidence | All 30 native numerical JSON files and 12 result workbook cell sets identical after explicit original/copy source-path, filename and source-hash substitutions |
| Figures | All 285 checked native PNGs pixel-identical |
| Artifacts | 489 artifact hashes and 150 publication mappings verified in each run |
| Focused tests | 34 passed in 29.27 seconds: four package regressions plus launcher/master checks |
| Accepted profile | `input/deidentified_20261116_ready/master.json` passed integrated preflight |

Numerical evidence includes Layer 3 selected-sample flags and patient/sample
hashes, establishing unchanged seeded choices. Only retrospective count surnames
were aliased; those observations stay in memory under the unchanged Layer 4
aggregate-only export policy. Study IDs and dates were not retokenised or shifted.

Native source/publication/privacy checks reused
`.maintenance/layer34_figures_before_20261103T083811Z/inspect_smoke.py`, with reports
`baseline_validation.json` and `candidate_validation.json` under the new evidence
directory. The existing strict Layer 3 scanner still flags short donor codes that
coincide with public Layer 2 labels. The check projected only the in-memory Layer 2
definition subtree after equality-checking it against the tracked definition;
clinical exports and all other metadata remained scanned. Layer 4 privacy passed
normally. This is the [previously documented limitation](figure_modules_20261103.md),
not a production validator change or a blanket identifier exclusion.

## Provenance and limits

Local evidence in `.maintenance/deidentification_20261116/` includes explicit
masters, logs, comparison script/report, validation reports and `verification.json`.
The copied-data folder contains its package report and a separate `acceptance.json`.
The private group map is outside that folder and excluded from images/Git. No raw
identifier values appear in code, tests, tracked reports or public logs.

Validation ran against the unchanged checkpoint contract before the documentation
amendment was appended. Its executed hash and `90954b1:docs/workflow_contracts.md`
are recorded in `verification.json`; historical runs retain that hash. The final
user-facing profile preflight also passed after documentation was updated. Future
strict replay must use the executed contract/source versions, as for other dated
acceptance runs.

This accepts controlled-access pseudonymised copies, not anonymous public data.
Exact clinical dates, age, approved protocol codes/initials and rare combinations
remain. Name scanning cannot certify absence of unknown or indirect identifiers.
No source workbook was rendered into a preview image, no Excel recalculation was
performed and no PDF export/visual Excel rendering was checked. Package styles and
formulas were verified structurally; pipeline PNG parity was pixel-exact.
Future source/header/formula changes require fresh dependency/privacy review,
including named/range/dynamic references; the maintenance helper is not a general
Excel dependency solver. No clinical-data image was built or published.

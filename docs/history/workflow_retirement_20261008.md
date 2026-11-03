# Older workflow retirement — October 8, 2026

Accepted retirement preserves the dirty pre-change four-layer implementation,
including its latest plotting changes. Fresh successful, blocked and clinical
runs match after removal of all three older scientific packages. This supersedes
earlier plans to migrate their longitudinal models, bootstrap trends, combined
panels or normalized kinetics. Those capabilities are historical and require
separate future scope. Scientific settings, preparation and plotting within the
four layers were not changed by retirement.

## Preservation and implementation

The code/configuration/documentation/test snapshot contains 241 implementation
files, original HEAD `92044beb31b7609a09b473e64603be34da582c2d`, dirty-tree status and a scoped
tracked patch. Its [inventory](../../archive/migrations/workflow_retirement_before_20261008/inventory.json)
verifies original file bytes. It excludes clinical inputs, outputs, credentials,
caches and the unrelated local cache-cleaning utility. Existing user edits are
preserved in that snapshot; nothing was reset, staged or committed.

The [code-only archive](../../archive/retired/older_workflows_20261008/README.md)
retains older packages, five profiles/root aliases, normalized YAML, extraction
configuration, association catalog, scientific tests, validators, original
instructions, shared pre-change dispatcher/publication code, environment lock
and source/code hashes. Its [path/hash inventory](../../archive/retired/older_workflows_20261008/inventory.json)
records moves versus reference copies. This bundle is eligible for Git tracking;
other archives, clinical inputs, results and the rollback snapshot remain ignored.

Active dispatch/publication now supports only the four layers. Version-1 layered
profiles and the version-2 master/selectors remain supported. Retired commands
fail before execution or output creation. Shared association methods, synthetic
numerical references, readers, plots, provenance, integrity and workbook tools
remain. Retrospective-blast migration moved unchanged to
`analysis/migrate_retrospective_blasts.py`; historical workbook packaging has an
independent owner in `analysis/historical_workbooks.py`. Its existing workbook
writer and explicit historical-layout resolution remain available without old
scientific imports. Generic orchestration/publication checks now use layers;
compatibility-only tests and validators are archived. `pytest.ini` prevents
archived tests from entering default discovery.

## Executed verification

Before archival:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests --ignore=tests/blast_kinetics/test_workbook_integration.py
```

Result: **508 tests and 123 subtests passed**. After final edits:

```bash
MPLCONFIGDIR=/tmp/pre_analysis_retirement_mpl conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests
```

Result: **352 tests and 82 subtests passed**. This includes fixed numerical
references, scientific-selection checks, standalone/integrated isolation, old
command rejection, source changes, interruption, publication failure, symlinks,
privacy and independent completion. The original retained pass had 348 tests;
four additional comparator mutation checks detect numerical, setting, workbook
and PNG drift. Final discovery includes all 352 tests.

All three cases ran integrated preflight before execution, for baseline, initial
candidate and final verified state. The saved `profiles/` select explicit source
paths, assessment time `2026-10-08T12:00:00+00:00`, selection seed 123 and jitter
seed 42; synthetic cases also enable PDF output. The source workbooks are shared
between each reference/candidate pair and rehashed during validation. New cases
and outputs live under `outputs/workflow_retirement_20261008/`; existing clinical
inputs and earlier result directories remain in place.

The capture commands used the scoped local helper before archival and its
archived CLI equivalent after review:

```bash
conda run --no-capture-output -n pre_analysis python -B /tmp/capture_retirement.py baseline
MPLCONFIGDIR=/tmp/pre_analysis_retirement_mpl conda run --no-capture-output -n pre_analysis python -B /tmp/capture_retirement.py candidate
MPLCONFIGDIR=/tmp/pre_analysis_retirement_mpl conda run --no-capture-output -n pre_analysis python -B /tmp/capture_retirement.py verified
```

`baseline/capture.json`, `candidate/capture.json` and `verified/capture.json`
retain every actual integrated command, log path and exit code. The maintained
reproduction helper is `archive/retired/older_workflows_20261008/capture_references.py`;
use its `--phase` and `--evidence-root` CLI in a fresh destination as documented
in the archive guide. Baseline restoration uses the exact implementation
snapshot and original source paths, never relocated clinical data.

For each named case, the final comparison command was:

```bash
MPLCONFIGDIR=/tmp/pre_analysis_retirement_mpl conda run --no-capture-output -n pre_analysis python -B -m analysis.validation.validate_retirement \
  --baseline outputs/workflow_retirement_20261008/baseline/<case> \
  --candidate outputs/workflow_retirement_20261008/verified/<case> \
  --snapshot archive/migrations/workflow_retirement_before_20261008/implementation \
  --report outputs/workflow_retirement_20261008/verified_comparisons/<case>.json
```

| Case | Preflight / execution exit | JSON | CSV | Workbook artifacts | PNG artifacts | PDF artifacts |
| --- | --- | --- | --- | --- | --- | --- |
| synthetic_success | 0 / 0 | 36 | 2 | 24 | 87 | 72 |
| synthetic_blocked | 1 / 1 | 36 | 2 | 24 | 69 | 54 |
| clinical_current | 1 / 1 | 36 | 2 | 24 | 389 | 0 |

Every comparison passed. Counts include native/audit and published copies, not
unique figures. Sources, definitions and resolved scientific settings match;
populations and all numerical evidence match exactly. Workbook cells, types,
formats, freeze panes, filters and merged ranges match. PNG pixels match exactly;
PDF bytes match after creation-date normalization. Artifact indices and every
publication/source checksum verify, and visible destinations match.

The successful case exits 0. Synthetic and clinical CIRCALL holds exit 1 on
preflight and execution. Full execution completes all four report workflows,
retains blocked CIRCALL reports and completes independent retrospective disease
analysis. No gate was weakened. Layer 3/4 aggregate exports and execution logs
passed source-identifier privacy checks; Layer 4 exported no CSV rows. Layer 1/2
identifier and export policies remain covered by retained tests and exact output
comparison. A baseline clinical association figure was also visually inspected;
its labels, axes and legend retain the requested presentation.

Allowed differences are execution timestamps/commands, run IDs/output-root
strings, code/contract provenance hashes and Excel container/core timestamps.
Both generations' original code and input hashes are independently checked
against the correct implementation; statistical values and settings are never
rounded or normalized away. The shared environment YAML and Linux lock are
unchanged, with actual package versions recorded in every run.

## Limits and rollback

Excel visual rendering and independent PDF rasterization are unavailable. The
checks establish workbook content/format equality, exact PNG rendering equality
and PDF content equality, rather than a separate Excel/PDF visual review. These
software and output comparisons do not establish biological validity or resolve
the existing CIRCALL annotation hold.

The [small acceptance summary](workflow_retirement_20261008.json) contains counts,
statuses and provenance pointers without clinical rows. Detailed capture logs,
comparisons, source hashes and native results remain in the named evidence root.
Restore only reviewed affected implementation files from the pre-change snapshot,
verify its hashes and account for later edits. Do not reset/clean the working tree,
replace clinical inputs/results, remove failed evidence or automatically restore
historical execution. The [retirement map](../replacement_coverage.md) owns the
current boundary; earlier dated plans retain their historical decisions.

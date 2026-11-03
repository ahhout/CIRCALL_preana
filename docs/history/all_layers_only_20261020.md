# All-layer execution and audit fixes — October 20, 2026

The investigator approved all eight audit repairs and retirement of public
single-layer execution. Scientific settings, identities and calculations are unchanged.
All public execution now attempts Layers 1–4 in order; quality gates and independent
completion remain. Historical result directories are neither moved nor rewritten.

## Preservation

Before edits, 149 implementation/configuration/documentation/test files were copied
to `archive/migrations/all_layers_only_before_20261020/implementation/`.
Its inventory records SHA-256 hashes and HEAD
`92044beb31b7609a09b473e64603be34da582c2d`; status, scoped tracked patch and rollback
instructions are adjacent. The snapshot excludes clinical inputs, outputs, caches
and credentials. Existing uncommitted work was preserved.

The [code-only retirement bundle](../../archive/retired/single_layer_interfaces_20261020/README.md)
contains original selector profiles and the unused generic artifact helper with
path/hash inventory. Original wrappers are preserved in the scoped snapshot.
No commits or staging were performed.

## Verification

Successful and deliberately blocked synthetic baselines were captured before edits
under `outputs/all_layers_only_20261020/runs/baseline/`, using saved explicit source
profiles, assessment time `2026-10-20T12:00:00+00:00`, sample-selection seed 123 and
jitter seed 42. PDFs and PNGs were enabled. Both cases ran explicit integrated
preflight before execution. Success exited 0; the blocked case exited 1 and retained
independent complete reports. `capture.json` records exact commands and logs.

The [aggregate acceptance record](all_layers_only_20261020.json) contains counts,
preflight outcome, comparison paths, visual-review scope and limitations. Initial
candidate runs and final verified runs used the same saved source profiles:

```bash
conda run --no-capture-output -n pre_analysis python -B outputs/all_layers_only_20261020/capture.py --phase baseline --evidence-root outputs/all_layers_only_20261020/runs
conda run --no-capture-output -n pre_analysis python -B outputs/all_layers_only_20261020/capture.py --phase candidate --evidence-root outputs/all_layers_only_20261020/runs
conda run --no-capture-output -n pre_analysis python -B outputs/all_layers_only_20261020/capture.py --phase verified --evidence-root outputs/all_layers_only_20261020/runs
```

These are recorded executed commands; reproduction requires fresh evidence/report
destinations because existing evidence is never replaced. The synthetic-only helper
was adapted from the retained retirement capture script; it never selects clinical
execution cases. Each phase's `capture.json` records actual underlying pipeline
commands, log paths and exit codes.

The complete portable suite ran after the implementation:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests --tb=short
```

Result: **402 tests and 98 subtests passed**, with **zero warnings**, in 443.60 seconds.
After removing remaining unreachable branches/obsolete imports and strengthening
index ownership verification, final affected orchestration checks ran:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/orchestration --ignore=tests/orchestration/test_layer_dependencies.py --tb=short
```

Result: **113 tests and 23 subtests passed**, with **zero warnings**, in 37.93 seconds.
The earlier full suite includes isolated execution through both public launchers
with older packages physically absent, successful/blocked cases, privacy, source
changes, interruption, fresh destinations and publication failures. Final targeted
checks include both comparators' extra/missing figures, selected historical scopes,
unindexed/relabelled artifacts, Layer 2 review quality, unit glyphs, full schema-1
ordering, schema-2 compatibility and rejected public partial interfaces.

For each of `synthetic_success` and `synthetic_blocked` the final comparator ran:

```bash
conda run --no-capture-output -n pre_analysis python -B outputs/all_layers_only_20261020/compare.py   --baseline outputs/all_layers_only_20261020/runs/baseline/<case>   --candidate outputs/all_layers_only_20261020/runs/verified/<case>   --snapshot archive/migrations/all_layers_only_before_20261020/implementation   --report outputs/all_layers_only_20261020/comparisons/verified_<case>.json
```

| Case | Preflight / execution | JSON | CSV | XLSX | PNG | PDF | Permitted typography changes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic_success | 0 / 0 | 36 | 2 | 24 | 87 | 72 | 44 PNG/PDF artifacts |
| synthetic_blocked | 1 / 1 | 36 | 2 | 24 | 69 | 54 | 20 PNG/PDF artifacts |

Both comparisons **passed with no unexpected differences**. Code/contract/source/
environment/artifact/publication hashes were independently checked against the
appropriate pre-change snapshot or final implementation. Numerical JSON/CSV,
workbook cells/styles and artifact populations matched. Only execution/code/contract
provenance, Layer 2 review-quality/cohort review-count fields and affected WBC/
platelet/count-unit typography were permitted to differ. Unaffected PNG pixels and
PDF content (excluding creation timestamps) matched.

Representative Layer 3 CIRCALL WBC-association and Layer 4 CIRCALL blast-count PNGs
were visually inspected: the exponent is readable, labels are complete and legends
remain clear of axes. Those reviewed candidate PNGs match the final verified PNGs
byte-for-byte. This is not full figure, workbook or PDF visual QA.

The configured current-source preflight also ran:

```bash
conda run --no-capture-output -n pre_analysis python -B run.py --validate-only --output-dir outputs/all_layers_only_20261020/configured_preflight_destination
```

It returned **0**, reporting all four preflights complete, and created **no output
directory**. The command, exit status and log are preserved in
`outputs/all_layers_only_20261020/configured_preflight.json` and its adjacent log.
This was preflight only, not clinical pipeline execution.

Master sources/defaults/scientific options match the snapshot exactly after
removing the execution switches. Environment YAML/lock bytes are unchanged.
All 149 snapshot files and 126 archive inventory entries matched their hashes.
All active Python files parsed and `git diff --check` passed. Documentation link
checks found only the two previously acknowledged absent historical acceptance JSON
records; stale active links/anchors were repaired. No files were staged or committed.

## Rollback and limits

Restore only reviewed affected files from the snapshot after verifying its inventory
and preserving later unrelated edits. Never reset/clean the dirty tree, overwrite
clinical workbooks/results or remove retained evidence. Re-run integrated preflight
before any restored execution.

No clinical full execution, dependency/environment change, source repair or scientific
redesign is authorized by this interface change. Software/synthetic equivalence does
not establish clinical scientific validity. Missing historical acceptance JSON
records remain acknowledged in the history index.

# Figure module extraction — November 3, 2026

This maintenance change separates figure families from workbook reporting in
Layers 2–4. The full four-layer launcher, selected sources, scientific definitions,
preparation, statistical methods, random seeds, output names and clinical gates
are unchanged. Layer 4 still exports aggregate evidence only.

## Implementation

- Layer 2: distribution, receipt-status and calendar-volume renderers, an export
  coordinator and shared workbook/figure labels.
- Layer 3: continuous and categorical drawing helpers with common figure layout;
  the existing workbook/export coordinator and compatibility imports remain.
- Layer 4: MRD, MRD-status, count, save and export modules. Recursive code discovery
  includes the nested renderers in workflow audit hashes; an execution regression
  test verifies all six package files.

The modules are internal. Routine execution remains documented in
[README](../../README.md#run); these modules add no public per-figure commands.

## Verification

All commands used the existing `pre_analysis` Conda environment.

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/sample_statistics tests/advanced_analysis tests/disease_modeling tests/orchestration
python3 run.py --validate-only --output-dir outputs/layered/figure_modules_smoke_20261103T084234Z
python3 run.py --output-dir outputs/layered/figure_modules_smoke_20261103T084234Z
```

The combined suite passed: **379 tests and 93 subtests**, in 437.46 seconds.
Preflight and the full current-profile smoke execution both returned exit 0.
All four workflows completed with `quality_status: review_needed`; those review
findings remain for scientific interpretation and were not changed by this refactor.
The run retains 489 indexed artifacts and 150 published files. Completion and
subsequent inspection verified current code hashes, all 15 nested figure modules,
source reconciliation and publication checksums. The smoke audit records the dirty
working tree before these reviewed source changes were committed.

Additional read-only smoke inspection used:

```bash
conda run --no-capture-output -n pre_analysis python -B .maintenance/layer34_figures_before_20261103T083811Z/inspect_smoke.py --run-dir outputs/layered/figure_modules_smoke_20261103T084234Z --report .maintenance/layer34_figures_before_20261103T083811Z/smoke_validation.json
```

The strict Layer 3 privacy comparator returned a false positive: four occurrences
of public timepoint labels inside the root manifest's shared Layer 2 definitions
coincide with short control identifiers. Diagnostic inspection found matches only
in that public configuration subtree, not in native association reports. A local
inspection helper required the entire subtree to equal the parsed checked-in
Layer 2 definition before excluding it from identifier matching in memory. With
that narrowly scoped projection, all remaining Layer 3 exports and pipeline
metadata passed identifier checks. The strict Layer 4 privacy check passed without
an exception; its source reconstruction and observation-field restrictions also
passed. No production validator, clinical gate or on-disk run evidence was
changed. The strict Layer 3 comparator limitation remains unresolved in production.

The local smoke execution/preflight logs and inspection result are retained beside
the second snapshot below; per-layer execution logs remain under the run's
`.audit/logs/`. These run/evidence paths are local-only and absent from a clone.

Before/after synthetic comparisons found 34 identical Layer 2 PNGs and 15
identical Layer 3/4 PNGs. The corresponding 49 PDFs match after excluding metadata
timestamps; seven workbook packages match after excluding document timestamps.
Rendering did not mutate source observations. Function syntax-tree checks preserve
workbook, export and lifted drawing logic; scientific definitions are byte-identical.
Representative synthetic association, MRD, distribution and calendar PNGs were
visually inspected. These checks establish software behaviour, not scientific
validity. No independent Excel or PDF page rendering was performed.

## Rollback and local evidence

The original tracked checkpoint is `c2fcc4e`. The dirty pre-change states,
including pending `.gitignore` changes and the completed Layer 2 extraction, are
preserved in code-only snapshots:

- `.maintenance/layer2_figures_before_20261103T083113Z/`
- `.maintenance/layer34_figures_before_20261103T083811Z/`

Each contains an `implementation/` tree and SHA-256 snapshot inventory. Synthetic
parity helpers, exact commands and results are retained beside the snapshots;
these local-only paths are Git-ignored and absent from a code-only clone. The
first partial Layer 3/4 baseline render is retained after a synthetic-fixture
setup error; the successful comparison explicitly selects `baseline_v2`.
The companion `.gitignore` update retains clinical data, outputs, credentials,
local evidence and caches outside Git, including inside archive source allowlists.
Twenty-one root/archive path checks passed and no tracked source was newly hidden.
Existing clinical inputs and historical results were not moved or replaced.

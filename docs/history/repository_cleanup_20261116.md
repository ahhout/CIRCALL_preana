# Repository interface cleanup — November 16, 2026

Completed migration tools were moved out of active code, reusable workbook tools
were grouped under `analysis/maintenance/`, and the README was shortened from
180 to 117 lines. The public `python3 run.py` launcher and scientific behavior
remain unchanged. Inputs, results, private images and existing evidence were not
relocated or deleted.

## Layout and preservation

The clean checkpoint was `e90445e58884e021951c521b264c0e90d120faa0`, recorded in
`.maintenance/repository_cleanup_20261116/prechange.json`. The
[archive inventory](../../archive/retired/completed_migrations_20261116/inventory.json)
maps 19 original paths and hashes to their destinations: 13 code/config/test files
in the completed-migrations archive and six files in reusable maintenance.
The archive retains its configurations and tests. No compatibility wrappers or
archive imports were added to active execution.

The shared CELL/ROW/cell_xml primitives were extracted unchanged into
`analysis/maintenance/xlsx_patch.py`; their ASTs match the original implementation.
All 63 remaining active analysis files are byte-identical. The engines, scientific
definitions, default data master, environment files, build recipe and launcher
were also checked unchanged. Imports and maintenance configuration/provenance paths
were rebased where needed; no clinical transformation was redesigned.

Top-level analysis modules decreased from 25 to 15. The
[README](../../README.md) owns normal setup/run commands; optional details are in
[container](../container.md) and [maintenance](../maintenance.md). The
[archive index](../../archive/README.md) owns retired-tool navigation. Dated
command strings and prior acceptance records remain historical.

## Verification

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests archive/retired/completed_migrations_20261116/tests
python3 run.py --validate-only
python3 run.py --config .maintenance/repository_cleanup_20261116/candidate_master.json --validate-only
python3 run.py --config .maintenance/repository_cleanup_20261116/candidate_master.json --output-dir outputs/layered/repository_cleanup_20261116
conda run --no-capture-output -n pre_analysis python -B .maintenance/repository_cleanup_20261116/compare.py
```

439 tests and 98 subtests passed in 475.80 seconds, including the preserved
archived-tool tests. The initial focused maintenance/archive checks passed 33
tests, and all ten current/archived CLI help commands resolved successfully.

Default and candidate preflight passed. The candidate completed all four layers
with the same `review_needed` flags as the explicitly selected baseline,
`outputs/layered/pseudonymised_default_20261116`. Its actual assessment timestamp
was pinned in the candidate master; actual resolved scientific settings and input
records match in every layer. All 30 native numerical JSON files, 12 workbook
cell sets and 285 checked PNGs match exactly, without value/path substitutions
or numerical tolerances. Artifact/publication hashes and source/privacy checks
passed for both runs.

Baseline code/contract bytes were materialised from the checkpoint and verified
against its recorded hashes before read-only validation. Candidate validation
used the current files. The existing short-donor-code/public-Layer-2-label false
positive remains: only the equality-verified public definition subtree was
projected in memory. Clinical exports stayed scanned; no production validator
was relaxed. This is the [previously recorded limitation](figure_modules_20261103.md).

Local aggregate evidence, the fixed candidate master, baseline code snapshot,
logs and `verification.json` are in `.maintenance/repository_cleanup_20261116/`.
No clinical data or private mappings entered the code archive. Existing private
SIF images remain immutable artifacts of their recorded code checkpoints; this
cleanup did not rebuild them. PDF export and visual Excel rendering were not
performed; the PNG comparison was pixel-exact. Scientific validity and the
outstanding data-sharing privacy review are unchanged.

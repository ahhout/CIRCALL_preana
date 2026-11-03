# Older workflows archived October 8, 2026

Historical implementation only. Active execution supports the four layers.
The acceptance boundary is the dirty October 8 layered implementation, including
its latest plotting changes, not the scientific populations of older workflows.
Longitudinal mixed models, bootstrap trajectories, combined yield/WBC panels,
older-only protocol/comparison exports and normalized kinetics are historical;
any future addition needs a separate scope.

`inventory.json` maps original paths to archived paths with SHA-256 hashes.
The original environment YAML/lock, master/definitions and source/code hash
record (`reference_provenance.json`) are included.
`reference_copy` marks original shared files preserved before their active
compatibility branches were removed. Entire retired scientific packages, profiles,
tests, validators and instructions retain their original bytes and import paths.
The retrospective blast migration and CSV-to-workbook packaging tools also have
maintained independent owners: `analysis/migrate_retrospective_blasts.py` and
`analysis/historical_workbooks.py`. Archived copies preserve their original form.

## Preserved state and evidence

- Dirty implementation snapshot: `archive/migrations/workflow_retirement_before_20261008/implementation/`.
- Snapshot inventory, original HEAD, status and scoped tracked patch: its parent directory.
- Fresh references, fixed profiles, clinical source hashes, execution/environment provenance,
  logs, candidate/final verified runs and equivalence reports: `outputs/workflow_retirement_20261008/`.
- Acceptance summary and exact verification commands: `docs/history/workflow_retirement_20261008.md`.

Clinical inputs, pre-existing results and earlier archives remain at their original
locations. This bundle contains implementation and synthetic-reference code only.
The complete dirty snapshot and run evidence remain local and Git-ignored; this
code-only bundle is eligible for version control. No files are staged automatically.

## Reproduction

Use the existing `pre_analysis` Conda environment and its retained environment
YAML/Linux lock. Do not execute the relocated modules directly: their original
imports and relative paths belong to the pre-retirement implementation. Inspect
hash inventories first, then restore the snapshot into a fresh isolated directory
such as `/tmp/pre_analysis_retirement_reference` using `cp -a <snapshot>/implementation/. <fresh-directory>/`.
This copies only implementation files, never clinical workbooks or prior results.
The snapshot does not include input data; use the explicitly selected absolute
source paths from the saved `profiles/*.json` for clinical reproduction.

From that restored repository, run `conda run --no-capture-output -n pre_analysis python -B run.py
--config <original-repository>/outputs/workflow_retirement_20261008/profiles/<case>.json
--output-dir <fresh-output> --validate-only`, followed by the same command without
`--validate-only`. Cases are `synthetic_success`, `synthetic_blocked` and
`clinical_current`. Success exits 0; both blocked cases exit 1 while retaining
independent results on execution. Never reinterpret exit 1 as a complete clean run.
The profile records assessment time `2026-10-08T12:00:00+00:00`, sample selection
seed 123 and jitter seed 42. Synthetic cases enable PDFs as well as PNGs.

`capture_references.py --phase baseline --evidence-root <fresh-directory>` recreates
synthetic inputs and frozen profiles when run with the restored implementation.
Use `--phase candidate` (or a fresh `--phase verified` final pass) against the same evidence directory from the retained
repository after reviewing absolute source/definition paths. It invokes integrated
preflight before every execution and records all commands, logs and exit codes.
For exact input-byte reproduction, keep the original saved synthetic workbooks;
regenerating Excel containers can change source hashes despite equal cells.

Compare each explicitly selected reference/candidate pair using the maintained
`analysis.validation.validate_retirement` command documented in the acceptance
record. The comparison checks source/configuration/environment hashes, code against
the appropriate implementation, resolved settings, populations, numerical evidence,
workbook cells/styles, PNG pixels, PDF content, privacy and publication hashes.
Execution timestamps, output-root strings and code/contract provenance hashes may
differ; no scientific settings or numerical values are normalized away.

## Rollback

Review the snapshot's inventory and current changes. Restore only the agreed
affected implementation files from the snapshot, checking their hashes and
accounting for subsequent edits. Do not reset/clean the dirty tree, overwrite
clinical workbooks/results, or remove this bundle or acceptance evidence. Preserve
new unrelated work. Re-run integrated preflight before any restored execution.

# Migration record

## Preserved sources

The migration created an independent `pre_analysis` repository from local `cfDNA_inventory` HEAD `a522f2a`. The source working tree contained both staged and unstaged changes; `bilan` was an unversioned directory containing four Python scripts.

| Commit | Purpose |
| --- | --- |
| `984c99b` | Snapshot the current cfDNA working files, including existing deletions |
| `4503ece` | Import the four current bilan scripts |
| `4be443b` | Move both workflows into their directories and rename the repository instructions, without implementation edits |

The original cfDNA commits and the `clean/history-cfdna` and `backup/pre-history-cleanup-cfdna` branches remain available. `master` continues with the integration. The new repository has independent Git objects and no configured remote. Both original project directories remain intact.

Local audit records are Git-ignored under `data/archive/migration/`:

- `source_manifest.json`: original HEAD, branches, Git status, and SHA-256 checksums of source files.
- `staged.patch` and `unstaged.patch`: binary-capable backups of the original diffs.
- `copy_manifest.json`: source-to-destination mapping and hashes for 54 copied data/output files.
- `verification.json`: checks that original files, staged and unstaged diffs, copied files, branches, and the environment lock were preserved.
- `baseline_status.json`: exit statuses from the isolated baseline runs.

The baseline scripts and inputs were copied to a temporary directory before integration edits. Their output artifacts and logs were subsequently retained under `outputs/validation/baseline/`. The retrospective baseline log's name-bearing diagnostic lines were suppressed; the new code prints only the corresponding count.

## Integration changes

`run.py` connects the existing scripts and preserves their workbook interface. Repository-relative defaults replace the old sibling-project and script-directory assumptions. The retrospective output-root option now covers all default artifacts. Fresh run directories, input/header validation, required-artifact checks, stage logs, and manifests make failures and provenance explicit.

Scientific calculations and selections remain unchanged. Two small reporting changes accompany the integration: patient names are no longer printed in the volume diagnostic, and the consolidated report can select the requested outlier-sensitivity count instead of always reading the drop-2 file. Sensitivity calculations remain opt-in.

## Validation performed

All six original baseline invocations completed successfully. The combined runner completed all seven stages from `/tmp`, using repository-relative default inputs and an explicit output directory.

| Comparison against baseline | Result |
| --- | --- |
| Retrospective table files | 5 matched, including 11 sheets across two workbooks |
| Bilan table files | 5 matched |
| Retrospective images | 18 pixel-identical |
| Bilan images | 11 pixel-identical |
| Missing or extra artifacts | None |

Table comparison preserves row/column/sheet order and checks categorical values and numerical values (`rtol=1e-9`, `atol=1e-12`). Representative missing-sample and subtype-violin plots were also visually inspected; titles, axes, legends, and table labels were readable.

Fourteen synthetic tests passed, covering CLI availability from another working directory, default/explicit path resolution, workbook headers and invalid inputs, output reuse refusal, workbook handoff, sensitivity-count forwarding, nonzero exits, missing artifacts despite a zero exit, and stopping after a failed stage. The individual retrospective driver and report commands also completed successfully from `/tmp` with a custom output root.

All 79 original non-Git files matched their initial checksums, including source caches already present before the migration. The source Git status and both diff backups matched exactly. All 54 copied files matched their source hashes. Clinical inputs and generated artifacts remain untracked, and the original Linux environment lock is unchanged.

Evidence is retained locally in `outputs/validation/`: `tests.log`, `final_comparison.json`, `legacy_comparison.json`, `warning_summary.json`, and the final run's `run_manifest.json` and logs. Runtime code hashes in that manifest identify the validated implementation even though validation preceded its commit.

## Existing limitations and rollback

The baseline and merged default runs both emitted two model-convergence warnings and one singular-covariance warning; neither emitted a failed-analysis warning. These are existing model diagnostics, not migration regressions. Font-cache warnings occurred in the restricted execution environment; image comparisons still matched exactly. Optional sensitivity models and optional Parquet export were not exercised end-to-end during this migration.

The new repository intentionally retains two parsers and their existing scientific assumptions. A unified sample model or changes to biological thresholds require a separate change.

For immediate rollback, use the untouched original `cfDNA_inventory` and `bilan` directories and their original environment. The snapshot, import, organisation, and integration commits separate the migration for review or reversal. Local data and old results are preserved independently of those commits. No source deletion, history rewrite, force-push, or remote publication was performed.

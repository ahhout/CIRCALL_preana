# Workflow retirement map

Accepted October 8, 2026. Retirement preserves the four layers as executed in the
fresh dirty-state baseline, including the latest plotting changes. It does not
require reproducing older populations or migrating older-only capabilities.
[Acceptance evidence](history/workflow_retirement_20261008.md) records successful,
blocked and current clinical comparisons. The [scientific contract](workflow_contracts.md#older-workflow-retirement--october-8-2026)
supersedes earlier compatibility-retention and migration plans.

## Active execution and dependencies

| Owner | Retained responsibility |
| --- | --- |
| `run.py`, `cli.py`, `pipeline.py`, `worker.py` | All four data_integrity, sample_statistics, advanced_analysis and disease_modeling in order; integrated preflight, independent completion, quality exits and CIRCALL hold |
| `configs/pipeline_layers.json` and full-run October 7 reference | Current complete master; schema-1/schema-2 configurations must include all four layers |
| `outputs.py`, `provenance.py` | Reviewed layer publication, shared artifact integrity, source/code/environment hashes and ISO execution timestamps |
| `sample_io.py`, `source_state.py`, `retrospective_controls.py`, `data_integrity/` | Shared reading, source-state verification, controls and cohort gates |
| `association_methods.py`, `advanced_analysis/` | Shared approved fits/diagnostics and Layer 3 preparation/reporting; frozen synthetic numerical references remain active |
| `sample_statistics/`, `disease_modeling/` | Layer 2 statistics and Layer 4 descriptive tracking; identities, populations, correction rules and privacy remain unchanged |
| Shared plotting and scientific definitions | Current presentation, seeds and approved settings; no migration or new scientific default |
| `analysis/validation/` | Current Layer 3/4 validation; completed retirement equivalence is archived |
| `analysis/maintenance/`, `configs/maintenance/` | Reusable explicit workbook preparation/deidentification; never automatic repair |
| Completed migrations and historical report packaging | [Archived with tests/configuration](../archive/retired/completed_migrations_20261116/README.md); no runtime imports |
| Shared Conda YAML/Linux lock | Unchanged pre_analysis environment; no dependency removal or lock regeneration |

## Historical functionality and paths

The [bundle inventory](../archive/retired/older_workflows_20261008/inventory.json)
maps each original path to its preserved archived SHA-256. The
[bundle guide](../archive/retired/older_workflows_20261008/README.md) explains reproduction
and reviewed rollback. Archived modules are historical references, not current
entrypoints. New future capabilities require a separate scope and scientific review.

| Original capability or path | Disposition |
| --- | --- |
| `analysis/sample_analysis/` | Archived: older preparation, longitudinal mixed models and sensitivities, pooled inference, bootstrap trajectories, handling scope, combined yield/WBC panels, protocol and derived-comparison exports |
| `analysis/cfdna_associations/` | Archived: older diagnosis preparation and execution; shared association methods remain active |
| `analysis/blast_kinetics/` | Archived: normalized/generic configured measurement modeling and original privacy instructions; no migration into Layer 4 |
| Five `configs/compatibility/pipeline_*.json` profiles and their root aliases | Archived: all, longitudinal, kinetics, MRD and cfDNA Spearman; old paths fail explicitly |
| `configs/blast_kinetics/`, `configs/sample_analysis/`, `configs/source_catalog.json` | Archived with the code that used them; active layer definitions and maintenance configuration remain |
| Older scientific test suites, compatibility assertions and validators | Archived together; generic orchestration/publication checks now exercise retained layers; frozen numerical references remain active |
| `docs/compatibility/` and older package instructions | Archived together; dated earlier plans/acceptance records remain historical |
| Method-origin metadata naming older paths | Preserved historical provenance, not runtime imports or a claim that current archived bytes match an earlier source revision |
| Clinical inputs, existing results, earlier archives and rollback snapshots | Remain in place; no data relocation, deletion or implicit source substitution |
| Root `codex-clean-cache` | Unrelated local utility; unchanged and not invoked |

## Acceptance and rollback

The dirty pre-change implementation, environment lock, source selection and hashes
were frozen before archival. Both generations executed all four layers with fixed
assessment time and seeds. The October 8 suite exercised standalone and integrated runs with old packages
physically absent; current acceptance exercises both full-pipeline launchers. Equivalence covers settings,
populations, numerical tables, workbook cells/styles, PNG pixels and PDF content,
privacy, artifact publication, locations, independent completion and exit codes.
The CIRCALL hold remains intentional; blocked reports are never labeled clean.

Restore only reviewed affected files from
`archive/migrations/workflow_retirement_before_20261008/implementation/`, checking
its inventory and preserving subsequent unrelated changes. The snapshot excludes
clinical data, outputs, credentials and caches. Do not reset/clean the dirty tree
or overwrite inputs/results. Environment changes and new scientific behavior are
outside this retirement's scope.

## Single-layer interface retirement — October 20, 2026

All new public execution runs all four layers. The four single-layer selector
profiles and unused generic artifact helper are preserved in the
[code-only interface archive](../archive/retired/single_layer_interfaces_20261020/README.md).
Standalone wrappers and original tests remain in the scoped pre-change snapshot.
Internal engines, full-run configuration references and historical output readers
remain active. [Acceptance and rollback](history/all_layers_only_20261020.md).

## Conda launcher consolidation — October 20, 2026

The sole public launcher is `python3 run.py`. It enters the existing `pre_analysis`
environment automatically and preserves caller-relative CLI paths, argument boundaries,
exit codes and terminal signals. The shell wrapper is [archived](../archive/retired/conda_launcher_20261020/README.md).
[Verification and rollback](history/conda_launcher_20261020.md).

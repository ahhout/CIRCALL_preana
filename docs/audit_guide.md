# Auditing and validating runs

This guide owns validation, completion status, publication and provenance.
Use [README](../README.md#run) for routine commands, selected profiles,
path resolution and default destinations. Scientific decisions remain in the
[contracts](workflow_contracts.md); workflow guides explain individual reports.

## Preflight and completion

Integrated execution preflights every selected workflow before reserving an output
directory. Invalid configuration, unavailable workers or invalid preflight metadata
abort execution. `--validate-only` performs that preflight without publishing.
Its scientific depth depends on the workflow:

| Entry point | What preflight establishes |
| --- | --- |
| Layer 1 | Runnable rules/configuration and source availability/state; workbook defects become findings during execution |
| Layer 2 | Rules/definitions and source state; whole-cohort integrity and statistics run during execution |
| Layer 3 | Configuration, source state and a preparation preview, without fitting; preview problems do not certify or replace execution-time cohort gates |
| Layer 4 | Source structure, inventory gates and selected clinical annotations; known blocked cohorts make validate-only return nonzero |

A successful Layers 1–3 preflight does not mean the clinical data are clean.
Full layered execution continues independent work after quality holds or workflow
failures. It preserves [CIRCALL clinical annotation gates](layers/disease_modeling.md#current-circall-source-review)
and does not replace unsupported annotations. Reviewed positive NQ sensitivity
annotations are accepted under the October 8 contract amendment. Interruptions stop remaining work;
input/configuration changes invalidate affected work. There is no resume support.
The [orchestration contract](workflow_contracts.md#unified-layered-orchestration--october-6-2026)
records the approved policy.

Report completion and data quality are separate. A layer can have `status: complete`
with `quality_status: errors_found`: its completed reports may describe a blocked
cohort. Any selected failure or quality hold makes the integrated root `status:
failed` and returns exit 1. Review findings alone do not impose that quality exit;
unavailable analyses in otherwise valid sources remain recorded limitations.
Historical standalone layer manifests retain their original completion/quality fields.
New execution always attempts all four layers through the public pipeline.

Inspect `<run>/.audit/run_manifest.json`, each workflow's native manifest and
`<run>/.audit/logs/<workflow>.log`. Do not infer validated results merely from an
existing file or select an older successful run by guessing the newest directory.

The selected master and every profile reference are hashed as configuration
inputs. The resolved engine options are saved in `.audit/resolved_config.json`.
Changing a referenced master invalidates preflight or completion just as changing
the selected profile does. See [configuration](configuration.md).

## Locations and ownership

The visible layout is documented once in [the results guide](results.md).
New runs always retain four numbered workflow directories. Historical single-layer
layouts remain readable without relocating their files. Audit evidence always stays under the run root:

```text
.audit/
├── run_manifest.json
├── resolved_config.json
├── artifact_index.json
├── logs/
└── workflows/<workflow-directory>/
```

Root metadata records `output_layout_version: 2`. Combined layered runs also have
one `run_id`, `pipeline_kind: layered` and an explicit `failure_policy`, with
per-layer states. Code hashes include `run.py` and Python files under `analysis/`;
the sole launcher selects Conda automatically and is included in every new code hash set. Resolved settings,
source/configuration hashes, environment-lock hash, actual package versions and
ISO execution `started_utc`/`finished_utc` timestamps identify the execution.

`publications` maps every visible file to its native audit source and SHA-256.
Both copies must match. The artifact index includes audit evidence and excludes
disposable caches, temporary publication files and the index itself. Ownership
records also retain cache paths/directories for replacement checks.

The publisher validates native results, stages reviewed copies, then exposes the
numbered workflow folder. Historical flat results remain readable.
A copy/publication failure fails the workflow and retains audit evidence. New
artifact names remain audit-only until included in `analysis/outputs.py`.
Native engine completion alone does not establish successful publication.

Native numerical evidence, diagnostics and workbook source references remain
under the audit workflow root.
The layer guides own their export details: [integrity](layers/data_integrity.md),
[statistics](layers/sample_statistics.md), [associations](layers/advanced_analysis.md) and
[disease tracking](layers/disease_modeling.md#results-and-validation). In particular,
Layer 4 has no patient-level MRD/count exports, even under `.audit`.
Hidden directories are an organizational convention, not access control.

## Existing outputs and replacement

Public pipeline runs require nonexistent destinations.
Existing run evidence is never replaced by layered execution; choose a fresh destination.

The [archival audit](history/archival_audit.md#completed-archival-on-october-7) owns the
historical result inventory and relocation record. Pass its mapped archive paths
explicitly to validators; immutable manifests and historical commands retain their
execution-time paths. There is no automatic alias. Use fresh destinations outside
archives for new validation reports, and preserve failed-workflow evidence.

## Validation commands

Run checks appropriate to the change in the existing `pre_analysis` environment.
The portable suite includes pytest functions and unittest classes; using pytest
ensures both are collected:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests
```

For a targeted check, replace `tests` with the affected workflow's test directory
and `tests/orchestration`. Older workflow tests are archived and excluded from
discovery. Do not treat a portable test pass as verification of a new source
workbook or scientific validity.

Method references and isolated execution without older scientific packages:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/advanced_analysis/test_methods_reference.py tests/orchestration/test_layer_dependencies.py
```

The isolation test excludes packages from a temporary copy, without moving real
code or data. The [coverage map](replacement_coverage.md#active-execution-and-dependencies)
owns the accepted dependency and retirement boundaries.

Compare explicitly named runs for Layer 3, including historical single-layer layouts:

```bash
conda run -n pre_analysis python -m analysis.validation.validate_advanced_analysis \
  --baseline outputs/layered/<baseline-run> \
  --candidate outputs/layered/<candidate-run> \
  --report outputs/<fresh-validation>.json
```

The same `--baseline`/`--candidate` interface is available for
`analysis.validation.validate_disease_modeling`. Existing `--standalone`/`--master`
argument aliases remain read-only compatibility names. Comparators require matching
scope/completion sets, matching PNG/PDF file sets and complete artifact indexes;
PNG pixels are compared, while PDFs receive structural checks only.
This checks native numerical evidence, workbooks, PNG pixels, publication/index/
code/source hashes and export privacy against source identifiers held only in
memory. Completion also reconciles selected source samples and recalculates statistical
results, checks literal workbook strings and PNG/PDF structure, and rechecks sources.
It does not establish equivalence to older clinical preparation. Structural Excel/
PDF checks do not substitute for visual rendering; record which checks actually ran.

Rebuild explicitly selected historical CSV reports without rerunning statistics:

```bash
conda run -n pre_analysis python -m analysis.historical_workbooks --run-dir output/<historical-run> --output-dir output/<fresh-workbooks>
```

The maintained retrospective blast workbook helper is
`python -m analysis.migrate_retrospective_blasts --help`; it retains its explicit
source/output/report interface and refuses existing outputs. Maintenance is never
an automatic preflight repair. Older scientific validators and commands are in the
[code-only archive](../archive/retired/older_workflows_20261008/README.md), with the
implementation snapshot needed to reproduce their original imports.

Retirement equivalence compares explicitly named fresh runs against the dirty
pre-retirement snapshot, including the latest plotting changes:

```bash
conda run -n pre_analysis python -B -m analysis.validation.validate_retirement \
  --baseline outputs/workflow_retirement_20261008/baseline/<case> \
  --candidate outputs/workflow_retirement_20261008/verified/<case> \
  --snapshot archive/migrations/workflow_retirement_before_20261008/implementation \
  --report outputs/<fresh-comparison>.json
```

Cases are `synthetic_success`, `synthetic_blocked` and `clinical_current`.
The validator checks settings, populations, exact numerical evidence, workbook
cells/styles, PNG pixels, PDF content, source/environment/code hashes, privacy,
completion and publication. It permits only documented execution/provenance changes.
Workbook visual rendering and independent PDF rasterization are unavailable;
PNG comparison is pixel-exact. The [acceptance record](history/workflow_retirement_20261008.md)
records the commands, holds, counts and limitations actually verified.

## Layered acceptance evidence

These are dated implementation checks, not claims about the current workbook or
this documentation edit. The linked records retain exact commands and rollback
checkpoints. The earlier orchestration records below did not rerun full clinical execution.
The October 8 retirement record additionally compares fresh full clinical runs.

| Change | Recorded checks | Evidence |
| --- | --- | --- |
| Older workflow retirement, October 8 | Fresh successful/blocked synthetic and current clinical equivalence; full retained suite; old packages physically absent | [Acceptance record](history/workflow_retirement_20261008.md) |
| Dependency extraction, October 6 | 378 portable tests, 81 subtests; 24 frozen numerical cases and three unchanged PNGs; expected Layer 4 preflight hold | [Validation record](../archive/migrations/dependency_boundary_before_20261006T150804113789Z/validation.json) |
| Unified launcher, October 6 | 391 portable tests, 81 subtests; synthetic successful/blocked launches and expected real-source preflight hold | [Validation record](../archive/migrations/unified_layers_before_20261006T152102522851Z/validation.json) |
| Default cutover, October 7 | 392 portable tests, 81 subtests; default and compatibility routing, expected preflight hold | [Validation record](../archive/migrations/layered_default_before_20261007T065636726624Z/validation.json) |

Workflow-specific release evidence remains in [Layer 1 acceptance](history/layer1_validation_20261005.md#acceptance-run--october-5-2026),
[Layer 3 acceptance](history/layer3_validation_20261006.md) and
[Layer 4 acceptance](history/layer4_validation_20261006.md).

The linked historical records preserve executed commands, inputs, counts and
rollback details; use current README commands for new runs.

Earlier integration and source-relocation evidence is in [the historical record](history/integration_validation_20261001.md).

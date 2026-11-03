# Workflow replacement coverage

Updated October 8, 2026. One layered pipeline is the target architecture.
The October 8 cleanup preserves its current scientific outputs; it does not
commit to carrying every historical feature forward. Before retiring older
interfaces, explicitly choose which remaining capabilities to migrate and which
to retire. See [the compatibility boundary](compatibility/README.md).

The four layers are the intended destination for retained capabilities.
They already cover integrity, sample statistics and approved comparisons, diagnosis cfDNA
associations, and descriptive disease tracking. They do not yet cover every
capability of the older workflows. Existing compatibility execution remains
available until the gaps below are resolved and dependency checks permit archival.

This is an implementation and retirement map. It does not authorize new scientific
settings, changed inputs, new pooling or file removal. The separately authorized
[October 7 default cutover](workflow_contracts.md#layered-default-cutover--october-7-2026)
is reflected in the entrypoint table. The
[scientific contracts](workflow_contracts.md) remain authoritative. In particular,
the harmonized sources and recorded identifiers deliberately differ
from older preparation. Functional replacement does not imply identical patient
populations, measurements, filenames, or historical numerical results.

## Classification

| Status | Meaning for migration |
| --- | --- |
| Replaced within stated scope | A released layer supplies that function under its own approved contract. The older implementation may still be needed for compatibility or by another module. |
| Partially replaced | A released layer supplies part of the function; the listed gap remains available through compatibility execution. |
| Planned migration | The investigator selected a layered destination; implementation and acceptance remain outstanding. Compatibility execution is retained until validated. |
| Retained | Required shared infrastructure, maintenance, historical validation, or older functionality with no released layered replacement. Retention is not a promise to migrate it. |
| Deferred | A possible future layered increment, not a current capability or implementation authorization. Existing compatibility execution is retained where available. |
| Retired | Execution already retired by an explicit earlier decision. Retained evidence must not be deleted or execution silently restored. |

No additional capability is declared retired by this map. The investigator chose
to migrate longitudinal DNA models and bootstrap trends, handling correlations,
and combined yield/WBC panels into the appropriate layers, retaining compatibility
execution until validated. This authorizes migration planning, not unreviewed
scientific adaptations. Other unresolved capabilities retain compatibility execution.

## Scientific capability coverage

The implementation links identify the current owners. Major eligibility,
threshold, model and pooling rules are defined in the contracts rather than
duplicated here.

| Capability and older owner | Layered owner and coverage | Classification and disposition |
| --- | --- | --- |
| Workbook structure, numeric/formula checks and source availability embedded in older preparation | [Layer 1](layers/data_integrity.md), with shared [source reader](../analysis/sample_io.py) and [integrity checks](../analysis/data_integrity/checks.py) | Replaced for harmonized inventory integrity. Workflow-specific clinical checks and older-source validation remain required; Layer 1 does not replace every analysis precondition. |
| Inventory availability, missed samples and center summaries in [sample analyses](../analysis/sample_analysis/analyses.py) | [Layer 2](layers/sample_statistics.md): inventory-based receipt, patient/sample counts, specimen/visit views and approved missed checklist; center details remain audit-only | Replaced for the new inventory contract. Revised receipt rules and identities prevent an old-output equality claim; no verified enrollment roster is introduced. |
| Plasma/CSF volume and elution summaries, including CIRCALL CSF by site | Layer 2 [metrics](../configs/definitions/sample_statistics.json) and specimen/visit views | Replaced within the selected metrics and populations. Retrospective elution is excluded by the current definition; an old report containing it is not proof of a new-layer omission to repair automatically. |
| DNA recovery and blood-pellet summaries/distributions in sample analysis | Layer 2 concentration, mass, fraction and size descriptions; albumin/DIN are excluded by the October 7 review | Partially replaced at the report-family level. Field availability and specimen/assay mapping follow the current metrics; do not claim every older Vario endpoint or figure has an identical replacement. Retain older preparation/reporting until metric-level disposition is reviewed. |
| Cohort-specific and pooled descriptive plasma summaries in [pooled.py](../analysis/sample_analysis/pooled.py) | Layer 2 separate-cohort and approved pooled aggregate views | Replaced within Layer 2's pooling scope. This does not replace pooled inference or pooled controls from the older longitudinal workflow. |
| Explicit between-cohort mean difference, mean ratio and percent-difference table from `cohort_comparison` | Layer 2 supplies descriptive cohort values, but not those explicit comparison columns | Partially replaced. Retain the older table pending a decision to migrate those derived comparisons or retire them. |
| Control descriptions and protocol annotation in [extraction.py](../analysis/sample_analysis/extraction.py) and older preparation | Layer 2 separately describes selected controls and recorded extraction state | Partially replaced. Older pooled-control preparation and protocol-annotation exports have no equivalent Layer 2 contract; retain them with compatibility execution. No protocol inference is added. |
| Handling/recovery scatter plots and descriptive Pearson/Spearman coefficients, including pooled coefficients | Layer 3 now includes approved diagnosis-only handling-variable comparisons; the older all-visit handling/recovery descriptions and pooling are not fully replaced | Retain the older scope pending explicit migration or retirement. Diagnosis sample selection is not equivalent to the old all-visit population; neither establishes causal handling effects. |
| Patient longitudinal DNA trajectories and cohort/pooled bootstrap median trends in [longitudinal_trends.py](../analysis/sample_analysis/longitudinal_trends.py) and [pooled_trend.py](../analysis/sample_analysis/pooled_trend.py) | Planned migration to Layer 2; current sample/visit distributions do not supply these trajectories or intervals | Partially replaced for descriptions; retain trajectory/bootstrap compatibility until the planned increment passes validation with explicit population and output scope. |
| Patient-only longitudinal mixed-model contrasts, BH correction, diagnostics and optional sensitivity paths | Planned migration to Layer 3; no released implementation | Retain [sample analyses](../analysis/sample_analysis/analyses.py) and [statistics](../analysis/sample_analysis/statistics.py) until validated. Optional availability limits remain governed by the existing contract; no new sensitivity model is authorized. |
| Exploratory pooled longitudinal inference in `sample_analysis/pooled.py` | Planned migration with the Layer 3 longitudinal capability | Retain separately from Layer 2's descriptive pooling and Layer 3's pooled diagnosis descriptions. Neither is a substitute for the older inferential question; harmonized population/pooling changes require review. |
| Diagnosis cfDNA regressions, predictor descriptions, sensitivity and pooled diagnosis views in `cfdna_associations` | [Layer 3 contract](workflow_contracts.md#layer-3-diagnosis-cfdna-associations--october-6-2026), [preparation](../analysis/advanced_analysis/preparation.py), [statistics](../analysis/advanced_analysis/statistics.py) | Replaced for the harmonized diagnosis scope, with approved preparation differences. Both entrypoints now use retained `association_methods.py`; Layer 3 no longer imports the older association package. |
| Retrospective and CIRCALL MRD descriptions and pooled MRD trajectories/status summaries | [Layer 4](layers/disease_modeling.md) owns local methods, preparation and reports | Replaced for the approved disease-tracking scope. Recorded-ID preparation differs from older retrospective grouping. The current CIRCALL annotation hold remains intentional; blocked output is not permission to use the older parser as a fallback. |
| Recorded blast counts, CIRCALL WBC trajectories and separate-cohort comparisons | Layer 4 full-range and early-window descriptions | Replaced for recorded-count descriptions. Count/MRD populations remain distinct. Under the current all-components cohort gate, the CIRCALL MRD hold also holds CIRCALL counts; do not weaken the gate to claim complete output coverage. |
| Normalized blast mixed model in [blast_kinetics](../analysis/blast_kinetics/pipeline.py) | Layer 4 descriptive release has no normalized-model implementation | Deferred as a possible separately selected Layer 4 increment. Retain explicit normalized-model compatibility execution and its configuration/validation. |
| Combined DNA-yield/WBC panels in [yield_wbc_panel.py](../analysis/sample_analysis/yield_wbc_panel.py) | Planned reporting composition using Layers 2 and 4; no released implementation | Retain until validated. Keep source provenance and approved display alignment without introducing patient linkage or association inference; neither analytical layer should depend on the combined report. |
| Older statistics workbooks and rebuilding them from retained CSVs | New layers own their own report workbooks; [stats_workbooks.py](../analysis/sample_analysis/stats_workbooks.py) rebuilds older reports | Replaced for new report production; retain the old rebuilder for compatible historical runs. New workbook layouts are not drop-in replacements for old CSV contracts. |

## Entry point and profile disposition

Profile names below describe current dispatch after the October 7 default cutover.
Paths are relative to the repository root. The layered master owns current source
selections and options; single-layer profiles are references, and compatibility
profiles resolve to `configs/compatibility/`; [README](../README.md#run) owns routine layer commands and
output destinations. This table records capability disposition, not frozen settings.

| Entry point or profile | Current selection | Disposition |
| --- | --- | --- |
| `python run.py`, [run_all_layers.sh](../run_all_layers.sh) and [pipeline_layers.json](../configs/pipeline_layers.json) | Layers 1–4 in one integrated run | Default layered execution; combined outputs under `outputs/layered/`. Full execution preserves independent results and blocked reports, with a nonzero overall result for holds/failures. Validate-only reports known holds without execution. |
| [pipeline_integrity.json](../configs/pipeline_integrity.json) | `data_integrity` | Retain Layer 1 profile and standalone module. |
| [pipeline_sample_statistics.json](../configs/pipeline_sample_statistics.json) | `sample_statistics` | Retain Layer 2 profile and standalone module. |
| [pipeline_advanced_analysis.json](../configs/pipeline_advanced_analysis.json) | `advanced_analysis` | Retain Layer 3 profile and standalone module. |
| [pipeline_disease_modeling.json](../configs/pipeline_disease_modeling.json) | `disease_modeling` | Retain Layer 4 profile and standalone module. |
| `python run.py --config configs/pipeline_all.json` and [pipeline_all.json](../configs/pipeline_all.json) | Older `canonical` plus `cfdna_associations` | Retained explicit compatibility execution with unchanged sources and settings; no longer the implicit default. |
| [pipeline_longitudinal.json](../configs/pipeline_longitudinal.json) | Older canonical longitudinal workflow | Retain: models, trends and pooled inference are not fully replaced. |
| [pipeline_kinetics.json](../configs/pipeline_kinetics.json) | Older canonical recorded counts plus MRD | Functional replacement is Layer 4; retain compatibility until retirement and dependency checks are complete. This profile does not select normalized kinetics. |
| [pipeline_mrd.json](../configs/pipeline_mrd.json) | Older canonical MRD | Functional replacement is Layer 4; retain compatibility for its older sources and rules. |
| [pipeline_cfdna_spearman.json](../configs/pipeline_cfdna_spearman.json) | Older diagnosis associations with sensitivity | Functional replacement is Layer 3 under new preparation; retain compatibility and the required engine. |
| Direct `run.py --workflow canonical` and `--workflow cfdna_associations` flags | Older selectable analyses | Retain active flags and options. Former `legacy` mode is a different, already-retired interface. |
| Explicit `blast_kinetics` JSON workflow; `python -m analysis.blast_kinetics`; [YAML profiles](../configs/blast_kinetics/blast_kinetics.yml) | Optional normalized/generic configured measurement model | Retain outside the descriptive layered release. The [raw-measurement example](../configs/blast_kinetics/raw_measurement_example.yml) also remains supported. |
| Former legacy execution, `--stage`, `--retrospective-workbook`, `scripts` and `kinetics_pipeline` entrypoints | Already retired or relocated | Preserve historical evidence; do not restore former execution paths. See the [retired execution contract](workflow_contracts.md#retired-historical-execution). |

## Shared infrastructure and supporting tools

| Area | Retain now | Boundary before any move |
| --- | --- | --- |
| Reading, integrity, source state and controls | `sample_io.py`, `source_state.py`, `data_integrity/`, `retrospective_controls.py` | Source selection/hash checks are shared directly; the Layer 1 runner re-exports them for compatibility. The controls module still combines integrity and Layer 2 observations; retain it for both consumers. |
| Scientific dependency for Layer 3 | [association_methods.py](../analysis/association_methods.py) | Retained predictor definitions, fits, sensitivity and diagnostic plotting; no workbook preparation or row-export code. The older association module re-exports these methods for compatibility. |
| Configuration parsing | [configuration.py](../analysis/configuration.py) | Layers 2–3 import the duplicate-key parser directly. `pipeline._unique_object` remains a compatibility alias. Layer-specific definition validation remains with each layer. |
| Layer 4 methods | `disease_modeling/`, its definitions/profile and method-origin metadata | Follow the [retained-file boundary](#layer-4-retained-files); independent execution does not authorize retirement. |
| Orchestration, publication and provenance | `run.py`, `cli.py`, `pipeline.py`, `worker.py`, `outputs.py`, `artifacts.py`, `provenance.py`, `figure_layout.py` | Some files still contain older dispatch/publication contracts. Preserve compatibility while separating ownership; do not move them with a single scientific workflow. |
| Scientific definitions and environment | Active definitions, profiles, source catalog, extraction protocols, shared Conda YAML/lock, scientific contracts | Retain configurations needed by both generations; proposed definitions remain historical review material, not active schema replacements. |
| Workbook maintenance | `workbook_cleanup.py`, `workbook_harmonization.py`, `repair_inventory_formulas.py`, `patient_ids.py`, `extraction_status.py`, `sample_analysis/migrate_retrospective_blasts.py` | Retain as explicitly invoked maintenance tools. They are not layer execution or automatic preflight repair; source adoption/identity changes retain their approval safeguards. |
| Historical report helpers and validation | `stats_workbooks.py`, `pooled_trend.py`, `yield_wbc_panel.py`, `analysis/validation/`, historical command shims in `tests/validation/`, workflow tests and synthetic fixtures | Audit import and artifact-format dependencies before relocating older code. Preserve checks needed to interpret retained runs; new layer tests do not replace all historical validators. |
| Local cache cleanup | Root `codex-clean-cache` | Unrelated utility, outside pipeline replacement scope. Do not invoke, delete or move it as part of scientific migration. |
| Clinical inputs, outputs, archives and snapshots | Existing authoritative locations | Retain as evidence. This classification never authorizes relocation, duplication or deletion of clinical data. |

## Remaining decisions and acceptance gates

| Decision | Current safe disposition | Evidence required before changing it |
| --- | --- | --- |
| Longitudinal models, pooled inference, bootstrap trends and handling correlations | Migration selected; retain compatibility until validated | Resolve harmonized preparation contracts and explicit acceptance populations, preserve approved methods, and verify synthetic numerical references. New eligibility, identity or pooling changes still require confirmation. |
| Combined yield/WBC panels | Migration selected; retain compatibility until validated | Define the reporting interface and source/visit alignment without inventing cross-modality linkage. Validate the composition after the Layer 2 trend capability is available. |
| Older metric/derived-comparison and protocol-report coverage | Retain compatibility | Review old-to-new fields and required deliverables, including explicit between-cohort difference/ratio columns and protocol exports. Do not infer missing scientific metadata or restore an excluded endpoint automatically. |
| Optional normalized modeling | Deferred layered increment; retain explicit older workflow | Separate implementation decision and validation; no automatic enablement in Layer 4. |
| Default switch and failure routing | Unified layered execution is now the default; independent continuation and CIRCALL hold retained | Default dispatch and explicit compatibility selection are tested. No older capability is retired by the default switch. |
| Archival move of older packages | No package is yet approved for wholesale removal | Resolve capability disposition and all runtime/test/helper imports. Run each retained layer in an isolated tree without candidate old packages, then verify scientific outputs and publication. Review concrete moves and rollback before acting. |

## Planned migration increments

| Increment | Destination and dependency | Completion condition |
| --- | --- | --- |
| Descriptive longitudinal DNA | Layer 2 owns patient/visit preparation for its trajectories and cohort/pooled bootstrap trends; retain deterministic settings and explicit control populations | Approved harmonized preparation; reference checks on identical synthetic observations; validated availability, intervals, figures and source provenance. Sample-level summaries remain distinct from patient-level summaries. |
| Handling and recovery correlations | Layer 3 owns descriptive pairs and coefficients; reuse reviewed low-level reading helpers, not Layer 2 aggregate reports | Explicit eligible pairs and scales; no added correlation tests or extraction-effect claims; cohort/pooled behavior and unavailable pairs reconcile. |
| Longitudinal DNA inference | Layer 3 owns repeated-measure models, planned contrasts, pooled inference and existing optional sensitivities | Approved identity, visit, endpoint and pooling adaptations; identical-observation method checks; model diagnostics, correction families and unavailability behavior validated. No automatic general multivariable model. |
| Combined yield/WBC presentation | A reporting component consumes explicitly selected Layer 2 trend evidence and Layer 4 count evidence; follows descriptive trend migration | Display alignment and separate populations retained; source lineage verified; no count/MRD/DNA identity join or new inference. Exact internal module location can be selected during implementation. |

These increments are planned work, not additions to current profiles. Each keeps
its compatibility counterpart runnable until its acceptance checks pass; no
compatibility retirement is automatic at implementation completion.

The initial dependency extraction is complete: Layer 3 uses retained association
methods, and Layers 2–3 use shared source/configuration helpers. All four layers
have executed standalone and in one integrated synthetic run in a copy without
`sample_analysis`, `cfdna_associations` or `blast_kinetics`. The tests reconcile
aggregate evidence, PNGs and artifact hashes. This establishes a runtime boundary,
not completion of the planned scientific migrations or permission to archive
compatibility packages and their historical validators.

## Layer 4 retained files

Layer 4 owns `analysis/disease_modeling/`, including the method-origin metadata,
and `configs/definitions/disease_modeling.json` / `configs/pipeline_disease_modeling.json`.
It does not import `analysis/sample_analysis`, `analysis/blast_kinetics`,
`analysis/cfdna_associations`, `analysis/advanced_analysis`, or `analysis/sample_statistics`.
Its standalone completion validator is local; the master uses a lazy Layer 4 dispatch.

Retain the shared infrastructure: `sample_io.py`, `sample_definitions.py`, `data_integrity/checks.py`,
`retrospective_controls.py` for its integrity-only function, `figure_layout.py`,
`provenance.py`, `outputs.py`, and package `__init__.py` files. For master execution,
retain `run.py`, `cli.py`, `pipeline.py`, `worker.py` and `configuration.py`. The Layer 4 code-hash list
explicitly records these retained files instead of hashing every legacy scientific
module. Preserve the shared integrity definition, Conda definition/lock, scientific
contract and explicitly selected inputs. `retrospective_controls.observations`,
which describes samples for Layer 2, is not called or imported by Layer 4.

Before an actual archival move, review other active layers: Layers 1–3 and old
compatibility entrypoints may still need files that Layer 4 does not. The isolated
execution test proves Layer 4 independence; it does not authorize moving or deleting
those files or certify every other workflow as independent.

## Evidence and recovery

Layer 3 and Layer 4 have named [Layer 3 acceptance](history/layer3_validation_20261006.md)
and [Layer 4 acceptance](history/layer4_validation_20261006.md) records. Layer 4 includes
an isolated execution test without older scientific packages and synthetic method
references; its accepted current-source hold is not scientific equivalence to
older clinical outputs. Layer 1/2 rules and checks are documented in their guides.

The retained checkpoint after plotting-state isolation records
351 passing portable tests and 81 passing subtests, with clinical-workbook tests
excluded. That result verifies software behavior, not complete replacement coverage.
The [validation record](../archive/migrations/plot_style_isolation_20261006T145748543893Z/validation.json)
contains the exact commands. No clinical execution is required to create this map.

Before this documentation change, the relevant documentation and README were
saved under
`archive/migrations/replacement_coverage_before_20261006T145956235425Z/`.
The broader [recovery baseline](../archive/migrations/repository_baseline_20261006T144151937060Z/RECOVERY.txt)
and subsequent plotting checkpoint remain intact. Restore only reviewed affected
files, preserving subsequent edits and all source/output evidence. The coverage
decisions alone did not change code, profiles or scientific settings; the separately
approved October 7 default cutover is recorded in the contract linked above.
The later dependency extraction preserves old import paths and executable interfaces;
its pre-change checkpoint is
`archive/migrations/dependency_boundary_before_20261006T150804113789Z/`.

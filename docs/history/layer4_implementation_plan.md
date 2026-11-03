# Layer 4 disease modeling implementation plan

First descriptive release approved and implemented, October 6, 2026. The investigator
additionally required local scientific methods with no runtime imports from old
workflow helpers. The implementation and current CIRCALL source hold are documented
in the [Layer 4 guide](../layers/disease_modeling.md); normalized modeling remains a later
opt-in increment. The proposal below records the original design and tradeoffs.

Build an independently runnable, read-only
`disease_modeling` workflow for measurable residual disease (MRD) and recorded
blood-count trajectories. Start with descriptive disease tracking for both cohorts;
add the existing normalized blast model as a separate, explicitly selected increment.
Reuse established scientific methods while adapting preparation to the current
sources. Approval of this plan would authorize its stated preparation changes;
writing the plan does not change the active workflows or scientific contracts.

## Scope and first release

The first release should produce retrospective and CIRCALL MRD summaries and
trajectories, recorded blast-count trajectories for both cohorts, CIRCALL WBC
trajectories, and compatible pooled MRD descriptions. Disease tracking must run
without Layer 2 summaries, Layer 3 association results, or eligibility based on
having a usable cfDNA sample. Controls contribute to selected inventory integrity
checks only.

The first release has no disease regression, MRD hypothesis tests, count-derived
MRD, outcome prediction or survival analysis. DNA-yield models and cfDNA–disease
associations remain Layer 3 questions. Retrospective `MRD_CMF` is present but is
outside the established IgTCR scope; combining assays needs a separate decision.
Retrospective longitudinal WBC is unavailable in the selected count source and
must not be reconstructed from diagnosis WBC or blast fractions.

## Selected sources and identity boundaries

Use explicit CLI/profile paths. These candidate sources were checked for sheet
and header availability; patient coverage, annotation validity and model eligibility
must be reassessed during implementation. Existing profiles using earlier inventory
paths are not suitable for the harmonized sources simply by replacing filenames.

| Population and measurement | Candidate workbook under input | Sheet and fields | Identity basis |
| --- | --- | --- | --- |
| Retrospective MRD | cfDNA_inventaire_retrospective_05102026.xlsx | Inventaire: MRD_IgTCR, timepoint, specimen_type | Recorded patient_id, qualified by cohort |
| CIRCALL MRD | inventaire_CIRCALL_05102026.xlsx | cohorte_lal: MRD_TP1, MRD_TP2 | Recorded circall_id, qualified by cohort |
| Retrospective blast counts | retrospective_blast_count_01102026.xlsx | blast: day, blast_count_x10*9/L; tt_d1_date and num_date retained as source metadata | Existing trimmed, case-sensitive surname grouping within this source only; no patient_id column is currently present |
| CIRCALL blast and WBC counts | CIRCALL_wbc_blast_count_01102026.xlsx | blast: day, blast_count_x10*9/L; wbc: day, wbc_count_x10*9/L | Recorded circall_id, qualified by cohort and measurement |
| Optional integrity controls | Selected CIRCALL inventory and cfDNA_donors.xlsx | cohorte_control and Feuil1 respectively | No disease observations or linkage |

For inventory MRD, propose the recorded-ID basis already adopted in Layers 2 and
3. Retrospective preparation would deliberately replace the older surname-based
MRD grouping, and map `treatment_phase`/`tissue` selection to harmonized
`timepoint`/`specimen_type`. These are explicit preparation changes to approve;
preserve recorded IDs without case folding or name/DOB fallback.

For retrospective counts, the smallest migration preserves the existing identity
rule in memory, isolated from inventory MRD. This retains the risk that different
people sharing a surname could be grouped together. Approve this compatibility
limitation explicitly, or supply an investigator-reviewed pseudonymous ID mapping
before including retrospective counts. The workflow must never generate that
mapping automatically from names. An ID correction would be a separate backed-up
source operation, not part of a read-only analysis run.

Do not match patients across cohorts, join retrospective count names to patient_id,
or intersect count populations with inventory cfDNA eligibility. Initially keep
MRD and count populations separate even where CIRCALL IDs exist in both sources.
Patient counts across these modalities cannot be added or presented as a deduplicated
global population without an approved linkage rule.

## Scientific rules and decisions

Retain the current methods in the linked contracts; historical prose superseded
by later amendments is not an active setting. Put the resolved Layer 4 mappings,
units, population rules, display conventions and seeds in a versioned definition
file, and record its hash. The table below distinguishes retained methods from
proposed preparation or orchestration decisions.

| Decision | Proposed Layer 4 rule | Basis and approval status |
| --- | --- | --- |
| Retrospective MRD selection | Diagnosis is not the eligibility visit for follow-up MRD. Select timepoint TP1/TP2 and specimen_type bone marrow, keyed by patient_id. No plasma/tube/cfDNA-yield filter or sample-ID receipt requirement is introduced. | Harmonized adaptation of the [retrospective MRD contract](../workflow_contracts.md#retrospective-mrd-by-treatment-phase--october-1-2026); approve new field/identity mapping |
| CIRCALL MRD selection | Read patient-level MRD_TP1/TP2 metadata across identified patient records, independently of the row's sample visit or specimen. Collapse identical repeats; conflicting nonmissing annotations fail. | Retain the [CIRCALL MRD method](../../archive/retired/older_workflows_20261008/docs/compatibility/sample_analysis.md#circall-mrd-plot) |
| MRD population and denominators | Preserve CIRCALL's population with at least one nonmissing follow-up MRD result, and retrospective patient/visit groups represented by selected marrow rows, including missing results. Coverage also reports identified source patients and unavailable visits. Do not silently replace these different population rules with a common enrolled-cohort denominator. | Retain source-specific populations; a common missingness denominator would require a separate scientific decision |
| MRD values and repeats | Preserve quantified residual fractions, negative, missing, CIRCALL uncertain significance, and retrospective positive nonquantifiable annotations/bounds. Keep retrospective approved worst-outcome priority and report resolved disagreements. Bounds are not quantitative measurements. | Retain [retrospective duplicate/bound rules](../workflow_contracts.md#retrospective-mrd-by-treatment-phase--october-1-2026) and CIRCALL conflict failures |
| Unknown or invalid MRD | Propose that the harmonized unknown marker remains an unavailable source value, distinct from the clinical category unknown significance. Reject malformed selected annotations and invalid quantitative fractions; do not interpret numeric zero as a negative MRD result. Preserve unavailable caches separately. | Approve harmonized missing/unknown mapping; retain existing clinical parser/range checks |
| MRD displays | Keep measured values, reported upper bounds, assigned categorical display positions and assumed diagnosis references distinct. Retain source-specific and pooled display conventions, including which lines may connect assigned values or bounds. Do not infer new detection limits. | Retain [MRD guide](../../archive/retired/older_workflows_20261008/docs/compatibility/sample_analysis.md#retrospective-mrd) and [pooled MRD contract](../workflow_contracts.md#approved-descriptive-pooled-mrd--october-1-2026), including subsequent display amendments |
| MRD pooling | Both cohorts must have usable MRD preparations. Concatenate without identity matching, use nominal Diagnosis/TP1/TP2 visits and the existing fixed included-patient denominator. Keep the current display grouping and hidden missing segments; tables retain all underlying categories, missing counts and denominator. No pooled MRD inference. | Retain approved descriptive pooling; recorded-ID preparation may intentionally change membership/counts |
| Count endpoint and validation | Recorded absolute counts only, in the investigator-confirmed units selected in the profile. Retain zeros, missing counts and source time metadata; reject negative/nonfinite counts, malformed measured days and duplicate subject/day/measurement records. No derivation from WBC × fraction, no imputation or duplicate averaging. | Retain [count contract](../workflow_contracts.md#kinetics-consolidation--october-1-2026); check current sources independently |
| Count time and baseline display | Preserve recorded days and established diagnostic-baseline selection. Keep the early comparison window explicit and separate from full-source coverage. Provide a clearly named full recorded-range view alongside the early-window comparison; report which observations appear in each. Never apply the comparison window as a global analytical exclusion. | Existing baseline/window rules; full-range view is a proposed presentation addition. Resolve the current guide/code mismatch about blast plot ranges during implementation |
| Count plots | Linear recorded-day x-axis, existing log count y-axis with a linear-display option. Zeros remain in tables, are counted on log figures, and break connecting lines; no pseudocount or invented zero location. Cohort colors and patient/measurement counts remain visible. | Preserve current code and [later concentration/count display amendments](../workflow_contracts.md#kinetics-consolidation--october-1-2026); older guide references to a zero strip are superseded |
| Two-cohort count comparisons | Shared axes and cohort-labeled trajectories only. No merged patient population, pooled count summaries, cross-cohort fit or shared MRD/count calendar mapping. | Retain existing descriptive comparison scope |
| Integrity and failure scope | Propose the same whole-cohort inventory gate as Layers 2/3, including selected controls, plus source-specific count/MRD structural checks. Reviews permit execution; definite failures block that cohort. An independent clean cohort may complete; pooled output requires both relevant cohorts. | Approve Layer 4 gate scope; unrelated inventory errors can block disease reports under this deliberately conservative choice |
| Missing analyses | A valid source without eligible disease measurements produces an explicit unavailable result. A missing selected source, invalid structure, conflicting clinical metadata or unexpected execution failure produces nonzero final exit after available reports publish. Do not silently suppress a selected input failure. | Proposed reporting behavior consistent with Layers 2/3 |
| Normalized modeling | Disabled in the first release. Later delegate the explicitly selected retrospective compatibility profile to the existing engine without altering its eligibility, exact baseline, normalization, bootstrap, winsorization, transformation or fit. Its baseline rule is distinct from descriptive diagnostic display. | Existing [normalized contract](../workflow_contracts.md) and [versioned profile](../../archive/retired/older_workflows_20261008/configs/blast_kinetics/blast_kinetics.yml); opt-in increment only |

Labels must distinguish clinical observations from assumptions: diagnosis MRD
reference is not measured MRD or blast-cell percentage; a plotting floor is not
an assay limit; nominal TP visits are not confirmation of common calendar days.
Separate log reduction calculated from a measured fraction from any assigned
display reduction. No multivariable, censoring, survival or cross-modality model
is implied by the name disease modeling.

## Implementation increments

1. **Preparation and integrity.** Add `analysis.disease_modeling` with a
   `python -m analysis.disease_modeling` entrypoint, a versioned
   `configs/definitions/disease_modeling.json`, and a separately selected
   `configs/pipeline_disease_modeling.json`. Use the shared raw/cached reader
   directly. Reuse existing MRD annotation parsers and repeat-resolution rules;
   add harmonized-source adapters rather than passing new inventories through
   obsolete canonical adapters. Reuse count baseline, summary and trajectory
   helpers where they preserve the approved preparation and privacy boundaries.

2. **Descriptive reports.** Produce cohort MRD and count workbooks/figures, then
   compatible pooled MRD and separate joint blast-count comparisons. Keep all
   original values and source coordinates available in memory for reconciliation.
   Export aggregate counts and cell-reference findings; retain existing stricter
   bans on retrospective count/MRD and normalized-model row exports. Hashed
   patient tables are not automatically permitted merely because they are hidden
   under `.audit`. Reconstruct row-level evidence from hashed sources during
   validation instead of adding new clinical row exports by default.

3. **Orchestration and acceptance.** Register `disease_modeling` in the existing
   worker, completion validator and publisher, using the shared `pre_analysis`
   environment. Preserve every established workflow/default. After Layer 4's
   preflight, standalone/master validation and acceptance pass, add its profile
   after Layer 3 in `run_all_layers.sh`; retain preflight-all and stop-on-failure
   behavior and explicit layer progress messages.

4. **Optional normalized model.** Add an explicitly selected compatibility mode
   only after the descriptive release is accepted. Reuse
   `analysis.blast_kinetics` and its versioned profile; retain no row-level exports
   and separately identify normalized versus recorded-count results. Confirm the
   selected source/profile and record model eligibility separately. A CIRCALL
   normalized model, a new baseline, a new bootstrap or broader fitted disease
   model requires its own scientific specification. Existing standalone normalized
   kinetics remains available throughout.

## Interface and results

These interfaces are proposed, not executable commands yet. Expose explicit
patient inventories, CIRCALL counts, retrospective blasts, donors, cohort and
analysis selection, selected-control integrity inclusion, rule/definition files,
confirmed count units, existing baseline/window and plot settings, MRD display
levels/duplicate policy, pooled MRD descriptions, fresh output destination and
validate-only mode. The descriptive profile should select both patient cohorts
and their four explicit sources, with controls for integrity and compatible pooled
MRD descriptions; it must not enable normalized modeling.

Layer 4 validate-only should check selected files, headers, units, identities,
annotations, resolved settings and gates without publishing or fitting models.
Return failures explicitly and preserve their cohort scope. Distinguish an unusable
configuration from a completed preflight that found a blocked clinical cohort:
record the latter as cohort findings rather than rejecting all execution metadata.
Validate-only should report those findings and return nonzero for definite errors.
Full execution should accept the structured findings, publish blocked/unavailable
reports and continue an independent clean cohort before its final nonzero exit.
This distinction needs explicit orchestration tests; otherwise the existing generic
preflight failure path would prevent those reports from being generated.
If optional normalized modeling is selected later, preflight
should validate its configuration and preparation; fits belong to execution.
The existing standalone normalized-kinetics validate-only behavior, which can fit
models, remains unchanged and documented separately.

Proposed output layout:

```text
outputs/layer4_disease_modeling/run_<timestamp>/
├── retrospective/
│   ├── disease_modeling.xlsx
│   └── figures/{mrd,blood_counts}/
├── circall/
├── pooled/                 # Compatible MRD descriptions only
├── comparisons/            # Separate-cohort blood-count figures
└── .audit/workflows/04_disease_modeling/
```

Use direct scope folders for single-layer runs and `04_disease_modeling/` for mixed
integrated runs. Each applicable Excel 2021-compatible workbook should have
Summary, Coverage, MRD, Counts, Models, Diagnostics and Definitions tabs. The
first release's Models tab explicitly states that modeling is disabled. Report
modality-specific patients and measurements, missing/unknown/cache availability,
duplicate resolution, exclusions, comparison-window counts, zero values,
unavailable analyses and denominator definitions. Scope-specific inapplicable
sections remain clearly labeled; do not fill them with invented zero results.

Publish PNG/PDF pairs grouped by clinical comparison, with legends outside data,
clean clinical titles and explicit patient/measurement counts. Logs, filenames,
legends, workbook cells and PDF metadata must not contain names, DOB, sample IDs
or unrestricted notes. Where an existing helper writes broader outputs or labels,
reuse only its calculation functions and add a safe Layer 4 presentation adapter.

Reuse existing commands/settings/code/environment provenance, actual package
versions, ISO execution timestamps, source/definition/rule hashes, input rechecks
and publication checksums. Preserve failed-workflow evidence and independent
cohort completion. New destinations must not exist; no historical result or source
overwrite is included.

## Validation and acceptance

Use synthetic fixtures for harmonized source selection, recorded identities,
MRD category/bound parsing, duplicate resolution, same-name/different-ID MRD
patients, and the intentionally separate retrospective count identity basis.
Test that future/planned sample rows do not suppress patient-level CIRCALL MRD,
and that neither plasma eligibility nor receipt gates disease annotations.

Compare reused functions on identical prepared observations with existing MRD,
count and optional normalized engines. Check original values, missingness, zeros,
patient/visit denominators, full versus comparison time ranges, diagnostic display
selection, units, deterministic figures and explicit skipped reasons. Cover
unknown annotations, absent/intentional-empty caches, invalid fractions/counts,
duplicate days, empty/constant/small sources, conflicting metadata and malformed
or missing headers. Do not claim clinical equivalence when sources or identity
rules differ; document those approved preparation differences separately.

Verify pooled MRD fixed denominators and category sums, the retained display
grouping/missing convention, source bounds versus assigned positions, cohort
colors, and the absence of pooled/count/MRD inference. Test included/excluded
controls, a blocked peer cohort, unavailable retrospective WBC, execution failures,
privacy in every artifact, fresh destination refusal, source byte preservation,
publication hashes, workbook reconciliation and standalone/master equivalence.
If the normalized increment is enabled, also verify its exact profile, eligibility,
filtering, daily/bootstrap estimates, fits and numerical diagnostics against the
existing engine with the same prepared observations.

Run the relevant `tests/sample_analysis/` MRD/count suites, `tests/blast_kinetics/`
when normalization is included, Layer 1/2/3 and orchestration regression suites,
plus new `tests/disease_modeling/` acceptance tests. Run integrated preflight and
both standalone/master executions against explicitly selected current sources;
record exact commands, actual modality-specific coverage and limitations. Inspect
main figures and validate workbook content, PNG/PDF files and provenance before
adding the workflow to the all-layers script. Acceptance requires accurate,
reproducible descriptions or justified unavailable outcomes, not a significant
association or a successful normalized fit for every cohort.

## Decisions before implementation and rollback

Approve the proposed MRD field/recorded-ID migration and unknown-value mapping,
choose how to handle the retrospective count identity limitation, and approve the
whole-cohort gate and first-release profile/pooled scope. Retaining the current
source-specific MRD populations is the smallest option; changing to an enrolled
cohort denominator or linking count/MRD populations needs an authoritative roster
and a separately agreed rule. Normalized modeling remains a later explicit opt-in.

The first implementation can deliver MRD and CIRCALL counts while reporting
retrospective counts as deferred if their identity choice remains unresolved.
This reduces migration risk but postpones joint blast views. Preserving legacy
retrospective count grouping provides earlier compatibility results, with its
surname-collision limitation stated. A reviewed ID migration improves identity
consistency but requires a separate source correction and new equivalence evidence.

Before implementation, preserve a scoped code/configuration/documentation snapshot
including relevant untracked files and the chosen source hashes, excluding clinical
data, credentials and outputs. The planning checkpoint is
`archive/migrations/layer4_plan_before_20261006T133445Z/` and preserves the pre-plan
documentation and run script. Rollback removes Layer 4 registration/script selection
only after reviewing later edits and restores affected implementation files from
the implementation snapshot. Keep existing sources, workflows, results and audit
evidence; no reset, cleanup, deletion or automatic source correction is authorized.

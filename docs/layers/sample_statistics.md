# Layer 2 sample statistics

Layer 2 describes inventory samples and received-sample measurements and performs
the approved participant-level DNA-per-mL comparisons described below. It does not
run diagnosis-predictor associations, MRD or kinetics. Other profiles remain unchanged.

The [October 7 shared amendment](../workflow_contracts.md#shared-sample-annotations-and-receipt-revision--october-7-2026)
defines current extraction (yes/no from DNA-ID presence) and canonical literal `na`.
The later [Layer 2 review amendment](../workflow_contracts.md#layer-2-measurement-and-pooled-display-review--october-7-2026)
uses Received, Marked missing and Unassessed, with a separate overdue flag. Overdue now includes unreceived samples beyond the applicable deadline: **Marked
missing** for explicit `na`, otherwise **Late** for blank/unknown IDs. Late remains
unassessed receipt, not confirmed missingness, and does not enter receipt-rate
denominators. Untimed rows show counts only. See the
[October 8 follow-up amendment](../workflow_contracts.md#layer-2-late-follow-up-and-center-inventory--october-8-2026). Historical acceptance
records retain their original source/rule hashes.
The scientific decision table in [workflow_contracts.md](../workflow_contracts.md#layer-2-descriptive-statistics--october-6-2026)
is authoritative. Definitions are in `configs/definitions/sample_statistics.json`;
v1 accepts that approved definition set, not arbitrary new pooling policies.

## Reports and selection

Use the [README layer commands](../../README.md#run) and
[master configuration](../../configs/pipeline_layers.json) for current
sources and settings. Layer 2 executes internally as part of every full run.
Its master options include cohort, controls, source/definition paths and
`assessment-time` (an ISO timestamp with explicit offset). An omitted assessment
timestamp is captured once during execution. Direct layer execution is retired.

Each available scope has `statistics.xlsx` and PNG figures, with PDFs when enabled; use the
[shared result layout](../results.md) to locate the layer directory.
Pooled output requires both cohorts. The workbook opens on **Inventory** and has
the following visible tabs when applicable:

CIRCALL visible tabs and labels are in French: **Inventaire**, **Mesures**,
**Comparaisons**, **Témoins** and **Retards** where applicable. The table below
uses the internal English names retained for retrospective and pooled reports.
Translation affects presentation only; numbers, pseudonyms, source references and
hidden technical evidence remain unchanged.

| Tab | What to read |
| --- | --- |
| Inventory | An overall All specimens row, RDB and TRS center totals beneath it (Unknown separately when present), then specimen/timepoint counts; a Center column distinguishes these views: patients, inventory samples, received, marked missing, unassessed, overdue and DNA-ID-derived extracted counts. Timed receipt rates are assessed only where applicable; exact numerators and denominators remain in hidden columns, without cell comments. Overall and breakdown rows overlap. |
| Measurements | Received-sample measurements by specimen, timepoint and recorded DNA label, with units, measured/missing sample counts, median and Q1/Q3. Timepoints follow protocol order. Mean, SD, minimum, maximum, total and further coverage counts are retained in hidden columns. |
| Comparisons | DNA-per-mL tests with participant counts, matched-pair counts, group medians, raw and Holm-adjusted p-values, stars, methods and unavailable reasons. |
| Controls | Optional separate control inventory and measurement tables. Controls never enter patient counts or pooled patient summaries. |
| Overdue | CIRCALL only: approved patient pseudonyms, Center, Timepoint, Specimen and Status (**Late** or **Marked missing**) beyond the applicable deadline. Late rows appear first; filter Status for follow-up. Reason is omitted; source worksheet/row remain hidden. |

A hidden **Reference** tab preserves metadata, blocking reasons, all original main
summary/receipt/measurement/availability rows, control tables and definitions. Unhide
it in Excel for technical details. Hiding is a navigation choice, not access control.
Center totals are exposed in Inventory using the existing native audit aggregates.
Detailed center/specimen/timepoint and other overlapping views remain under
`tables.audit_detail`. Zero center totals mean no inventory rows in that scope;
unassessed receipt rates remain blank. Filtering and formatting
do not change sample populations, denominators or calculation results.

The whole affected cohort, including controls, is held when its source integrity
has definite errors. A blocked workbook shows reasons in Inventory and explicit
blocked messages on the other tabs instead of zero-valued statistics.
The [audit guide](../audit_guide.md#preflight-and-completion) owns shared
preflight, publication and failure behavior. Native evidence includes sanitized
sample observations and aggregate tables.
Unassigned template rows containing only pre-entered timepoint/specimen/protocol fields
are counted under `non_sample_rows_skipped`; they do not block the cohort or enter
receipt denominators. Identified planned timepoints retain their receipt classification.
Rows with sample/DNA IDs or actual clinical/measurement data still require a valid
participant ID. The definition lists the permitted empty-template fields.
Only the missed checklist contains approved patient pseudonyms; other observation
identity keys are hashed. Names, DOB, sample IDs and unrestricted notes are never
exported. Hidden audit folders remain sensitive local evidence, not access control.

## Identity preparation

Retrospective analysis uses recorded `patient_id` values, with no name fallback.
The original name/DOB-based ID backfill was a completed migration and is now
[archived](../../archive/retired/completed_migrations_20261116/README.md).
It is not a preparation step for the current pseudonymised copies; see
[working-input guidance](../deidentification.md). Recorded IDs remain unchanged and define groups even when historical demographic
annotations differ.

## Validation and limitations

Use `tests/sample_statistics`, `tests/maintenance` and `tests/orchestration` with
the [central validation commands](../audit_guide.md#validation-commands).

The tests use synthetic workbooks. They check deadlines and daylight-saving changes,
manual fallback, genuine zeros, formula caches, repeated samples, approved pooling,
controls, privacy, source preservation and independent failure handling. Source runs
and standalone/master comparisons are documented in the local acceptance record.
Excel is reopened and its values compared with audit tables. No Excel/LibreOffice
calculation engine is invoked; layout validation cannot substitute for opening the
workbook in Excel. Missing/stale caches are not repaired by Layer 2.

Historical Layer 2 folders were flattened with unchanged report/figure bytes and
rebuilt artifact indexes; the records are in
`archive/migrations/flatten_layer2_20261006/`.

Retrospective controls use the explicitly selected donor workbook, sheet `Feuil1`. `--no-include-controls` excludes both
cohorts' controls. The master explicitly selects the donor source; no input is guessed. The Controls tab and figures/controls directory
contain the supplied plasma DNA ng/mL endpoint using the existing donor mapping.
Controls never contribute to patient totals, missed lists, or pooled patient summaries.
Other donor measurements and protocol volumes are not inferred from formula constants.

## Comparing controls and timepoints

The two comparisons annotated on DNA-per-mL figures are **controls versus Diagnosis**
and **controls versus TP1 (D29)**. Both use a two-sided Mann–Whitney U test:
controls and patients are different people, so these are independent groups.
The test compares distributions; it is not specifically a test of medians unless
additional distributional assumptions hold. In contrast, comparisons such as
Diagnosis versus TP1 use the paired Wilcoxon signed-rank test: each patient is
compared with themselves, using only participants observed at both timepoints.
The signed-rank interpretation requires reasonably symmetric within-patient
differences. The choice of test follows independence versus pairing, not the
timepoint name. See the primary [Mann–Whitney documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html)
and [Wilcoxon documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html).

For inference, received numeric measurements are reduced to one **median per
participant per timepoint**, including genuine zeros. Missing measurements are not
imputed. Controls are reduced to one median per control participant. Tests use
original ng/mL values, not their logarithms. The existing figures and descriptive
tables still show sample-level observations; zero values remain absent from log
axes, but can contribute to tests. Repeated measurements do not increase the
independent participant count. No participant-level testing table is exported.

The Comparisons sheet contains both control comparisons and all 15 pairs among
Diagnosis, D4, D8, D15, TP1 and TP2. Holm correction covers the full **17-test family
per endpoint, specimen and analysis scope**, including contrasts not drawn on the
figure. Unavailable tests stay unavailable in the report; they occupy p=1 only
internally for correction so missing timepoints do not shrink the planned family.
The permutation engine requires at least two participants in each independent
group or two matched pairs. Smaller comparisons are unavailable with their counts
and reasons retained; observations remain in descriptions. Counts expose sparse
comparisons. All-zero paired differences return p=1; Wilcoxon
otherwise excludes zero differences from signed ranks using `zero_method=wilcox`.

Separate cohort figures use their own controls. **Pooled tests combine both
cohorts' patients and controls**, as requested, while paired matching remains
within cohort and participant. Cohort identities are never linked across sources.
These pooled comparisons are unadjusted for cohort composition and can reflect
cohort differences as well as the clinical comparison. Controls share one combined box in the figure, with points retaining their
cohort colours and shapes. Separate-cohort tests still use matching-cohort controls.

Brackets show **stars**, with no numeric p-values. The pooled DNA-per-mL figure
also names the test beside the highest bracket, omits its title and explanatory
footer, and labels timepoints with total sample n only; participant counts remain
in the workbook. Only the two control
comparisons can receive brackets; nonsignificant or unavailable brackets are
omitted. Numeric raw/adjusted results remain in Comparisons. The convention
uses Holm-adjusted p<0.05 (*), p<0.01 (**), p<0.001 (***) and p<0.0001 (****).
No stars means neither a demonstrated difference nor proof of equivalence; check
the table to distinguish nonsignificance from unavailable tests.

Both tests use SciPy permutation calculations to accommodate small samples and
ties (Wilcoxon uses vectorized sign flips of averaged absolute-difference ranks): exhaustive permutations when the finite space fits the configured budget,
otherwise seeded Monte Carlo permutations. The [definition](../../configs/definitions/sample_statistics.json)
records endpoints, timepoints, correction, zero-difference rule, resampling budget,
batch size and seed. The resampling budget permits four-star resolution even
after the full Holm adjustment. Each contrast derives a stable seed from its scope and names;
row order and audit hashing do not change results. Monte Carlo p-values have finite
resolution and sampling uncertainty, recorded through the method and seed.
Software checks establish calculation behavior, not clinical comparability or
the validity of the signed-rank assumptions.

Figures are grouped by specimen (`plasma/`, `CSF/`, `blood_pellet/`,
`bone_marrow/`) beneath `figures/`; control figures use the same specimen folders
beneath `figures/controls/`. Receipt-status plots stay at the corresponding figure
root. Filenames contain the metric and an assay suffix only when multiple assays
would otherwise collide. When PDF export is enabled, PNG/PDF pairs stay together; empty folders are not created.
Available-volume, elution-volume, cfDNA average-size and cfDNA fraction figures
show overall sample distributions across eligible timepoints in every applicable
compartment, cohort, control and pooled view. Specimens and existing assay groups
stay separate; pooled views retain their existing shared-timepoint eligibility and
cohort-colored points. Each metric configures this through `plot_grouping: overall`.
Measurement tables retain timepoint detail; existing metric exclusions remain in effect.
All Layer 2 workbook sheets display Excel gridlines for readability.

All Layer 2 plots share the Layer 3 visual style: CIRCALL orange circles,
retrospective blue triangles, pale boxes with dark medians, light horizontal
gridlines and legends below the plotting area. Receipt bars use the cohort colour.
Sample points use deterministic horizontal jitter (`plot_jitter_seed`); values,
box summaries and eligibility are unchanged. Exports are 300-dpi PNGs and vector
PDFs with embedded fonts. The shared implementation is `analysis/utils/plot_style.py`.

DNA per mL plasma figures use a grant layout in every cohort and control view:
300-dpi PNGs and optional vector PDFs, readable timepoint labels, lightly shaded boxes, and
reproducibly jittered points with distinct cohort colours and shapes. The logarithmic
y-axis retains original units. Pooled `dna_ng_per_ml_plasma` figures show only Diagnosis, D4, D8, D15, TP1 (D29) and
TP2 (D71), even when only one cohort contributes. The same selected
timepoints apply to both patient cohorts through `plot_visits`; missing timepoints have
empty bins with n=0. D1 means Diagnosis; there is no additional D1 position.
Selected controls that pass their cohort integrity gate share one **Controls**
box before Diagnosis in every DNA-per-mL patient figure. The combined box
retains cohort-coloured points. Pooled plot labels show total sample n only;
distinct-participant counts remain in workbook tables. Controls never
enter patient descriptive counts or summaries. Unselected or unavailable control sources are
omitted; no source is selected implicitly.
The figure selection changes display eligibility only: pooled
workbook summaries retain the shared timepoints. Other metrics retain their existing
timepoint rules. Style and jitter seed are recorded in the metric definition.

DNA/cfDNA total-mass plots (ng) and concentration plots (ng/µL and ng/mL) use base-10 logarithmic
y-axes with values displayed in their original units. Zero/nonpositive values are
included in total n but cannot be plotted; boxplots use positive values only.
Tables retain all observations, including genuine zeros, with no pseudocount.
Volume, fraction and size plots retain linear axes. All plot titles, subtitles and
descriptive footers are omitted under the [shared presentation rule](../results.md#figure-presentation).
Axes and legends retain units and group identities; stored values are unchanged. The legacy assay key holds
DNA-type metadata, and not_recorded means the label was absent, not missing DNA.

The [October 7 Layer 2 review amendment](../workflow_contracts.md#layer-2-measurement-and-pooled-display-review--october-7-2026)
excludes albumin/DIN from this layer and combines pooled cohorts into one box per
metric and nominal timepoint (or across eligible timepoints for overall-display metrics),
with cohort-colored observations. cfDNA fragment size is pooled separately within
plasma and CSF over the shared timepoints. Other statistical
rules and source-integrity gates remain as previously defined. The workbook layout
uses the report organization described above; detailed evidence remains available.

## Calendar collection-volume monitoring

CIRCALL patient folders `figures/CSF/` and `figures/plasma/` also contain
`extraction_input_volume_ml_by_collection_date.png`, with PDF when enabled.
The existing overall-volume figures remain. Each point is one received sample's
recorded available volume against its actual `sampling_date`, across protocol
visits. Dates are not jittered and samples are not joined into trajectories.
The y-axis is linear in mL and retains genuine zeros; no trend model, aggregation,
hypothesis test or automatic performance threshold is added.

Available plasma means plasma available after centrifugation; CSF means available
CSF. Neither is total blood drawn or proof of extraction. Missing volumes and
numeric-volume samples lacking a usable collection date are counted separately in
the legend and `calendar_volume_coverage` audit metadata. Only typed workbook dates
or usable typed formula-cache dates are used. Planned dates, textual/serial-date
guesses and timezone conversion never substitute for collection dates. Source
dates are retained as day-precision local audit metadata with hashed identities.

These are descriptive collection-monitoring views, not adjusted evidence of
declining performance. Visit/participant mix, repeat samples and incomplete volume/
date recording can change the visible pattern. Existing receipt counts help
distinguish absent samples from missing volume metadata.

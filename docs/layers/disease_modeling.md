# Layer 4 disease tracking

`disease_modeling` independently prepares MRD and recorded blood-count trajectories
from explicitly selected sources. Its first release is descriptive: it has no
normalized model, regression, disease prediction or cross-modality patient linkage.
Scientific rules are in the [Layer 4 contract](../workflow_contracts.md#layer-4-disease-tracking--october-6-2026)
and [versioned definitions](../../configs/definitions/disease_modeling.json).
The [October 6 acceptance record](../history/layer4_validation_20261006.md) gives exact commands,
coverage for its recorded source hashes, archival independence evidence and limitations.

## Selection

Use the [README pipeline commands](../../README.md#run) and
[master configuration](../../configs/pipeline_layers.json) for sources and settings.
Layer 4 executes internally as part of every full run. Direct layer execution and
its former selector profile are retired; the following option names describe
internal engine settings exposed through the master.

`--cohort retrospective|circall` selects one cohort. `--analysis mrd|counts`
selects one disease component, with `all` as default. The count sources and their
explicit unit confirmation are required only when counts are selected. Each
selected cohort still requires its inventory for the whole-cohort integrity gate.
An omitted donor workbook is not selected implicitly. Controls are integrity-only;
`--no-include-controls` removes them from the gate. `--no-pool-mrd` disables pooled
MRD descriptions. Configure these settings in the master.

See [preflight and completion](../audit_guide.md#preflight-and-completion) for validation
depth, independent execution after holds and exit status.

## Current CIRCALL source review

The October 6 acceptance and October 8 run initially blocked positive
nonquantifiable annotations at `cohorte_lal!R2`. Following manual review, the
investigator confirmed that NQ means detected but nonquantifiable and the number
following `<` is reported assay sensitivity. The
[October 8 category amendment](../workflow_contracts.md#circall-positive-nonquantifiable-mrd-and-reported-sensitivity--october-8-2026)
supersedes that category hold. `Positive NQ` and `pos NQ` are accepted, with optional
sensitivity metadata in the configured fraction units. Original workbook
annotations remain intact. Sensitivity is neither measured MRD nor an inferred
upper bound. The MRD table reports aggregate `positive_nq_with_sensitivity` and
`reported_sensitivity_counts`; repeated sample rows do not multiply patient counts.

Invalid annotations, invalid sensitivity values and conflicting patient/visit
metadata still block the cohort. With `analysis=all`, a remaining whole-cohort
hold also prevents CIRCALL count publication and dependent pooling/comparisons.
Use each new run's blocked Summary for the actual source cell and reason.

## Sources and interpretation

Retrospective MRD reads `MRD_IgTCR` on TP1/TP2 bone marrow rows, keyed by recorded
`patient_id`. CIRCALL reads `MRD_TP1/TP2` metadata across patient records keyed
by `circall_id`, independently of sample visit/specimen/receipt. Neither population
requires a usable plasma sample or cfDNA measurement. The recorded-ID preparation
deliberately differs from the older retrospective surname-based MRD workflow.

Keep quantified fractions, negative results, missing/unknown source values,
unavailable formula caches, clinical uncertain significance, CIRCALL reported
sensitivities and retrospective positive nonquantifiable bounds distinct. Quantitative MRD zero is invalid under
the retained parser; it is not converted into a negative category. Retrospective
repeat priority and CIRCALL conflict failures remain explicit and recorded.

MRD plots use a log fraction y-axis and nominal treatment visits. Negative and
uncertain-significance positions are assigned display conventions. Retrospective
positive NQ is shown at its reported upper bound when available; an unbounded
result is counted without a fabricated position. CIRCALL positive NQ results are
also counted without a numerical trajectory position; sensitivity never supplies
their y-coordinate. Only quantified retrospective
pairs are connected. Pooled positive NQ uses its separately configured assigned
level, without treating that position as a measured fraction or bound. Diagnosis
in CIRCALL/pooled views is an assumed reference, not measured MRD or blast-cell
percentage. No common calendar day is inferred from TP labels.

Blood-count files supply absolute recorded counts in confirmed units; fractions
do not reconstruct counts. Duplicate measured subject/day/measurement entries
fail. Retrospective grouping remains trimmed, case-sensitive surname grouping
within that count source alone, with the surname-collision limitation preserved.
No name-based join to inventory MRD is performed. Count formula caches without
results remain unavailable rather than acquiring a zero; measured counts require
a usable integer recorded day. Source date cells and coordinates remain in memory
for validation, without deriving new days or exporting clinical rows.

Counts have full recorded-range and early-window views, with the diagnostic
display selection applied explicitly. Tables retain all measured source days and
values. The early window does not globally exclude later observations. Log count
figures omit and count genuine zeros, and lines break at zeros; a linear-display
option retains them. No count baseline normalization or pseudocount is added.

## Results and validation

Locate the layer directory through [README](../results.md).
Available scopes contain:

```text
retrospective/
├── disease_modeling.xlsx
└── figures/{mrd,blood_counts}/
circall/
pooled/                 # Compatible MRD descriptions
comparisons/            # Separate-cohort blast figures and counts
```

Excel workbooks have Summary, Coverage, MRD, Counts, Models,
Diagnostics and Definitions tabs. Models explicitly states that modeling is
disabled. MRD/count patient denominators are separate and must not be summed into
a deduplicated global cohort. Pooled MRD has the retained fixed MRD population;
the count comparison workbook keeps cohort rows separate and contains no pooled
count statistic or inference.

Audit evidence contains aggregate reports, sanitized integrity findings, settings,
source/method/code/environment hashes, timestamps and artifact checksums. There
are no patient-level MRD/count tables, including hashed tables under `.audit`.
Completion validation reconstructs source observations in memory and reconciles
the aggregate reports, workbook contents and artifact hashes. Main figures are
PNGs and optional PDFs, with legends outside data and patient/measurement counts shown.

Use `tests/disease_modeling` and `tests/orchestration` with the
[central validation commands](../audit_guide.md#validation-commands).

The new suite tests the source/identity changes, values/bounds, cache availability,
repeat rules, count selection/zeros, source preservation, controls, independent
failures, privacy, standalone/master equivalence and execution with legacy workflow
directories physically absent. A synthetic numeric reference records original
method hashes and outcomes; it requires no old helpers at test or runtime.
Scientific validity and clinical equivalence across changed inputs/identities are
not established by software checks. Excel/PDF rendering limitations must be stated
in each acceptance record.

Code ownership and the [Layer 4 retained-file boundary](../replacement_coverage.md#active-execution-and-dependencies)
are maintained in the coverage map.

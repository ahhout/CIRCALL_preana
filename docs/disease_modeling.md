# Layer 4 disease tracking

`disease_modeling` independently prepares MRD and recorded blood-count trajectories
from explicitly selected sources. Its first release is descriptive: it has no
normalized model, regression, disease prediction or cross-modality patient linkage.
Scientific rules are in the [Layer 4 contract](workflow_contracts.md#layer-4-disease-tracking--october-6-2026)
and [versioned definitions](../configs/definitions/disease_modeling.json).
The [October 6 acceptance record](layer4_validation_20261006.md) gives exact commands,
verified current coverage, archival independence evidence and remaining limitations.

## Execution

Use the existing `pre_analysis` Conda environment, defined by
`environments/environment.yml` and its adjacent Linux lock.

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_disease_modeling.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_disease_modeling.json
```

Standalone equivalent of the shipped profile:

```bash
conda run -n pre_analysis python -m analysis.disease_modeling \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --circall input/inventaire_CIRCALL_05102026.xlsx \
  --blood-counts input/CIRCALL_wbc_blast_count_01102026.xlsx \
  --retrospective-blasts input/retrospective_blast_count_01102026.xlsx \
  --donors input/cfDNA_donors.xlsx --cohort all --analysis all \
  --blood-count-unit 'x10^9/L' --retrospective-blast-unit 'x10^9/L' \
  --include-controls --pool-mrd \
  --rules configs/definitions/data_integrity.json \
  --definitions configs/definitions/disease_modeling.json \
  --baseline-day-max 1 --baseline-selection latest --overlay-max-day 8 \
  --kinetics-y-scale log --mrd-negative-level 1e-8 --mrd-unknown-level 1e-6 \
  --mrd-positive-nq-level 1e-6 --retrospective-mrd-duplicate-policy worst \
  --jitter-seed 42
```

Omit `--output-dir` for a fresh timestamped run; explicit destinations must not
exist. `--cohort retrospective|circall` selects one cohort. `--analysis mrd|counts`
selects one disease component, with `all` as default. The count sources and their
explicit unit confirmation are required only when counts are selected. Each
selected cohort still requires its inventory for the whole-cohort integrity gate.
An omitted donor workbook is not selected implicitly. Controls are integrity-only;
`--no-include-controls` removes them from the gate. `--no-pool-mrd` disables pooled
MRD descriptions. The complete CLI is available with `--help`.

Validate-only inspects source structure, clinical annotations and cohort gates
without fitting, creating output folders or publishing. Definite errors return
nonzero with aggregate cohort status. Full execution can publish a blocked report
and complete an independent clean cohort before returning nonzero for quality.
An unavailable analysis in a valid source is a reported limitation, not an
execution failure. Source changes during a run prevent publication.

`./run_all_layers.sh` runs the combined `pipeline_layers.json` profile with one
manifest under `outputs/layered/`. A reported Layer 4 quality hold does not suppress
independent layers or retrospective disease reports in a full run. Blocked reports
are published and the final exit remains nonzero. Validate-only returns nonzero
for the hold without publishing anything; infrastructure preflight errors still
prevent execution. Individual-layer full commands remain available. See the
[unified run contract](workflow_contracts.md#unified-layered-orchestration--october-6-2026).

## Current CIRCALL source review

On the selected October 5 inventory, CIRCALL MRD fails the retained category
parser at `cohorte_lal!R2`. The source includes positive nonquantifiable annotations
outside the established CIRCALL category scope. The investigator explicitly chose
to keep CIRCALL blocked pending source review rather than introduce a new mapping.
No source cell or annotation was changed. With the shipped `analysis=all` profile,
the whole-cohort rule also prevents CIRCALL count publication; retrospective reports
remain available, while pooled MRD and joint count comparisons are not generated.
The blocked workbook's Summary identifies the clinical component and source cell.

## Sources and interpretation

Retrospective MRD reads `MRD_IgTCR` on TP1/TP2 bone marrow rows, keyed by recorded
`patient_id`. CIRCALL reads `MRD_TP1/TP2` metadata across patient records keyed
by `circall_id`, independently of sample visit/specimen/receipt. Neither population
requires a usable plasma sample or cfDNA measurement. The recorded-ID preparation
deliberately differs from the older retrospective surname-based MRD workflow.

Keep quantified fractions, negative results, missing/unknown source values,
unavailable formula caches, clinical uncertain significance and retrospective
positive nonquantifiable bounds distinct. Quantitative MRD zero is invalid under
the retained parser; it is not converted into a negative category. Retrospective
repeat priority and CIRCALL conflict failures remain explicit and recorded.

MRD plots use a log fraction y-axis and nominal treatment visits. Negative and
uncertain-significance positions are assigned display conventions. Retrospective
positive NQ is shown at its reported upper bound when available; an unbounded
result is counted without a fabricated position. Only quantified retrospective
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

```text
outputs/layer4_disease_modeling/run_<timestamp>/
├── retrospective/disease_modeling.xlsx
│   └── figures/{mrd,blood_counts}/
├── circall/
├── pooled/                 # Compatible MRD descriptions
├── comparisons/            # Separate-cohort blast figures and counts
└── .audit/workflows/04_disease_modeling/
```

Single-layer runs publish scope folders directly; mixed runs group them under
`04_disease_modeling/`. Excel workbooks have Summary, Coverage, MRD, Counts, Models,
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
PNG/PDF pairs, with legends outside data and patient/measurement counts shown.

```bash
conda run -n pre_analysis python -m pytest -q tests/disease_modeling tests/orchestration
```

The new suite tests the source/identity changes, values/bounds, cache availability,
repeat rules, count selection/zeros, source preservation, controls, independent
failures, privacy, standalone/master equivalence and execution with legacy workflow
directories physically absent. A synthetic numeric reference records original
method hashes and outcomes; it requires no old helpers at test or runtime.
Scientific validity and clinical equivalence across changed inputs/identities are
not established by software checks. Excel/PDF rendering limitations must be stated
in each acceptance record.

## Files to retain when archiving old workflows

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

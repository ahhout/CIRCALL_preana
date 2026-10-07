# Layer 2 sample statistics

Layer 2 describes inventory samples and received-sample measurements. It does not
run associations, tests, MRD or kinetics. Existing analysis profiles remain unchanged.

The [October 7 shared amendment](workflow_contracts.md#shared-sample-annotations-and-receipt-revision--october-7-2026)
defines current extraction (yes/no from DNA-ID presence) and canonical literal `na`.
The later [Layer 2 review amendment](workflow_contracts.md#layer-2-measurement-and-pooled-display-review--october-7-2026)
uses Received, Marked missing and Unassessed, with a separate overdue flag. Only
explicit `na` with applicable timing can become overdue; blank IDs remain
unassessed. Untimed rows show counts only. Historical acceptance
records retain their original source/rule hashes.
The scientific decision table in [workflow_contracts.md](workflow_contracts.md#layer-2-descriptive-statistics--october-6-2026)
is authoritative. Definitions are in `configs/definitions/sample_statistics.json`;
v1 accepts that approved definition set, not arbitrary new pooling policies.

## Execution

Use the existing `pre_analysis` Conda environment:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_sample_statistics.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_sample_statistics.json
```

Standalone equivalent:

```bash
conda run -n pre_analysis python -m analysis.sample_statistics \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --circall input/inventaire_CIRCALL_05102026.xlsx \
  --donors input/cfDNA_donors.xlsx
```

Both accept explicit fresh output destinations. Standalone supports `--cohort
retrospective|circall|all`, `--no-include-controls`, `--donors`, `--rules`, `--definitions` and
`--assessment-time` (ISO timestamp with explicit offset). Integrated settings use
the same hyphenated names inside workflow `options`; paths are profile-relative.
An omitted assessment timestamp is captured once during workflow execution.

Outputs default to `outputs/layer2_sample_statistics/run_<timestamp>/`, with
`{retrospective,circall,pooled}/statistics.xlsx` and PNG/PDF
figures. Pooled output exists only when both cohorts are selected. Excel tabs are
Summary, Receipt, Measurements, Availability, Definitions, CIRCALL Missed samples,
and optional Controls. Main counts show the overall total and specimen/visit
breakdown; do not add the total to its breakdown. Center and previous overlapping
views remain in native audit statistics JSON, under `tables.audit_detail`, and
are not exported as workbook rows. Measurement rows show metric/specimen/visit.

Layer 1 is executed against the actual selected sources. Definite errors block the
whole affected cohort, including its controls. Reports describing blocked outcomes
are still published, independent cohorts finish, and the final exit is nonzero.
A blocked workbook has reasons instead of zero-valued statistics. Preflight checks
configuration/provenance; it does not certify clean clinical data.

The audit retains source/rule/code/environment hashes, settings, raw-free integrity
findings, sanitized sample observations, aggregate tables, and artifact hashes.
Only the missed checklist contains approved patient pseudonyms; other observation
identity keys are hashed. Names, DOB, sample IDs and unrestricted notes are never
exported. Hidden audit folders remain sensitive local evidence, not access control.

## Identity preparation

The October 6 investigator revision supersedes the earlier RETRO-code proposal.
Use existing inclusion identifiers as `patient_id`. Preserve recorded IDs and
fill gaps by exact lastname–firstname–DOB tuples, using `unk-NNN-L-F` where no ID
exists. The correction helper accepts either the renamed header or `inclusion_id`
and renames the latter explicitly. It refuses open workbooks, existing destinations,
ambiguous mappings and incomplete identities; unaffected rows remain unchanged.

```bash
conda run -n pre_analysis python -m analysis.patient_ids \
  --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx \
  --output-dir archive/migrations/<fresh-patient-id-update> --adopt
```

Without `--adopt`, this produces a verified copy and backup without replacing the
input. Review `patient_id_report.json` for unfilled cells and pre-existing identity
variations. No name removal occurs in this correction or during statistics.
Existing inclusion IDs can identify the same patient across inconsistent demographic
annotations; Layer 2 preserves those recorded IDs rather than splitting them.

## Validation and limitations

```bash
conda run -n pre_analysis python -B -m unittest discover -s tests/sample_statistics -v
conda run -n pre_analysis python -B -m unittest discover -s tests/validation -v
conda run -n pre_analysis python -B -m unittest discover -s tests/orchestration -v
```

The tests use synthetic workbooks. They check deadlines and daylight-saving changes,
manual fallback, genuine zeros, formula caches, repeated samples, approved pooling,
controls, privacy, source preservation and independent failure handling. Source runs
and standalone/master comparisons are documented in the local acceptance record.
Excel is reopened and its values compared with audit tables. No Excel/LibreOffice
calculation engine is invoked; layout validation cannot substitute for opening the
workbook in Excel. Missing/stale caches are not repaired by Layer 2.

Single-layer runs expose the cohort folders directly alongside `.audit/`. Mixed
workflow runs retain the workflow directory. Existing top-level Layer 2 run folders
were flattened with unchanged report/figure bytes and rebuilt artifact indexes;
the relocation records are in `archive/migrations/flatten_layer2_20261006/`.

Retrospective controls are explicitly selected from `input/cfDNA_donors.xlsx`,
`Feuil1`, by both shipped layer profiles. `--no-include-controls` excludes both
cohorts' controls. Standalone runs require `--donors PATH` to select retrospective
controls; no input is guessed. The Controls tab and figures/controls directory
contain the supplied plasma DNA ng/mL endpoint using the existing donor mapping.
Controls never contribute to patient totals, missed lists, or pooled patient results.
Other donor measurements and protocol volumes are not inferred from formula constants.

Figures are grouped by specimen (`plasma/`, `CSF/`, `blood_pellet/`,
`bone_marrow/`) beneath `figures/`; control figures use the same specimen folders
beneath `figures/controls/`. Receipt-status plots stay at the corresponding figure
root. Filenames contain the metric and an assay suffix only when multiple assays
would otherwise collide. PNG/PDF pairs stay together; empty folders are not created.

Concentration plots (ng/µL and ng/mL) use base-10 logarithmic
y-axes with values displayed in their original units. Zero/nonpositive values are
counted on the figure but cannot be plotted; boxplots use positive values only.
Tables retain all observations, including genuine zeros, with no pseudocount.
Mass, volume, fraction and size plots retain linear axes. Subtitles use one rule for every measurement: specimen · Patient samples or
specimen · Controls. Internal DNA-type/group labels never appear in subtitles;
the concentration-scale change itself preserves stored values. The legacy assay key holds
DNA-type metadata, and not_recorded means the label was absent, not missing DNA.

The [October 7 Layer 2 review amendment](workflow_contracts.md#layer-2-measurement-and-pooled-display-review--october-7-2026)
excludes albumin/DIN from this layer and combines pooled cohorts into one box per
metric and nominal visit, with cohort-colored observations. cfDNA fragment size
is pooled separately within plasma and CSF at the shared visits. Other statistical
rules and source-integrity gates remain as previously defined. Worksheet selection
and content will be reviewed separately with the investigator.

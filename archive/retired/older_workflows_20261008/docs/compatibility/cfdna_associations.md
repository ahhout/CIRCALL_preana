# Compatibility diagnosis associations

This workflow compares **diagnostic cfDNA with diagnosis metadata**, separately
from longitudinal yield, MRD and kinetics. The explicit `pipeline_all.json` profile selects both
retrospective and CIRCALL inventories and adds compatible pooled descriptive views.

Use the [canonical compatibility guide](sample_analysis.md#run) for the combined
profile command.

Run just these associations with both explicitly selected inventories:

```bash
conda run -n pre_analysis python run.py --workflow cfdna_associations --circall input/inventaire_CIRCALL_01102026.xlsx
```

Omitting `--circall` retains the retrospective-only interface. The retrospective
source is hash-pinned in `configs/source_catalog.json`; `--inventory PATH` explicitly
overrides it and records the actual hash. A changed pin fails preflight clearly.
Neither loader chooses a workbook by modification time. Both input hashes and
executed code/settings are recorded; sources are never modified.

The [scientific contract](../workflow_contracts.md#diagnosis-associations-across-cohorts--october-1-2026)
contains all eight requested variable mappings, units, eligibility and pooling rules.
Only rows labelled `diag` contribute diagnosis measurements. Missing sex/age or
absolute-count sources are skipped; blood/marrow absolute blast counts are not
computed from percentages. In the legacy profile's source, five WBC patients
and no marrow-blast-percentage patients remain eligible at diagnosis. TP1 values
are not used to restore the earlier larger diagnostic dataset.

Outputs with both cohorts selected:

```text
cfdna_associations/
  diagnosis_availability.csv   # all eight variables, counts and reasons for skips
  diagnosis_settings.json     # units, source mappings and analysis scope
  retrospective/              # diagnosis views and selected tests
  circall/                    # diagnosis views and selected tests
  pooled/                     # comparable descriptive views, colored by cohort
```

Each cohort retains the peripheral-blast regression as its selected hypothesis
test, with HC3 uncertainty, effect size/CI and BH correction across selected tests.
`--predictors` changes the testing selection, not the scope of descriptive views.
Other available variables retain scatter plots/trends or categorical distributions
and summaries. `--no-pool-cohorts` disables pooled diagnosis views. The full and focused association profiles now confirm retrospective WBC as ×10⁹/L
using `retrospective-wbc-unit`, enabling the pooled WBC view. Without that explicit
unit setting, pooled WBC remains skipped. Absolute blast counts remain unavailable
and are not derived. Association folders and figure filenames explicitly distinguish peripheral blood
from bone marrow; see the output naming table below. Pooled outputs
have no hypothesis p-values; differing extraction protocols and cohort composition
still limit interpretation. Unavailable metadata have explicit coverage entries;
no borrowed follow-up measurements or invented numeric values are used.

All legends remain below the plotting area. Audit data and residual diagnostics
remain under `.audit/workflows/cfdna_associations/`; only reviewed aggregate tables
and main plots are published. Previous result folders are retained unchanged.

Use `tests/advanced_analysis`, `tests/cfdna_associations` and `tests/orchestration`
with the [central validation commands](../audit_guide.md#validation-commands).

The engine originated in `multivariate_analysis_retrospective` revision
`81f14d045c02410e587ed239d62c6588d841ae95`. Import hashes and its original snapshot
are recorded in `analysis/cfdna_associations/import_provenance.json`.
The earlier import comparison remains at
[archived comparison](../../archive/results/compatibility_20261007T073346593956Z/cfdna_migration_validation_20261001/comparison/comparison.json).

The following comparison documents the historical imported engine. It is not an
equivalence validator for the revised scientific plan and will detect intentional
model/output changes. Use the focused suites and source checks for current runs.
Historical comparison commands (fresh destinations only):

```bash
conda run -n pre_analysis python run.py --workflow cfdna_associations --output-dir output/new_associations_check
conda run -n pre_analysis python -B -m analysis.validation.validate_associations \
  --original ../multivariate_analysis_retrospective/analyze_blast_cfdna.py \
  --inventory input/cfDNA_inventaire_retrospective.xlsx \
  --integrated-run output/new_associations_check \
  --output-dir output/new_associations_comparison
```

The comparison checks membership, predictor observations, CSV values and missingness
without printing clinical rows. It writes original-engine results only to the
comparison destination. Numerical tolerances remain rtol=1e-10 and atol=1e-12.

## Tissue-explicit association filenames

New runs use these folders within each available cohort scope:

| Comparison | Folder | Figure |
| --- | --- | --- |
| Peripheral blood WBC | `cfDNA_vs_peripheral_blood_wbc_count/` | `log10_cfDNA_ng_per_mL_vs_peripheral_blood_wbc_count.png` |
| Peripheral blood blast percentage | `cfDNA_vs_peripheral_blood_blast_percent/` | `log10_cfDNA_ng_per_mL_vs_peripheral_blood_blast_percent.png` |
| Bone marrow blast percentage | `cfDNA_vs_bone_marrow_blast_percent/` | `log10_cfDNA_ng_per_mL_vs_bone_marrow_blast_percent.png` |

This naming-only change leaves CLI/config predictor names (`gb_per_l`,
`peripheral_blast_percent`, `tumor_fraction_percent`) and all calculations intact.
Predictor metadata records the figure name for validation and publication;
historical runs retain their original filenames and metadata.

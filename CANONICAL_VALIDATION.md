# Canonical workflow validation

The canonical workflow now uses the revised root-level source workbooks, the unadjusted total-DNA/plasma-volume endpoint, and pooled existing/pediatric controls. The legacy workflow remains available with its preserved source inputs and calculations.

## Implementation checkpoints

| Commit | Change |
| --- | --- |
| `300ff9f` | Explicit source adapters, compartment preparation, and measurement-level QC |
| `b8f6016` | Shared cohort policies and statistical calculations |
| `43ee4ff` | Canonical CLI, reports, and explicit legacy mode |

The subsequent default-switch commit enables canonical mode and documents the validated behaviour. Raw inputs and generated results remain outside Git.

## Completed checks

The full canonical workflow completed for both patient cohorts. A complete run was also exercised from `/tmp`, with absolute runner/output paths and repository-relative default inputs. The release outputs are retained locally under `outputs/canonical_validation/release_final/`.

The unit suite passed 34 tests covering numeric conversion, blank-input formula zeros, genuine measured zeros, missing volume, arithmetic conflicts, wide-to-long preparation, MNC/plasma separation, patient namespaces, source-header validation, control pooling, eligibility, statistical equivalence, CLI modes, output reuse, failed stages, and missing/unsupported analyses.

Independent source-cell validation checked 374 prepared plasma/control records. It verified all five corrected reference samples, exclusion of the thirteen identified CIRCALL formula-zero records from concentration analyses, and 514 retrospective MNC records without copied plasma volumes. No genuine numerical holds were found in the revised sources. The pooled measured control group contains nine existing donors and four pediatric controls; two additional pediatric controls remain undosed.

Both patient-cohort MixedLM result tables contain finite contrasts and use the same thirteen controls. Cohorts are fitted separately. Source file hashes match the snapshot taken before implementation.

## Equivalence and intentional changes

Legacy mode reproduced all ten table files, including eleven workbook sheets, and all 29 images from the preserved baseline; image pixels matched exactly. Its only required path adjustment was following the previously moved local data directories.

On identical prepared records, 40 defined correlation result rows matched the legacy calculations at their original two-decimal export precision. Fifteen groups that previously returned undefined correlations are now explicitly labelled unavailable because their inputs are constant. Synthetic sample-level Welch, patient-median Welch, and Mann–Whitney results matched the legacy routines exactly.

Canonical results intentionally differ from legacy outputs because they use the revised source versions, unadjusted DNA quantities, pooled controls, and corrected measurement missingness. The current sources have 246 comparable plasma records whose unadjusted and percentage-adjusted endpoints differ. This is a within-source measurement-basis comparison, not an assertion that 246 samples changed between file versions.

Each canonical run writes `prepared/reconciliation.json`, `prepared/endpoint_basis.csv`, measurement-availability and eligibility tables, and the input/code hashes. These explain the changes without silently repairing source workbooks.

## Sensitivity and availability

A dedicated run with `--mixed-outlier-drop-n 2 --mixed-random-slope-sensitivity` completed. Outlier-drop refits completed for both cohorts; retrospective random-slope sensitivity completed. CIRCALL random-slope sensitivity is explicitly unavailable because a numeric mapping between day and TP labels has not been agreed. Actual CIRCALL MRD measurements are not mapped, so MRD annotations are also explicitly unavailable; assay-availability columns are not interpreted as results.

The statistical logs contain model-boundary/singular-covariance and small-bin warnings. Fits that fail to converge or produce nonfinite primary contrasts fail the analysis; these are not reclassified as unsupported data. The present runs completed with finite primary contrasts. Users should still inspect the paired counts and diagnostics, particularly sparsely sampled timepoints.

## Visual and artifact checks

The release run produced 26 CSV files, five Excel workbooks, and 46 figures. Representative subtype and concentration-distribution figures were visually inspected. Figures use readable shared axes and source-labelled cohort panels; logarithmic transformations remain question-specific. Raw genetic-subtype spellings remain available, while case-only variants share display colours.

Local evidence:

- `outputs/canonical_validation/tests_final.log`
- `outputs/canonical_validation/release_final/validation.json`
- `outputs/canonical_validation/release_final/run_manifest.json`
- `outputs/canonical_validation/legacy_comparison.json`
- `outputs/canonical_validation/shared_correlation_comparison.json`
- `outputs/canonical_validation/sensitivity/analysis_status.csv`

Validation scripts use local clinical data only for integration checks; unit tests use synthetic inputs. No original source workbook was edited, no original project was deleted, and no remote was configured or published. Rollback remains `python run.py --workflow legacy`.

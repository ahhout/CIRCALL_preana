# Layer 1 acceptance — October 5, 2026

Historical evidence for the recorded sources and settings.

## Acceptance run — October 5, 2026

Historical evidence: the commands and counts below describe the source/rule hashes
at acceptance, not the current profiles. Four referenced result/verification paths
are absent locally, as also recorded by the [archival audit](archival_audit.md#completed-archival-on-october-7).
Their original paths are retained below as unresolved evidence references, not
links to substitute runs. The relocation records alone do not restore those files.

Implemented Layer 1 was run on both adopted workbooks, including CIRCALL controls.
The 28 validation tests and 35 orchestration tests passed (63 total). The validation
suite includes 17 Layer 1 tests. Orchestration tests emitted a Matplotlib cache
fallback warning; no additional dependency installation was needed.

Commands actually run at the original locations (subsequently relocated below):

```bash
conda run -n pre_analysis python -m unittest discover -s tests/validation -v
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -v
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --output-dir output/layer1_integrity_20261005
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --circall input/inventaire_CIRCALL_05102026.xlsx --cohort all --output-dir output/layer1_integrity_standalone_20261005
conda run -n pre_analysis python output/layer1_integrity_validation_20261005/verify.py --root . --integrated output/layer1_integrity_20261005 --standalone output/layer1_integrity_standalone_20261005 --output output/layer1_integrity_validation_20261005/verification.json
```

Both full inspections returned the intended exit code 1 for definite source errors
after publishing both cohort reports. Retrospective: 0 errors and 103 review
occurrences across 61 affected rows. CIRCALL: 404 error and 2 review occurrences
across 140 affected rows, all on the patient sheet. These are rule occurrences,
not patient counts; multiple findings can refer to the same cell or sample.

The historical verification record at
`outputs/layer1_data_integrity/validation/verification_20261005/verification.json`
recorded identical standalone/integrated findings and Excel tab values, 20 artifact
hashes, four visible/native publication pairs, unchanged input hashes and matching
executed code hashes. The reports were published under
`outputs/layer1_data_integrity/run_20261005/01_data_integrity/` before flattening;
the named run is now absent locally.
The real workbooks were never saved or recalculated. The other scientific
workflows were not rerun; they still require separate migration to the new schema.

At the investigator's request, the accepted run, standalone comparison run and
verification evidence were relocated under `outputs/layer1_data_integrity/`.
All file hashes were preserved. Historical manifests retain their execution-time
paths; use the [relocation record](../../archive/migrations/layer1_output_location_20261005/relocation.json)
to resolve them. The output-default change is covered by the additional targeted
default/override test; it does not change the historical run's issue counts.

## Extraction-state and contextual reporting acceptance — October 5, 2026

Following the approved source correction, 51 explicit not-extracted notes now live
in `extraction_status`; incompatible text fields were cleared. The 13 numeric
contradictions were preserved and independently compared with the archived source.
All four active/archive source hashes match the correction relocation record.

The reporting revision retains future-row formula errors, classifies extraction
contradictions as logic errors, recognizes explicit unknowns, and distinguishes
workflow notes, aliquot-count annotations and written-unit measurements. Summary
shows rule occurrences separately from distinct cells and rows. The grouped Issues
tab adds categories/context without changing the fewer-than-ten reference rule.

Validation performed:

```bash
conda run -n pre_analysis python -m unittest discover -s tests/validation -q
conda run -n pre_analysis python -m unittest discover -s tests/orchestration -q
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --output-dir outputs/layer1_data_integrity/run_20261005_logic_review
conda run -n pre_analysis python -m analysis.data_integrity --inventory input/cfDNA_inventaire_retrospective_05102026.xlsx --circall input/inventaire_CIRCALL_05102026.xlsx --cohort all --output-dir outputs/layer1_data_integrity/validation/logic_review_standalone_20261005
conda run -n pre_analysis python outputs/layer1_data_integrity/validation/verification_20261005/verify.py --root . --integrated outputs/layer1_data_integrity/run_20261005_logic_review --standalone outputs/layer1_data_integrity/validation/logic_review_standalone_20261005 --output outputs/layer1_data_integrity/validation/logic_review_verification_20261005.json
```

All 34 validation and 35 orchestration tests passed (69 total). Both inspections
published both reports and returned the expected exit code 1 for source errors.
Retrospective: 13 error occurrences on 13 distinct cells/rows, plus 13 review
occurrences. CIRCALL: 404 error occurrences on 403 distinct cells across 138 rows,
plus two review occurrences. These counts describe the corrected source versions.

The historical verification record at
`outputs/layer1_data_integrity/validation/logic_review_verification_20261005.json`
recorded identical standalone/master findings and Excel tab values, 20 artifact
hashes, four publication pairs and current source/rule/code hashes. Reports were published under
`outputs/layer1_data_integrity/run_20261005_logic_review/01_data_integrity/`;
that path is now absent locally. Previous reports were retained at acceptance. Excel was checked programmatically; visual
rendering was unavailable. No scientific models were run.

The investigator requested flattening of the historical `run_20261005` visible
cohort folders. The [migration record](../../archive/migrations/flatten_layer1_20261006/relocation.json)
records unchanged report bytes; the current layout is in README.

Retrospective controls were added on October 6. Their findings remain within the
retrospective report, distinguished by source workbook and sheet. The sparse donor
schema requires Donor and the supplied plasma ng/mL endpoint rather than patient
inventory columns. Numeric/reference/cache checks apply; fixed-volume conversions
lack independent protocol metadata, so those arithmetic checks remain unavailable.

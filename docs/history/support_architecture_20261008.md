# Supporting architecture consolidation — October 8, 2026

The investigator approved the supporting-architecture audit recommendations and
specified one pipeline as the eventual repository architecture, preserving current
layered output. This change centralizes selection and organizes supporting files;
it does not retire scientific capabilities or change clinical sources/settings.

## Preservation and rollback

The dirty working state, including relevant untracked implementation and tests,
was preserved before editing in
`archive/migrations/support_architecture_before_20261008T072011Z/`.
`implementation.tar.gz` contains 210 scoped files; `snapshot.json` records their
hashes, Git HEAD and initial status. Clinical inputs, outputs, caches and credentials
are excluded. Nothing was staged or committed for this change.

Rollback must review later edits and restore only the affected files from that
snapshot. Restore moved files to their recorded paths; review newly added files
separately. Do not reset the working tree or overwrite clinical data/results.

## Final ownership and relocations

| Before | Current owner / retained interface |
| --- | --- |
| Combined plus four copied layered profiles | `configs/pipeline_layers.json` owns shared sources/defaults and layer options. Four single-layer files and the dated combined filename are references. |
| Five root compatibility profiles | Authoritative profiles in `configs/compatibility/`; root names remain references. Relative paths were adjusted, with resolved source/options equality checked. |
| `configs/definitions/{sample_annotations,workbook_harmonization}.json` | `configs/maintenance/`, exact file bytes preserved; active tool defaults/tests updated. |
| Four current layer guides at `docs/` root | `docs/layers/`; association compatibility instructions split into `docs/compatibility/cfdna_associations.md`. |
| Canonical, normalized-kinetics and older statistical-question guides | `docs/compatibility/`; current questions are explained in `docs/results.md`. |
| Cleanup, archival audit, Layer 3/4 acceptance and Layer 4 original plan | `docs/history/`, preserving executed commands and updating Markdown links. |
| Historical sections embedded in integrity/audit guides | `docs/history/layer1_validation_20261005.md` and `integration_validation_20261001.md`. |
| Cross-test fixture imports | Shared synthetic builders under `tests/fixtures/`. No test imports another `test_*.py` module. |
| Six result-validator implementations in `tests/validation/` | `analysis/validation/`; original `python -m tests.validation.<name>` commands remain forwarding interfaces. |
| Integrity and workbook-maintenance tests in `tests/validation/` | `tests/data_integrity/` and `tests/maintenance/`; validator unit tests remain in `tests/validation/`. |

The four scientific packages and older scientific package paths remain intact.
Normalized-kinetics YAML, extraction protocols and the older association source pin
retain their existing paths; their compatibility-only role is documented. Workbook
maintenance commands remain explicit. Existing inputs and result directories were
not moved, deleted or overwritten.

## Configuration and output checks

The new master was resolved and compared with the saved pre-change configuration.
Every previous engine option and source path matched exactly; the only added
transport option carries the same existing Layer 3 comparison matrix. The five
compatibility profiles also retained identical resolved options and source paths.
Both moved maintenance definitions retained their exact SHA-256 hashes. The four
scientific definition files also retained their pre-change hashes, and AST checks
confirmed every extracted synthetic fixture function body was unchanged.

Synthetic before/after integrated runs covered all four layers, using the same
explicit synthetic sources, fixed Layer 2 assessment time, scientific definitions
and PNG-only figure choice. The before run used pre-change code. The after run
used the resolved engine options plus the master's unchanged comparison switches.
These version-1 execution profiles isolate engine-output equivalence from master
resolution, which was checked separately. This is not a new full clinical run.

Commands actually executed from the repository root:

```bash
conda run --no-capture-output -n pre_analysis python -B run.py --config /tmp/pre_analysis_architecture_n5y5wghb/baseline.json --output-dir /tmp/pre_analysis_architecture_n5y5wghb/before --validate-only
conda run --no-capture-output -n pre_analysis python -B run.py --config /tmp/pre_analysis_architecture_n5y5wghb/baseline.json --output-dir /tmp/pre_analysis_architecture_n5y5wghb/before
MPLCONFIGDIR=/tmp/pre_analysis_architecture_n5y5wghb/mpl conda run --no-capture-output -n pre_analysis python -B run.py --config /tmp/pre_analysis_architecture_n5y5wghb/after.json --output-dir /tmp/pre_analysis_architecture_n5y5wghb/after --validate-only
MPLCONFIGDIR=/tmp/pre_analysis_architecture_n5y5wghb/mpl conda run --no-capture-output -n pre_analysis python -B run.py --config /tmp/pre_analysis_architecture_n5y5wghb/after.json --output-dir /tmp/pre_analysis_architecture_n5y5wghb/after
conda run --no-capture-output -n pre_analysis python -B /tmp/pre_analysis_architecture_n5y5wghb/compare_outputs.py --before /tmp/pre_analysis_architecture_n5y5wghb/before --after /tmp/pre_analysis_architecture_n5y5wghb/after --report /tmp/pre_analysis_architecture_n5y5wghb/comparison.json
./run_all_layers.sh --validate-only
```

Both synthetic runs completed. Comparison found 12 identical workbook contents
apart from creation timestamps, 36 byte-identical published PNGs, and 30 equal
native JSON evidence files. Published filename sets matched and both artifact
indexes verified. Execution manifests intentionally differ in code/configuration
provenance and timestamps. Matplotlib runtime cache files are not analytical
evidence and were excluded. No PDF parity claim is made for these PNG-only runs;
format-selection tests exercise both choices.

The real-source schema-2 preflight returned the expected exit 1 for blocked disease
cohorts without publishing a run. The CIRCALL hold was not bypassed.

## Software verification

The portable suite was run with:

```bash
MPLCONFIGDIR=/tmp/pre_analysis_architecture_n5y5wghb/mpl conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests --ignore=tests/blast_kinetics/test_workbook_integration.py
```

Initial failures exposed two relocation omissions: the new configuration module
was absent from Layer 4's explicit code inventory, and a shared compatibility
fixture lacked its original `PRIMARY` import. Both were corrected. The targeted
configuration/isolation rerun passed 16 tests, including a real schema-2 synthetic
execution recording both the selected reference and master in provenance.
The final portable suite passed **507 tests and 123 subtests** in 282.33 seconds.
Two existing Matplotlib `vert` deprecation warnings came from the compatibility
statistical-plot tests. The clinical-workbook integration test was explicitly
excluded as shown in the command; no full clinical execution was performed.

All six current validator commands and their six historical forwarding commands
were invoked with `--help` in the same environment. The documentation link check
allows only the two already-absent historical Layer 3/4 aggregate verification
JSONs, now explicitly labeled in their acceptance records. No replacement baseline
was inferred from another output folder.

Synthetic run directories above are temporary validation artifacts. A small
comparison record and helper are retained under
`archive/migrations/support_architecture_validation_20261008/`; the durable
pre-change implementation snapshot is the rollback reference. Software and
synthetic parity checks do not establish clinical scientific validity.

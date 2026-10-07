# Repository cleanup — October 1, 2026

This is a historical migration record. Its environment commands retain the paths
used at that time; current setup uses `environments/environment.yml` and
`environments/conda-linux-64.lock`, as documented in the [README](../README.md).

The investigator requested removal of obsolete legacy/archive material and
environment consolidation. Active scientific preparation, source selection,
identifiers, profiles, pooling, thresholds, models and corrections are preserved.

## Removed material and retained evidence

The retired `analysis/historical_workflows/` runner and its dedicated tests,
legacy-only output comparator, and two redundant environment definitions/locks
were removed. `--workflow legacy`, legacy JSON selection, `--stage`, and
`--retrospective-workbook` are no longer supported; active CLI flags remain.
Six superseded migration/design/usage documents were consolidated into current
guides. Their complete contents remain in the cleanup snapshot.
Ten unused scripts under `blast_kinetics_workflow/archive/legacy_scripts/` were
preserved in `kinetics-legacy-code.tar.gz` beside that snapshot, then removed.
Archived outputs lost only 216 disposable font-cache files/tags (7,943,040 bytes);
their paths and sizes are recorded in `discarded-caches.json` beside the snapshot.

Synthetic Welch and Mann–Whitney results were captured from the retired engine
before removal in `tests/fixtures/synthetic_statistics_reference.json`.
The current statistics regression test checks this fixed reference without importing
retired code. It contains only synthetic data.

`archive/input/`, `archive/output/`, migration snapshots, previous results and
the explicit kinetics workbook at `blast_kinetics_workflow/data/` remain local.
These preserve source provenance, validated evidence and rollback; they are not
obsolete executable workflows. Original association import hashes remain in
`analysis/cfdna_associations/import_provenance.json`.

Earlier validation evidence remains at `archive/output/canonical_validation/`,
`output/cfdna_migration_validation_20261001/`, and
`output/layout_validation_20261001T094022Z/`. Counts and outcomes recorded there
describe those historical runs, rather than tests performed for this cleanup.

## Shared Conda environment

All active workflows and their workers use `pre_analysis`. Every workflow records
the shared lock hash and actual package versions. The existing canonical explicit
lock is retained in full, with 12 package builds added from the installed kinetics
lock: Seaborn, PyYAML, pytest and their missing dependencies. Numerical-library
builds already present in `pre_analysis` are unchanged. The YAML now includes the
three direct requirements and uses conda-forge, matching the explicit package URLs.

Dependency constraints for all 155 combined packages were checked with Conda
`MatchSpec`; there were no conflicts. No new online package resolution was used
to construct the lock. A cached exploratory solver dry run would have updated
OpenSSL/certificates; those unrelated updates were excluded from the explicit lock.

Install the reviewed package set into an existing environment:

```bash
conda install --offline -n pre_analysis --file environments/pre_analysis/conda-linux-64.lock
```

On another machine without cached packages, omit `--offline`. If the environment
is absent, use `conda create -n pre_analysis --file environments/pre_analysis/conda-linux-64.lock`.
The old installed `multivariate_analysis` and `kinetics_pipeline` environments are
retained; they are no longer required by this repository and may serve other projects.

After installation, export the actual lock with:

```bash
conda list -n pre_analysis --explicit
```

Compare this export to the reviewed lock before updating the file. YAML resolution
with `conda env create -f environments/pre_analysis/environment.yml` can choose
different versions; prefer the explicit lock for reproducibility.

## Snapshot and rollback

The pre-cleanup dirty tree is preserved in
`.maintenance/cleanup_20261001T100451Z/before.tar.gz`, with 113 code/configuration/
documentation files, their SHA-256 hashes, Git status and the tracked diff.
Clinical inputs, outputs, credentials and caches are excluded. Its recorded HEAD
is `ae3e34519c46deb1475c8f51a34ec8cada3333e5`; HEAD alone cannot restore the
pre-existing untracked migration work. `.maintenance/` is Git-ignored.

Restore only cleanup-owned files after checking saved after hashes against the
current files, and preserve later edits. The previous environment definition and
lock are in that snapshot. Do not reset or clean the entire working tree.
This code snapshot does not replace a backup of clinical inputs or results.

## Verification

The actual `conda list -n pre_analysis --explicit` export matches all 155 reviewed
package URLs. Installation used the offline command above with `-y`; only the
12 additions were installed. Both retired environments remain installed.

```bash
conda run --no-capture-output -n pre_analysis python -m pytest -q tests
conda run --no-capture-output -n pre_analysis python -m pytest -q tests/validation
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_all.json --output-dir output/environment_cleanup_20261001T100451Z --validate-only
conda run --no-capture-output -n pre_analysis python run.py --config configs/pipeline_all.json --output-dir output/environment_cleanup_20261001T100451Z
conda run --no-capture-output -n pre_analysis python -m tests.validation.compare_integrated --standalone-dir output/layout_validation_20261001T094022Z/final --integrated-run output/environment_cleanup_20261001T100451Z --report output/environment_cleanup_20261001T100451Z_comparison_final.json
conda run --no-capture-output -n pre_analysis python -m tests.validation.validate_canonical --run-dir output/environment_cleanup_20261001T100451Z --output output/environment_cleanup_20261001T100451Z_source_validation.json
```

The full suite passed 147 tests, including three local-workbook kinetics checks,
with existing model-boundary/deprecation warnings. After adding backward
compatibility for unused legacy CLI fields in old canonical manifests, all seven
validation-tool tests passed. The comparator ignores only null `stage` and
`retrospective_workbook` fields; nonnull values still cause a settings mismatch.
All three workflows passed preflight, completed, and recorded the shared
environment/lock in both preflight and execution provenance.

The [source-cell report](../archive/results/compatibility_20261007T073346593956Z/environment_cleanup_20261001T100451Z_source_validation.json)
passed for 401 endpoints and verified unchanged sources. The
[strict reference comparison](../archive/results/compatibility_20261007T073346593956Z/environment_cleanup_20261001T100451Z_comparison_final.json)
matched all scientific settings/input hashes, 74 table/workbook files, 53 worksheets,
102 images and the kinetics model summary. Two PDFs were present and nonempty.
The strict comparison returned failure because one association diagnostic image,
`cfDNA_genetic_subtype/assumptions/scale_location.png`, differs: width 2007 pixels
versus 2004 previously. All 19 association CSVs, including assumption-test results,
matched the established numeric tolerance and missingness rules; no output files
were missing or added.

An aggregate diagnostic check found four observations with near-unit leverage.
Standardized residuals divide by `sqrt(1 - leverage)` and are sensitive to
floating-point differences here. The fitted maximum absolute residual differed
only at approximately 1e-15 across the old and shared environments, but the
standardized-residual range changed. This explains why exact diagnostic-image
reproduction remains unsupported after consolidation. No scientific handling,
filtering, or diagnostic calculation was changed to force a match.

Python syntax and Markdown link targets were checked; `git diff --check` passed.
Software regression tests and numerical comparisons do not establish scientific
validity or interchangeability of the workflows' sources and endpoints.

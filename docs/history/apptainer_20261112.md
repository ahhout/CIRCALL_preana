# Apptainer acceptance — November 12, 2026

The optional Apptainer packaging built and completed all four layers using five
synthetic workbooks, the unchanged Linux Conda lock and four local Arial styles.
Clinical workbooks were not used in these images. Their deidentification remains
deferred in the [README to-do list](../../README.md#to-do).

## Implementation and rollback

`Apptainer.def` pins the Miniforge OCI base; the standard-library packaging helper
selects exact source bytes, keeps scientific options, records hashes, refuses
existing destinations and builds a read-only SIF. Runtime commands retain the
existing `run.py` launcher and clinical gates. Use the
[current commands](../../README.md#container-build-linux-x86-64).

Pre-change HEAD was `e02f8eb8514119a06f81f02dda6974c59873771a`, with uncommitted
Docker packaging work. A scoped code-only snapshot preserves those edits in
`.maintenance/apptainer_setup_20261112/before_code.tar.gz`; `prechange.json` lists
its files. No clinical data, credentials or results entered that snapshot.
The earlier Docker recipe/ignore files remain labelled drafts and are unused by
Apptainer. No image or code changes from this task were published.

## Executed checks

Host environment: `/home/arnohoutman/miniconda3/envs/pre_analysis`; container
runtime: Apptainer 1.5.5 in Ubuntu-24.04 WSL2, Linux x86-64.

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/orchestration/test_container_build.py tests/orchestration/test_launcher.py tests/orchestration/test_master_configuration.py
```

34 host tests passed. After the generated master was renamed to avoid the
reserved `pipeline_*.json` reference naming pattern, all four packaging tests
passed again. All 30 launcher/master tests then passed inside the corrected SIF.
The first in-image run had 29 passes and one profile-naming failure; the failed
image/log and corrected image/log remain local evidence.

The default subordinate-ID fakeroot build failed before project execution with
`failed to mount binfmt_misc filesystem: invalid argument`. A public Alpine probe
and the complete recipe succeeded with `--root-mapped-build`, which passes
`--ignore-subuid --ignore-fakeroot-command` to Apptainer without changing host
configuration. Both full root-mapped image builds ran the four-style Arial check
successfully.

Synthetic inputs were generated solely from `tests.fixtures.advanced_analysis`
and `tests.disease_modeling.fixtures`, adding internally consistent DNA/cfDNA
measurements, diagnostic and MRD visits, and a fixed Layer 2 assessment timestamp
of `2026-10-20T12:00:00+00:00`. The five selected source hashes were checked against
the generated workbook files. This is a software fixture, not a clinical cohort.

```bash
python3 run.py --config .maintenance/apptainer_setup_20261112/synthetic_master.json --validate-only
python3 run.py --config .maintenance/apptainer_setup_20261112/synthetic_master.json --output-dir outputs/layered/apptainer_host_smoke_20261112
python3 environments/container/build.py --config .maintenance/apptainer_setup_20261112/synthetic_master.json --arial-dir /usr/share/fonts/truetype/msttcorefonts --context .maintenance/apptainer_setup_20261112/context_verified --image .maintenance/apptainer_setup_20261112/circall-synthetic-verified.sif --root-mapped-build
apptainer run --cleanenv --containall .maintenance/apptainer_setup_20261112/circall-synthetic-verified.sif
apptainer run --cleanenv --containall --bind "$PWD/outputs/container:/app/outputs" .maintenance/apptainer_setup_20261112/circall-synthetic-verified.sif --output-dir outputs/apptainer_verified_20261112
apptainer exec --cleanenv --containall --pwd /app .maintenance/apptainer_setup_20261112/circall-synthetic-verified.sif /opt/conda/envs/pre_analysis/bin/python -B -m pytest -q -p no:cacheprovider tests/orchestration/test_launcher.py tests/orchestration/test_master_configuration.py
```

Host and corrected container preflight/execution returned zero. Each of the four
layers was complete with `quality_status: no_issues_detected` in both runs.
Each artifact index contains 432 artifacts and 129 publications. The local
comparison verified their hashes, unchanged inputs, executed code/contract/lock
hashes, Layer 3 export privacy and Layer 4 aggregate-only privacy/reconciliation.
All 30 native JSON evidence files and all 12 workbook cell sets matched after
normalising the explicit host/container packaging paths. All 249 checked native
PNG files matched pixel-for-pixel. No numerical tolerance or scientific setting
change was needed. Constant synthetic predictors produced the same statsmodels
warnings on host and container; runs completed normally.

The corrected SIF SHA-256 is `1cf2437d6335690056047941973879319360426a39a45cb2d9b5bfa7985eef53`.

## Evidence and limits

`.maintenance/apptainer_setup_20261112/` retains `make_sources.py`, the explicit
synthetic master, source files, build contexts/results, logs, `commands.json`,
`compare.py`, `comparison.json` and `verification.json`. It is Git-ignored.
The comparison ran inside the SIF with the host checkout mounted read-only for
source reconciliation, plus the evidence directory writable for its report:

```bash
apptainer exec --cleanenv --containall --env PYTHONPATH=/app --bind "$PWD:$PWD:ro" --bind "$PWD/.maintenance/apptainer_setup_20261112:/evidence" --pwd /app .maintenance/apptainer_setup_20261112/circall-synthetic-verified.sif /opt/conda/envs/pre_analysis/bin/python -B /evidence/compare.py
```

The actual smoke execution mounted only its output parent. Host paths were
available only during the later read-only comparison. No PDF export or visual
Excel rendering was performed. These checks establish synthetic software parity;
they do not certify clinical anonymity or clinical/scientific validity. No clinical
image has been built or published. Fonts and images remain local/Git-ignored.

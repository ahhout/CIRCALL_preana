# Default working inputs and private image — November 16, 2026

The default master now selects the five accepted pseudonymised workbooks. The
usual `python3 run.py` launcher completed all four layers, and a private Apptainer
image reproduced its numerical reports, workbooks and PNGs. The image remains
local; no clinical data, mapping, image or output was published to GitHub.
Sharing review remains open because exact dates and approved IDs/initials remain.

## Scope and checkpoint

Code/configuration/documentation was reviewed and pushed in `5c9f7b3` before the
image build. Only the five source paths changed in the default master; scientific
options/definitions, seeds, four-layer selection and clinical gates were retained.
The preservation helper's critical checks now raise explicit errors rather than
relying on optimisation-sensitive Python assertions, with a synthetic regression
that rejects an unintended measurement edit before output publication.

The clean pre-change HEAD was `90954b1`, with the preceding deidentification work
still local. The scoped code/config/docs snapshot and file inventory are under
`.maintenance/default_input_adoption_20261116/`; they contain no data, credentials
or outputs. The authoritative originals and private group map were preserved.
A separate protected original-source master supports future maintenance without
feeding the already aliased default copies back through the deidentifier.

## Executed checks

Host environment: existing `pre_analysis` Conda environment; runtime: Apptainer
1.5.5 on Ubuntu-24.04 WSL2, Linux x86-64. No dependency/lock change was needed.

```bash
python3 run.py --validate-only
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/test_deidentification.py tests/orchestration/test_container_build.py tests/orchestration/test_launcher.py tests/orchestration/test_master_configuration.py
python3 run.py --output-dir outputs/layered/pseudonymised_default_20261116
python3 environments/container/build.py --config configs/pipeline_layers.json --arial-dir /usr/share/fonts/truetype/msttcorefonts --context .maintenance/private_clinical_image_20261116/context --image .maintenance/private_clinical_image_20261116/circall-preana-private.sif --root-mapped-build
apptainer run --cleanenv --containall .maintenance/private_clinical_image_20261116/circall-preana-private.sif
apptainer exec --cleanenv --containall --pwd /app .maintenance/private_clinical_image_20261116/circall-preana-private.sif /opt/conda/envs/pre_analysis/bin/python -B -m pytest -q -p no:cacheprovider tests/test_deidentification.py tests/orchestration/test_launcher.py tests/orchestration/test_master_configuration.py
```

The host default preflight passed, and 39 focused host tests passed in 28.73 s.
The clean image built from `5c9f7b3f8caa005ab944ec9787013cbc71095f84`; its
metadata records `code_dirty: false`. The four-style Arial build check passed.
The embedded-profile preflight passed without host input/configuration mounts,
and 35 in-image tests passed in 35.71 s.

The host's actual Layer 2 assessment timestamp was read from its native manifest.
A private validation master differed from the embedded master only by that
explicit timestamp option. It was mounted read-only for the full image smoke run:

```bash
apptainer run --cleanenv --containall \
  --bind "$PWD/.maintenance/private_clinical_image_20261116/validation_master.json:/app/configs/container_master.json:ro" \
  --bind "$PWD/.maintenance/private_clinical_image_20261116/outputs:/app/outputs" \
  .maintenance/private_clinical_image_20261116/circall-preana-private.sif --output-dir outputs/smoke
```

The image's persistent/default configuration was not frozen or edited. Its normal
runs still assess receipt at current time; build and runtime configuration hashes
and the replayed timestamp are retained separately in `runtime_override.json`.
Only outputs and the explicit validation configuration were mounted during this
execution. Original workbooks and the private group map were never mounted.

| Check | Result |
| --- | --- |
| Full host/image execution | Both complete; four complete layers with the same `review_needed` flags |
| Embedded data | Exactly five workbook files; all hashes match the accepted copies; no originals or private group map included |
| Embedded build files | 178 recorded hashes checked; recipe checked at Apptainer's stored `/.singularity.d/Singularity` location |
| Numerical evidence | All 30 native JSON files identical after filesystem-path normalization only; no data-hash substitution or numeric tolerance |
| Workbooks | All 12 native result workbook cell sets identical |
| Figures | All 285 checked native PNGs pixel-identical |
| Publication/index | 489 artifact hashes and 150 publication mappings verified in each run |
| Privacy/source checks | Source reconciliation and clinical export scans passed; retained documented public-label false positive only |
| Private access | Build workspace 0700; completed SIF 0600; validation did not change the image hash |

The SIF SHA-256 is
`98128d38f92bef226aa4ddbad6d25ca4d56e3e326656e37c8d928566aa920c03`.
Its local path is
`.maintenance/private_clinical_image_20261116/circall-preana-private.sif`.
It contains the approved working data and licensed local fonts and must remain
private pending the separate sharing review. It was not uploaded to a registry.

## Audit scope and retained evidence

`.maintenance/private_clinical_image_20261116/` retains build metadata, input/code
audit, commands, runtime override, host/image logs, source/privacy validations,
comparison script/report and `verification.json`. The host output is
`outputs/layered/pseudonymised_default_20261116`; the image output is the private
workspace's `outputs/smoke`. These payloads and the image are Git-ignored.

Comparison and native validation ran inside the image with accepted copies,
configuration, host results and tracked method-provenance JSON mounted read-only,
plus a writable private evidence area. Original inputs and private maps stayed
unmounted. The local audit helper required container import/report paths and the
method-provenance mount; initial failed audit logs were retained. Validation rules
were not relaxed, no input was changed and no production validator was modified.

The strict Layer 3 scanner retains the [known donor-code/public-label false positive](figure_modules_20261103.md).
As before, only the in-memory public Layer 2 definition subtree was projected after
equality-checking it against the tracked definition. Clinical exports and other
metadata remained scanned. Layer 4 aggregate-only/privacy checks passed normally.

The work establishes software/source equivalence for these named runs, not
clinical validity or public anonymity. Existing quality reviews remain. PNG
comparison was pixel-exact; PDF export and visual Excel rendering were not checked.
The later acceptance-documentation commit does not change the image's recorded
clean build checkpoint or scientific engine code. Current routine commands are
owned by the [README](../../README.md#container-build-linux-x86-64).

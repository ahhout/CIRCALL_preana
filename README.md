# Pre-analysis

One four-layer pipeline for CIRCALL and retrospective sample integrity, DNA
statistics, diagnosis associations, and descriptive disease tracking.

- **Run:** this README.
- **Configure:** [master configuration guide](docs/configuration.md).
- **Interpret:** [results guide](docs/results.md).

## Setup

The sole launcher, `run.py`, selects the existing shared `pre_analysis` Conda
environment automatically; activation is not required. Create the environment only
if missing:

```bash
conda create -n pre_analysis --file environments/conda-linux-64.lock
```

The [environment definition](environments/environment.yml) and adjacent Linux lock
specify dependencies. Figure export additionally requires Arial installed on the
rendering system; the Conda lock does not install it. On Linux, verify the licensed
system font installation before running:

```bash
conda run -n pre_analysis python -c "from matplotlib.font_manager import findfont; print(findfont('Arial', fallback_to_default=False))"
```

Clinical workbooks and outputs are local and Git-ignored; a code-only clone does
not include them.

## To do

- [ ] Deidentify the five clinical workbooks selected in
  [the pipeline master](configs/pipeline_layers.json) before embedding them in a
  shared container image. Preserve originals; agree the date policy, remove direct
  identifiers and identifying metadata from copies, preserve approved matching
  rules, and validate the copies with preflight and a smoke run. Deferred for now;
  source workbooks, private mappings and data-bearing images must remain outside Git.
- [x] Adapt packaging to Apptainer and validate a complete four-layer run with
  synthetic inputs. Clinical-data acceptance remains pending the review above.

## Container build (Linux x86-64)

The optional Apptainer image runs all four layers with the existing launcher and
Linux Conda lock. Install Apptainer inside WSL2 Ubuntu or Linux using the
[official installation guide](https://apptainer.org/docs/admin/1.5/installation.html#install-ubuntu-packages).
Docker Desktop is not required. Standard-library Python and Git prepare the build;
Arial's four local TTF styles are also required.

Select an explicit schema-2 master with reviewed workbooks under `sources`;
see [configuration](docs/configuration.md). The helper copies selected bytes
unchanged and does not anonymise them. Anonymisation of the current clinical
workbooks is deferred in the [to-do list](#to-do). Use synthetic sources until
that review is complete. No clinical data image has been built or published.

```bash
python3 environments/container/build.py \
  --config /absolute/path/to/reviewed_master.json \
  --arial-dir /usr/share/fonts/truetype/msttcorefonts \
  --context .maintenance/container_builds/reviewed_build \
  --image .maintenance/container_builds/circall-preana.sif
```

Each context and image destination must be fresh; existing files are preserved.
Contexts and SIF images are Git-ignored and can contain selected data and fonts.
`--prepare-only` prepares a context without building. On this WSL installation,
Apptainer 1.5.5's subordinate-ID build fails while mounting `binfmt_misc`;
add `--root-mapped-build` to use the tested root-mapped namespace alternative.
This changes build mechanics only, without changing system configuration.

The font directory must contain `Arial.ttf`, `Arial_Bold.ttf`, `Arial_Italic.ttf`
and `Arial_Bold_Italic.ttf`. The build checks all four styles without fallback.
Use fonts covered by the applicable licence for installation and sharing;
see [Microsoft's redistribution guidance](https://learn.microsoft.com/en-us/typography/fonts/font-faq).
The Conda definition and lock are unchanged; Arial is an image-level asset.

Run from WSL/Linux. Without pipeline arguments the image performs preflight:

```bash
apptainer run --cleanenv --containall .maintenance/container_builds/circall-preana.sif
mkdir -p outputs/container
apptainer run --cleanenv --containall \
  --bind "$PWD/outputs/container:/app/outputs" \
  .maintenance/container_builds/circall-preana.sif --output-dir outputs/smoke
```

Execution uses your host UID/GID and a read-only image. The output parent must be
writable; each run destination must not exist. Selected workbooks are embedded
under `/app/input/`. `--containall --cleanenv` avoids the default home/current
working-directory mounts and inherited analysis environment. Only the explicit
output directory is shared with the run. The four-layer clinical gates and exit
codes remain unchanged. See [container provenance](docs/audit_guide.md#container-provenance)
for build hashes, validation and limitations.

## Run

[configs/pipeline_layers.json](configs/pipeline_layers.json) owns current sources,
scientific options and figure output. Every execution runs all four layers in
order. Always run preflight before execution:

```bash
python3 run.py --validate-only
python3 run.py
```

Only standard-library Python is needed to start the launcher. It finds Conda via
`CONDA_EXE`, then `PATH`, then standard `~/miniconda3`, `~/miniforge3` or
`~/anaconda3` installations. Set `CONDA_EXE` for a different installation. It
relaunches in `pre_analysis` once; an already-correct environment is reused.
The launcher never creates or installs an environment automatically. Missing Conda
or an unavailable environment fails explicitly. The former shell wrapper is
[archived](archive/retired/conda_launcher_20261020/README.md).

Python accepts `--config PATH` for a complete four-layer configuration or profile
reference. Public `--layers`, `--workflow`, direct layer-module commands and the
four former single-layer profiles are retired and fail explicitly before source
preflight or output creation. Internal workers and scientific modules remain
separate for testing and independent completion.

Every new run defaults to `outputs/layered/run_<timestamp>/`, containing numbered
layer folders and one `.audit` directory. `--output-dir outputs/<fresh-name>`
selects a new destination; existing directories are refused. Relative CLI paths
resolve from the caller, including when Conda is launched.
Configuration paths resolve from the file that owns them.

The [CIRCALL MRD rules](docs/layers/disease_modeling.md#current-circall-source-review)
accept reviewed positive NQ annotations with separate sensitivity metadata.
Invalid annotations and conflicting records still impose quality holds.
Preflight returns nonzero for a known hold. Full execution preserves independent
completed and blocked reports, then returns nonzero. Infrastructure/configuration
preflight failures prevent execution. See
[completion semantics](docs/audit_guide.md#preflight-and-completion).

For a run-specific figure choice, append `--pdf-output` or `--no-pdf-output` to both
preflight and execution. Persistent choices live in the master; CLI choices win.
PNG output remains enabled. See the [results guide](docs/results.md).

## Repository ownership

| Location | Purpose |
| --- | --- |
| `analysis/{data_integrity,sample_statistics,advanced_analysis,disease_modeling}/` | Internal scientific layers and worker interfaces |
| `analysis/{sample_statistics,advanced_analysis,disease_modeling}/figures/` | Internal figure families for Layers 2–4; workbook reporting stays in each layer's `reporting.py` |
| Shared `analysis/*.py` | Reading, methods, configuration, orchestration, publication and maintained workbook tools |
| `analysis/validation/` | Read-only result-validation commands |
| `configs/pipeline_layers.json` | Complete pipeline controls; full-run references remain supported |
| `configs/definitions/` | Approved scientific definitions, mappings and comparison matrix |
| `configs/maintenance/` | Explicit workbook maintenance; never automatic repair |
| `Apptainer.def`, `environments/container/` | Single-image Apptainer recipe and explicit-source packaging helper |
| `tests/` | Automated checks and synthetic fixtures, including historical result layouts |
| `docs/layers/` | Layer-specific interpretation |
| [Scientific contracts](docs/workflow_contracts.md) | Approved decisions and rationale |
| [Audit guide](docs/audit_guide.md) | Validation, provenance, publication and failure handling |
| [All-layer acceptance](docs/history/all_layers_only_20261020.md) | Interface retirement, audit fixes, verification and rollback |
| [History](docs/history/README.md) | Dated acceptance, migration and rollback evidence |
| [Retirement map](docs/replacement_coverage.md) | Active dependencies and historical-only capabilities |

Update the owning document and link to it elsewhere. Scientific values live in
configuration and rationale in contracts. Historical commands remain as executed.
Older scientific workflows are [archived](archive/retired/older_workflows_20261008/README.md).
Single-layer selectors and unused artifact helpers are
[retired separately](archive/retired/single_layer_interfaces_20261020/README.md).
Longitudinal mixed models, bootstrap trajectories, combined yield/WBC panels and
normalized kinetics remain historical functionality. Inputs, existing results and
rollback snapshots stay in place; historical single-layer output readers remain.

# Pre-analysis

Sample handling, diagnosis cfDNA associations, and longitudinal blood-count/MRD kinetics in one repository.
The default pipeline runs Layers 1–4: integrity, sample statistics, diagnosis cfDNA
associations, and descriptive disease tracking in the shared `pre_analysis` Conda
environment. Older workflows remain explicitly available for compatibility.

## Run an analysis

Run all implemented layers (currently Layers 1–4):

```bash
./run_all_layers.sh
```

Both `./run_all_layers.sh` and `python run.py` select `configs/pipeline_layers.json`
through the integrated runner.
Each invocation preflights all four layers, then executes them in order under one
fresh `outputs/layered/run_<timestamp>/` root with `01_data_integrity/`,
`02_sample_statistics/`, `03_advanced_analysis/`, `04_disease_modeling/` and `.audit/`.
The root `.audit/run_manifest.json` records one run ID, every layer's outcome,
input hashes and the publication evidence. Independent layers and cohorts continue
after quality holds or workflow failures; an incomplete run exits nonzero.
Configuration or worker-preflight failures stop before execution, and an interrupt
stops remaining work. See the [unified run contract](docs/workflow_contracts.md#unified-layered-orchestration--october-6-2026).

Use `./run_all_layers.sh --validate-only` for preflight alone, with no output
publication; `--output-dir outputs/<fresh-name>` overrides the combined destination.
Relative destinations are resolved from the repository root. Existing directories
are refused. Individual-layer profiles retain their existing output roots, and
historical results stay in place.

Layer 4 provides MRD and recorded-count descriptions; normalized modeling remains
a later opt-in. The current [CIRCALL MRD hold](docs/disease_modeling.md#current-circall-source-review)
still makes validate-only return nonzero. Full layered execution can publish
Layers 1–3, independent retrospective disease results and blocked Layer 4 reports,
then return nonzero for the hold. It does not reinterpret the unsupported annotations.

Open the cohort workbooks inside each numbered layer directory: `integrity_report.xlsx`,
`statistics.xlsx`, `associations.xlsx`, and `disease_modeling.xlsx`. Start with the
root manifest to distinguish completed reports from blocked or failed analyses.

For **Layer 1 integrity reports** on the harmonized October 5 inventories:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_integrity.json
```

Layer 1 runs are saved under `outputs/layer1_data_integrity/run_<timestamp>/`.
Open `retrospective/integrity_report.xlsx` and
`circall/integrity_report.xlsx` inside that run. Each report has
Summary, Issues, Coverage and Definitions tabs. Issues are grouped with counts;
cell references appear only for groups with 1–9 occurrences. Definite data errors
produce exit code 1 **after** completed reports are published. See the
[Layer 1 guide](docs/data_integrity.md) for standalone execution and interpretation.
The existing canonical and `cfdna_associations` profiles retain their selection
and preparation. Layer 3 is separately selected for harmonized diagnosis sources.

Run these commands from the repository root. Create an environment only if it is
missing; its YAML definition is beside the lock file. For an existing installation,
add the locked packages with `conda install -n pre_analysis --file environments/conda-linux-64.lock`.

```bash
conda create -n pre_analysis --file environments/conda-linux-64.lock

conda run --no-capture-output -n pre_analysis python run.py --validate-only
conda run --no-capture-output -n pre_analysis python run.py
```

With `pre_analysis` activated, `python run.py` loads `configs/pipeline_layers.json`
and runs all four layers after integrated preflight. Normalized modeling remains
outside this descriptive disease release. Use explicit profiles for individual
layers or compatibility workflows. Scientific option changes still require review.
Paths in the JSON are relative to the JSON file, even when launching
the script from another directory. Use `--config path/to/profile.json` for another profile.

Optional top-level JSON keys `"output-dir": "../output/my-run"` and
`"validate-only": true` configure the destination and preflight-only mode.
Omit them for a fresh timestamped destination and full execution. CLI
`--output-dir`, `--validate-only`, and `--no-validate-only` override those settings.
An explicitly configured destination must not already exist.

## Compatibility workflows

The former combined default remains available unchanged:

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_all.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_all.json
```

Compatibility `canonical`, `cfdna_associations`, and `blast_kinetics` workflow IDs,
direct analysis flags and existing profiles remain supported. Longitudinal DNA
models, bootstrap trends, handling correlations and combined yield/WBC panels
remain here until their [planned layered migrations](docs/replacement_coverage.md#planned-migration-increments)
are validated. No older package has been archived or retired by the default switch.

Older analysis flags such as `--circall` or `--analysis` select the canonical
compatibility interface when no profile is supplied. Use a layer profile for
harmonized sources; changing workbook filenames alone does not migrate preparation.

The older profiles explicitly select the October 1 CIRCALL inventory and blood-count
workbooks, plus `input/retrospective_blast_count_01102026.xlsx` for
retrospective blast counts. Both count sources use investigator-confirmed ×10⁹/L.
Blood-count cohorts retain separate identities and are displayed together without pooled inference.
For plasma DNA, the compatibility combined and longitudinal profiles also enable exploratory pooled
diagnosis-versus-TP1/TP2 comparisons, as requested by the investigator. The blood-count source was selected by the investigator during the
layout migration. Input hashes and all resolved settings are recorded per run.
Missing sources fail validation; the runner never substitutes a newer file.

| Analysis | Command inside its Conda environment |
| --- | --- |
| Sample inventory, DNA recovery and longitudinal summaries | `conda run -n pre_analysis python run.py --circall input/inventaire_CIRCALL_01102026.xlsx` |
| Inventory only | `conda run -n pre_analysis python run.py --circall input/inventaire_CIRCALL_01102026.xlsx --analysis inventory --cohort circall` |
| Diagnosis cfDNA associations (retrospective; add --circall for both cohorts) | `conda run -n pre_analysis python run.py --workflow cfdna_associations` |
| Blood-count and MRD kinetics only | `conda run -n pre_analysis python run.py --config configs/pipeline_kinetics.json` |

Use `--output-dir output/<fresh-name>` to select a destination. Integrated runs
require a nonexistent destination; other commands accept a new or empty directory.
Active `run.py` flags and JSON workflow names remain supported. Legacy mode,
`--stage`, and `--retrospective-workbook` have been retired. Former
`python -m scripts...` and `python -m kinetics_pipeline` entrypoints have moved;
use the commands above and the audit guide.

### Compatibility results

The explicit `pipeline_all.json` run exposes compatibility kinetics under sample analysis:

```text
output/run_<timestamp>/
├── sample_analysis/       # workbooks, figures and primary tables
│   └── kinetics/          # recorded blast/WBC trajectories and mrd/
├── cfdna_associations/    # diagnosis: retrospective/, circall/, pooled/, availability
└── .audit/               # full engine outputs, logs, settings and hashes
```

Open the three statistics workbooks directly inside `sample_analysis/`. Prepared
observations, duplicate CSV exports, diagnostics and execution logs are retained
under `.audit/workflows/`; enable “show hidden files” to inspect them. Final
artifacts are copied from validated engine outputs, and their source locations and
hashes are indexed. A failed workflow retains its evidence and prints the log
location; independent workflows can still complete.

The explicit `blast_kinetics` JSON workflow and `python -m analysis.blast_kinetics`
entrypoint remain available for normalized-model compatibility runs; they produce
a separate `blast_kinetics/` folder only when selected. See the
[kinetics guide](docs/blast_kinetics.md). The consolidated descriptive workflow reads
both count sources directly; no cross-cohort identity linkage or pooled count model is added.
MRD includes CIRCALL TP1/TP2 and retrospective `MRD_IgTCR` paired with
`treatment_phase` TP1/TP2 and `tissue = Moelle`. Retrospective repeated annotations
use the approved numeric > pos NQ > negative priority; see the [MRD guide](docs/analysis_guide.md#retrospective-mrd).

Earlier integrated output folders retain their original layout. The former
`output/` contents are now preserved in
[the historical compatibility results archive](archive/results/compatibility_20261007T073346593956Z/),
with [old-to-new paths and verification](archive/migrations/archival_cleanup_20261007T073346593956Z/relocation.json).
Their internal layouts and manifests are unchanged; all layered `outputs/` results
remain in place. New compatibility runs may still use `output/`. The former
`blast_kinetics_workflow/` has been folded into the main pipeline: its reformatted
retrospective source is under `input/`, and its original workbook and historical
artifacts are retained byte-for-byte under
`archive/retired/blast_kinetics_workflow_20261001/`. The relocation/equivalence record
is in `archive/migrations/retrospective_input_20261001/`.

## Repository map

| Folder | Contents |
| --- | --- |
| `analysis/` | Four layers, retained shared helpers and explicit compatibility workflows |
| `configs/` | Run profiles, source catalog and extraction metadata |
| `environments/` | One shared Conda definition and explicit Linux lock |
| `tests/` | Workflow tests, orchestration tests and validation commands |
| `docs/` | Scientific contracts, analysis guides and audit instructions |
| `input/`, `outputs/`, `output/`, `archive/` | Local inputs, layered/single-layer runs, compatibility runs and historical evidence; Git-ignored |

## Validation and documentation

[Workflow replacement coverage and retained capabilities](docs/replacement_coverage.md) ·
[Audit and validation guide](docs/audit_guide.md) ·
[Scientific contracts](docs/workflow_contracts.md) ·
[Analysis guide](docs/analysis_guide.md) ·
[Blast kinetics guide](docs/blast_kinetics.md) ·
[cfDNA associations guide](docs/cfdna_associations.md) ·
[Cleanup, environment changes and rollback](docs/repository_cleanup.md)

The layout migration preserved scientific behavior. The later approved statistical
simplification uses patient-only planned longitudinal contrasts, descriptive handling
correlations, and one default peripheral-blast association regression; see the contract. The shared environment retains the previous canonical numerical package builds.
Scientific engines continue to prepare and analyze their own sources. Interpretation limitations and unresolved experimental decisions are
listed in the scientific contracts.

## Layer 2: inventory and descriptive sample statistics

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_sample_statistics.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_sample_statistics.json
```

Reports and PNG/PDF figures are under `outputs/layer2_sample_statistics/`, separated
into retrospective, CIRCALL and pooled scopes. Layer 1 errors produce a blocked
report rather than statistics for the affected cohort. See the
[Layer 2 guide](docs/sample_statistics.md) for receipt definitions, ID preparation,
standalone commands and validation. Individual profile settings remain unchanged.

Single-layer integrity runs now publish `retrospective/` and `circall/` directly
inside the run folder. `.audit/` is retained for provenance and validation. Mixed
workflow runs retain their workflow directories; other historical runs keep their
original layout. The explicitly requested `run_20261005` was relocated with a
verified migration record under `archive/migrations/flatten_layer1_20261006/`.

## Layer 3: diagnosis cfDNA associations

```bash
conda run -n pre_analysis python run.py --config configs/pipeline_advanced_analysis.json --validate-only
conda run -n pre_analysis python run.py --config configs/pipeline_advanced_analysis.json
```

Open `retrospective/associations.xlsx`, `circall/associations.xlsx` and
`pooled/associations.xlsx` in the fresh run under `outputs/layer3_advanced_analysis/`.
These reports use recorded cohort-qualified IDs and predictor-specific patient
populations, with logarithmic concentration figures in original ng/mL units.
Controls affect integrity only; pooled views have no inference. See the
[Layer 3 guide](docs/cfdna_associations.md#layer-3-harmonized-diagnosis-associations).

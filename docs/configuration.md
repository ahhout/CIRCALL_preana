# Configure the layered pipeline

Edit [the master](../configs/pipeline_layers.json) for routine runs. It contains
the complete pipeline run options and the Layer 3 comparison switches. Referenced
scientific definitions describe the approved methods; they are not alternative
run profiles. The default sources are the validated pseudonymised working copies;
[the input guide](deidentification.md) owns their provenance and the retained
original-source maintenance profile. Use [README](../README.md#run) for execution commands.

## Controls and precedence

| Master field | Meaning |
| --- | --- |
| `sources` | Explicit inventory, CIRCALL, donor and count workbook paths, declared once. No newest-file selection or cross-source matching. |
| `defaults.cohort` | `all`, `retrospective` or `circall`, applied to every layer unless overridden in its options. |
| `defaults.include-controls` | Existing control selection and associated integrity checks. Layer 3 controls remain integrity-only. |
| `defaults.rules` | Shared integrity definition. Disabling Layer 1 execution does not disable other layers' own integrity gates. |
| `defaults.pdf-output` | PDF alongside PNG for Layers 2–4. The shipped master currently selects PNG only. |
| `layers` | All four layer option blocks are required and execute in order. Legacy `enabled` values may be omitted or Boolean `true`; `false` is rejected. |
| `layers.<name>.options` | Layer-specific definitions, pooling, predictors, seeds, count/MRD component selection and display settings. These override shared defaults. Workbook paths belong only in `sources`. |
| `layers.advanced_analysis.options.comparison-switches` | Complete cohort → outcome → predictor Boolean matrix. False suppresses that pair's tests, descriptions and figures. Pooled descriptions require both cohort switches. All false is valid; preparation and integrity still run. |
| Optional `output-dir` / `validate-only` | Run destination and preflight mode; CLI options override them. |

The master is schema version 2. It resolves into the established engine options
before any source preflight or execution. Unknown fields and invalid switches
fail; there is no arbitrary inheritance or automatic scientific adaptation.
Version-1 configurations remain readable only when they select exactly all four layers once; execution is normalized to layer order.
Retired workflow names and profiles fail; they never forward to another analysis.

Public `--layers`, `--workflow` and direct layer-module execution are retired.
The sole `python3 run.py` launcher selects Conda automatically and runs all four layers. `--pdf-output` / `--no-pdf-output`
override figure choices without changing PNG output. All new results use the
numbered full-pipeline layout documented in [results](results.md).

The four former single-layer profiles are preserved in the
[single-layer interface archive](../archive/retired/single_layer_interfaces_20261020/README.md)
and their old paths fail explicitly. `pipeline_layers_circall_07102026.json` remains
a full reference, not a frozen source snapshot. Schema-2 profile references remain
supported; an optional legacy `layers` list must contain each of 1–4 exactly once.
Partial references are rejected rather than expanded silently.

## Scientific definitions

| Definition | Purpose and allowed variation |
| --- | --- |
| [Integrity](../configs/definitions/data_integrity.json) | Field types, arithmetic checks, severity and approved receipt/extraction rules. |
| [Sample statistics](../configs/definitions/sample_statistics.json) | Metrics, visits, receipt rules, plotting and existing participant-level comparison methods. Custom definitions must match the versioned file. |
| [Diagnosis associations](../configs/definitions/advanced_analysis.json) | Approved endpoint/predictor matrix, mappings, eligibility and methods. The master's switches select within that matrix; they cannot add comparisons or change preparation. |
| [Disease tracking](../configs/definitions/disease_modeling.json) | MRD/count rules, identity boundaries and default displays. Custom definitions must match the versioned file. |

Selection is distinct from changing a scientific rule. Eligibility, matching,
thresholds, transformations, multiplicity and pooling rules still require explicit
scientific authorization under [the contracts](workflow_contracts.md). The current
configuration selects the validated working copies while retaining scientific
values, switches and PNG/PDF choices. Source adoption does not enable another analysis.

## Provenance and other configuration

The run records the fully resolved engine options. Every selected profile
reference and its owning master is hashed as an input, and changes during
preflight or execution invalidate the run. Source files, definitions, code and
the environment retain their existing provenance checks.

Older scientific configuration is [archived](../archive/retired/older_workflows_20261008/README.md). `configs/maintenance/` is for explicitly invoked annotation/harmonization
tools. Those tools can prepare source copies under their documented safeguards;
they never run as a side effect of analysis or preflight.

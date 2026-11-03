# Diagnosis cfDNA associations

## Layer 3: harmonized diagnosis associations

The read-only `advanced_analysis` workflow reads the explicitly selected inventories
through the shared raw/cached reader. It does not consume Layer 2 summaries. Its
[scientific contract](../workflow_contracts.md#layer-3-diagnosis-cfdna-associations--october-6-2026)
and [versioned definitions](../../configs/definitions/advanced_analysis.json) specify
five recorded outcomes and the exact cohort-specific comparison matrix.

Use the [README layer commands](../../README.md#run) and
[master configuration](../../configs/pipeline_layers.json) for sources and settings.
The default `--predictors requested` tests all enabled requested pairs: 31 CIRCALL
and 30 retrospective comparisons when every switch is enabled.
Edit `layers.advanced_analysis.options.comparison-switches` in the master.
Each cohort/outcome/predictor entry is a JSON Boolean; setting
`circall.dna_total_ng.sampling_time` to `false` suppresses that pair's test,
descriptions and figure. Pooling requires the pair in both cohorts. All switches
may be false; source validation and sample selection still run unchanged.
The approved comparison matrix remains in the versioned scientific definition.
A custom definitions file may select Boolean changes; master comparison switches
override the definition defaults. Direct layer execution is retired.
See [configuration precedence](../configuration.md#controls-and-precedence).
An explicit predictor list restricts hypothesis testing within the enabled matrix;
enabled comparisons remain described. It cannot re-enable a disabled comparison.
Unrequested variables are absent, including retrospective marrow blasts. CIRCALL
marrow blasts remain requested. [Older association workflows](../../archive/retired/older_workflows_20261008/docs/compatibility/cfdna_associations.md) are archived.

Only diagnosis plasma supplies outcomes. Retrospective eligibility additionally
requires recorded cfDNA and a Roche tube. A present sample ID is required.
Unassigned diagnosis template rows without sample/DNA identifiers or clinical and
extraction measurements are counted and skipped before identity validation. Actual
records with missing or malformed participant IDs still block; this does not relax
whole-cohort integrity gates or the separate Layer 4 clinical annotation gates.

One eligible diagnosis sample is selected per patient using the configured
`sample-selection-seed`. Selection remains based on numeric recorded
`cfdna_ng_per_ml_plasma`, including zeros, with an independent RNG per cohort-qualified
patient and candidates ordered by hashed sample identity. All five outcomes and
sample handling variables come from that same selected row. There is no redraw for
missing endpoints or clinical values. When all selection outcomes are unavailable,
one eligible row is retained; no measurement is imputed or recalculated. Selection
can discard informative repeats and must not be optimized for significance.

Retrospective metadata are restricted to diagnosis plasma: no blood-pellet, marrow
or follow-up matching. Sex, age, maximum WBC, hemoglobin, platelets and peripheral
blasts come from the selected row; subtype retains first-nonmissing diagnosis
plasma handling with discordance counts. `cytology` supplies peripheral blasts,
falling back to `cytospin_%` only on that row. Source fractions are converted once
to percentage points. WBC uses `diag_blood_wbc_max_x10*9/L` in both inventories;
its maximum interpretation was confirmed by the investigator. In the reviewed
retrospective source, diagnosis plasma WBC, hemoglobin and platelet values remain
unavailable even though other specimen rows contain blood counts.

CIRCALL diagnosis clinical metadata retain concordance checks. Handling variables,
corticosteroid exposure and collection time belong to the selected plasma sample.
`sampling_time` is a categorical morning/afternoon comparison, split at noon. It
uses recorded clock time and is not a processing delay. Sex, genetic subtype,
corticosteroid exposure and morning/afternoon use categorical omnibus tests where
requested; recorded categories are not silently combined.

The existing single-predictor OLS method is applied to log10 of each recorded
outcome, including positive cfDNA fractions. Continuous predictors use HC3 robust
uncertainty; categorical tests use the existing omnibus method. Each pair uses
its own complete positive observations. Genuine zero outcomes remain in original-
scale descriptions and are counted as excluded from log analyses; no pseudocount
is introduced. The models have no patient random effect or covariate adjustment.
Singleton categories can give an observation unit leverage, making its studentized
residual and Cook's distance undefined. Diagnostics count these unavailable values
and scale-location plots omit and label only the affected diagnostic points.
The observation stays in the fitted model; coefficients and p-values are unchanged.

**All primary p-values are unadjusted, at the investigator's request.** No BH or
other multiplicity correction is applied. Reports show the number of requested
and selected tests; the larger testing scope increases false-positive risk.
Ordinary 95% intervals are pointwise. Peripheral-blast Spearman remains a secondary
unadjusted analysis for each tested outcome; other Pearson/Spearman coefficients
are descriptive. The four mass/concentration endpoints share arithmetic operands,
and elution volume enters several outcome formulas, limiting interpretation of
those associations as independent biological or extraction effects.

Each cohort/scope has `associations.xlsx` with Summary, Coverage, Associations,
Descriptions, Diagnostics and Definitions tabs. Every comparison table identifies
the outcome and its units. Coverage distinguishes missing endpoints, nonpositive
pairs, analysis counts and unavailable tests; Summary reports empty template rows
and cfDNA-based sample-selection counts. Unavailable or unestimable tests have
explicit reasons, not fabricated figures. Main plots are under
`figures/<outcome>/<predictor>/` and display original units on log y-axes. WBC and
CIRCALL marrow plots, and all DNA concentration (ng/µL) predictor plots also use
log x-axes (configured by `rules.log_x_predictors`); nonpositive predictors remain in models
but are counted and omitted from the log display. Categorical boxes are computed
on log10 values and back-transformed, so their median can differ from the raw-scale
median in the workbook.

Layer 3 matches the Layer 2 figure style: CIRCALL orange circles and retrospective
blue triangles, pale categorical boxes, dark fitted curves and neutral confidence
bands. Legends sit below the plotting area. Titles and descriptive footers are omitted;
pooled count labels show total analysis n without cohort-specific counts. Main exports
are 300-dpi PNGs and, when enabled, vector PDFs with embedded fonts; audit diagnostic plots use
the same cohort colours and axes. The shared `analysis/plot_style.py` controls the
palette and export settings. These presentation changes preserve model fits,
confidence intervals, p-values, observation selection and categorical jitter seeds.

Pooled views remain descriptive and are limited to requested pairs shared by both
cohorts with comparable units and available observations. There are no pooled
hypothesis tests, no retrospective marrow pooling and no controls in patient
models. Extraction protocol and cohort differences still limit pooled interpretation.

Public reports contain no patient/sample identifiers. Selected source coordinates,
hashes and residual diagnostics stay in local `.audit` evidence. Definite integrity
errors, invalid measurements and conflicting CIRCALL clinical metadata block the
affected cohort; independent reports still publish before a nonzero quality exit.
See the [audit guide](../audit_guide.md) for validation and publication safeguards.
The [October 6 acceptance record](../history/layer3_validation_20261006.md) remains historical
evidence for its recorded sources and earlier comparison scope.

# What question does each statistical output answer?

This guide describes retained compatibility analyses and their historical methods.
For the current layered pipeline, use [the results guide](../results.md).
The Layer 2 comparison tests and expanded Layer 3 scope have separate contracts.

The compatibility plan follows the [approved scientific contract](../workflow_contracts.md#approved-statistical-simplification--october-1-2026).
Earlier results used a larger testing battery; those runs and the pre-change source
snapshot remain retained evidence. Their p-values are not equivalent to current results.

## Does DNA abundance change during follow-up?

Each cohort has one patient-only model:

`log10(DNA per mL) = categorical visit mean + patient random intercept + residual`

The random intercept accounts for repeated observations from a patient. Visit is
categorical; displayed day labels do not establish numerical spacing. Earlier visits
can inform the fit without generating additional tests. Configured descriptive visits
remain in the figures and counts but do not enter the model. Controls are a separate
descriptive reference because the mixed adult/pediatric reference lacks age adjustment.

Read `mixed_contrasts.csv` as B/A geometric-level ratios and ordinary 95% confidence
intervals, followed by BH-adjusted p-values. This is not the arithmetic mean of
individual fold changes. `primary_contrasts.csv` contains the same rows for compatibility;
it is not an extra analysis. `planned_comparisons.csv` records unavailable/descriptive
comparisons, and `paired_counts.csv` distinguishes paired patients from per-visit counts.

`model_diagnostics.csv` records convergence, patient/record counts, variance components
and numerical warnings. A converged fit with a variance-boundary warning still needs
review. Common residual variance, the random-intercept structure and log-scale errors
are modelling assumptions, not facts established by software tests. Missing visits
may bias observed trajectories and model estimates; the model does not correct
informative follow-up. Sparse-visit rules are documented in the contract.

## How is sample handling associated with recovery?

Existing scatter plots and Pearson/Spearman coefficients describe the measured variable pairs.
They generate no correlation p-values. Overall records may repeat patients and mix
visits; coefficients do not isolate a within-patient or causal handling effect.
Total DNA equals concentration multiplied by eluate volume, so some relationships
are coupled by construction. Well counts, pooling of wells and the per-well elution
choice remain unresolved. No extraction-effect regression is justified by these
correlations alone. Eligibility and the existing minimum display counts are unchanged.

## Is peripheral blood blast percentage associated with diagnostic cfDNA?

The selected default is one patient-level OLS regression with log10(cfDNA) as outcome
and HC3 uncertainty. Read the slope and CI, the geometric fold change per specified
predictor increment, then the corrected p-value. With one selected predictor the
adjusted p-value equals its raw p-value. Additional explicitly selected predictors
share one correction family within each cohort; categorical predictors contribute an overall test.
There is no correction across cohorts or across all workflows. The default predictor
was selected by the investigator during this exploratory review, not preregistered
before examining results.
An unavailable selected predictor remains in that family but has no reported p-value.

Age, sex, genetic subtype, WBC and marrow blast percentage remain descriptively
summarized by default. Separate one-predictor models do not establish independent
associations or address confounding. Predictor-specific missingness can change the
patients entering each selected model. Group summaries do not justify inference
for rare categories. Residual, Q-Q and influence diagnostics require inspection;
there is no Shapiro/linearity/heteroskedasticity test battery. The plotted diagnostics
are residual versus fitted, Q-Q and scale-location; influence is currently recorded
as aggregate maximum leverage and Cook’s distance, not a Cook’s-distance plot.
HC3 applies to selected continuous inferential models, not descriptive trendlines;
optional categorical tests retain conventional OLS uncertainty.

## What stays descriptive?

Inventory, missing collections, volumes, DNA recovery summaries, blood counts and
MRD retain their established meanings. Whole-patient bootstrap trend intervals
quantify uncertainty in observed-visit medians; they are not patient spread,
simultaneous confidence bands or an adjustment for selective follow-up. Assigned
MRD display fractions are not measured values or detection limits. Normalized blast
modeling remains an explicit compatibility workflow, excluded from default runs.

## Verified comparison with the retrospective archive — October 1, 2026

Source review covered `../archive/multivariate_analysis_retrospective/`:
`archive/v1/analyze_blast_cfdna.py` and the root `analyze_blast_cfdna.py` (v2).
The archived scripts were inspected, not executed or modified.

| Difference | Verified interpretation |
| --- | --- |
| Archived v1 | Broad exploratory analysis with raw Spearman p-values, single- and multiple-predictor regressions, interaction/sensitivity analyses, and automated association wording. Pairwise verdicts used both HC3 slope p-values and Spearman p-values; they were not based solely on Spearman. Multivariable cfDNA models used natural log, whereas v2/current diagnosis models use log10. |
| Archived v2 | Six separate predictor OLS fits with no multiplicity adjustment. Robust versus conventional uncertainty was fixed in predictor configuration. Shapiro–Wilk, Harvey–Collier and Breusch–Pagan results were diagnostic reports, not automatic gates selecting the model or covariance estimator. |
| Current diagnosis | Patient-level diagnostic associations retain all available descriptive views. The selected continuous inferential models use HC3; correlation coefficients and other trendlines are descriptive. Fewer tests are an investigator-approved reporting choice, not proof that correlation tests on independent diagnostic patients are inherently invalid. |
| Current handling/recovery | Repeated sample records can violate independence; mixing visits can confound interpretation; arithmetic coupling can create associations by construction. These are distinct concerns: coupling itself is not a violation of independence. Descriptive coefficients cannot establish a handling effect. |
| Pooled diagnosis | Implemented in `analysis/cfdna_associations/diagnosis.py`, descriptive only, with cohort labels and explicit eligibility/unit checks. A combined trend can reflect between-cohort differences. Comparable units do not establish exchangeability or control confounding. |
| Pooled longitudinal | Implemented separately in `analysis/sample_analysis/pooled.py`; the enabled profile includes exploratory mixed-model inference without a cohort covariate. It must not be described as universally descriptive or as a cohort-adjusted effect. |
| Provenance | `import_provenance.json` documents code import, not validation of clinical harmonization. Actual source hashes, resolved settings, availability and run manifests establish which data and rules produced a result. |

The nine retrospective preparation functions compared by Python AST were identical
between v2 and current code: `normalized_text`, `validate_columns`, `load_dataset`,
`_normalize_patient_component`, `_numeric`, `_join_sample_ids`,
`_first_nonmissing_text`, `prepare_cohort`, and `prepare_analysis_data`.
Thus the recent diagnosis WBC reduction from 46 to 5 patients is attributable to
changed source phase labels, not a rewritten retrospective preparation rule. The
five retained pairs are unchanged; the other 41 now have WBC only on TP1 rows.
The investigator explicitly prohibited borrowing follow-up metadata for diagnosis.

### Assessment and limits

Retaining all available plots while choosing one default inferential question is a
reasonable exploratory simplification. It does not answer adjusted clinical-effect
questions: univariable regressions leave confounding unresolved. Both Pearson and
Spearman remain useful descriptions of linear and monotonic patterns, respectively,
on the workflow's stated scales. The diagnosis endpoint is recorded cfDNA ng/mL;
handling/recovery metrics and their transforms are separate endpoints.

HC3 addresses heteroskedasticity in coefficient uncertainty, not nonlinearity,
confounding, dependence or guaranteed small-sample accuracy; see the
[statsmodels covariance documentation](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html).
Visual review of residual-versus-fitted and Q-Q plots from
`output/diagnosis_cohorts_20261001` found no compelling curvature in the retrospective
primary fit (55 patients); CIRCALL has only 16 patients and visible Q-Q departures.
These observations do not establish model assumptions or absence of an association.
Aggregate maximum leverage/Cook's distance were approximately 0.073/0.102 and
0.343/0.248, respectively, so CIRCALL uncertainty and influence deserve particular
care. No observations were excluded and no model settings were changed by this review.

BH is applied within each cohort's selected predictor family; one selected test
means adjusted p equals raw p. This is not study-wide FDR control, nor does it turn
a question chosen after exploratory review into a confirmatory hypothesis. Changes
to inferential scope, correction families, covariate adjustment or pooled models
would require a separate scientific decision; this audit does not introduce them.

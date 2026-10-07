# Workflow scientific contracts — version 2

The [October 7 shared sample annotation amendment](#shared-sample-annotations-and-receipt-revision--october-7-2026)
supersedes earlier extraction-state, missing-marker and receipt definitions for
Layers 1–4. Earlier acceptance counts remain evidence for their recorded hashes.

The current canonical and association contracts include the investigator-approved
statistical simplification below. Normalized kinetics retains its version-1 methods. Integration preserves each engine's preparation. All active engines now use the
shared pre_analysis environment; see [consolidation evidence](repository_cleanup.md).
Resolved arguments/profiles and source hashes identify the exact execution. No
cross-workflow prepared-table exchange or patient linkage is performed.

| Rule | Canonical (`canonical`) | Associations (`cfdna_associations`) | Normalized kinetics (`blast_kinetics`) |
| --- | --- | --- | --- |
| Sources/sheets | Explicit CIRCALL: `cohorte_lal`, `cohorte_control`; retrospective: `Inventaire`; donors: first sheet; blood counts: `blast`, `wbc` when selected | Catalog-pinned inventory or explicit override; configured `Inventaire` sheet | YAML source and sheet (`blast` in the current blast profile); CSV also supported |
| Identity | Existing source-qualified hashed identities; retrospective surname rule and CIRCALL IDs retained | Surname, first name, date of birth; blood/marrow matching retained | Configured subject column (`lastname` in blast profile); IDs kept in memory |
| Endpoint/units | Unadjusted total DNA / initial plasma volume, ng/mL; donors use supplied endpoint | Recorded `cfDNA_ng_per_mL_plasma`, ng/mL | Recorded blast count normalized to percent of each subject's day-1 baseline |
| Eligibility | Question-specific source policies; plasma and cfDNA extraction rules; present CIRCALL IDs; QC holds; positive endpoint for longitudinal inference | Diagnostic Roche blood cfDNA; configured tissue/acid/tube/phase; positive endpoint and predictor-specific complete observations | Profile window days 1–15; minimum two observations; baseline present and positive |
| Missingness | Formula-zero operands propagate missingness; genuine measured zeros retained where supported; `na` collection IDs differ from blank future visits | Existing numeric coercion, predictor-specific missingness and matching | Invalid required measurements fail; missing/nonpositive baselines excluded under configured policies |
| Aggregation | Sample summaries and patient medians are separate observation units; original cohort keys retained | Patient medians and original marrow matching | One subject/time observation; duplicates fail; daily medians for descriptive bootstrap |
| Time/transform | Model timepoints remain cohort-specific; longitudinal log10(x); descriptive log10(1+x); correlations question-specific | Diagnostic phase; log10(cfDNA) | Percent baseline; model-only global winsorization 0.025 per tail; natural log(value + 0.1) in blast profile |
| Controls/pooling | Adult/pediatric controls descriptive only; exploratory plasma pooling enabled in full/longitudinal profiles by investigator request; direct CLI pooling remains opt-in | No canonical control/table exchange | No control reference or cohort exchange |
| Models/correction | One patient-only categorical-time random-intercept ML MixedLM per cohort; planned diagnosis contrasts and BH per cohort; descriptive Pearson/Spearman only | Peripheral-blast OLS with HC3 by default; other predictors descriptive unless selected; BH across selected predictor tests | Random-intercept linear-time model; configured response transform; baseline-anchored displayed predictions; deterministic bootstrap/jitter seeds 42 |

## Diagnosis associations across cohorts — October 1, 2026

The investigator clarified that diagnosis associations and longitudinal analyses
are separate questions. Compare diagnostic cfDNA with eight requested clinical
variables, independently in retrospective and CIRCALL cohorts, plus descriptive
pooled views only where both cohorts have comparable data. A source row must say
`diag`; TP1/TP2 metadata must not be substituted, even if this reduces sample size.
Unavailable fields are skipped for now; no absolute counts are derived.

| Variable or decision | Retrospective source/rule | CIRCALL source/rule | Pooled behavior/rationale |
| --- | --- | --- | --- |
| cfDNA outcome | Recorded positive `cfDNA_ng_per_mL_plasma` in diagnostic Roche blood cfDNA; established patient medians and matching | Recorded positive `cfDNA_ng_per_mL_plasma` in diagnostic plasma with present sample and CIRCALL IDs; median per patient | Same recorded ng/mL endpoint; log10 for associations, distinct from canonical unadjusted extracted DNA yield |
| Sex | `sex` on diagnostic eligible blood records | Not present; skipped | Skipped until available in both cohorts |
| Age | `age_diag` on diagnostic eligible blood records | Not present; skipped | Skipped until available in both cohorts |
| Subtype | `genetic_subtype` in diagnostic records, established first-nonmissing rule | `genetic_subtype` in diagnostic records; discordant patient metadata fail | Descriptive pooled distributions, exact recorded category labels; no new label harmonization |
| Peripheral WBC | `GB_per_L` on diagnostic records only, established patient median | `diag_blood_wbc_x10*9/L` on diagnostic records; concordant patient metadata | Separate cohort views; pooling skipped because retrospective scale is not explicitly confirmed comparable |
| Peripheral blast percentage | Diagnostic Sang cytology, falling back to cytospin; existing fractions-to-percentage-points conversion | `diag_blood_blast_pct` on diagnostic rows; recorded Excel percentage fractions ×100 | Comparable percentage-point pooled descriptive view |
| Peripheral absolute blast count | No explicit diagnosis absolute-count field in selected inventory; skipped | No explicit diagnosis absolute-count field in selected inventory; skipped | No derivation from WBC × fraction, nor automatic borrowing from the separate kinetics source |
| Marrow absolute blast count | No source field; skipped | No source field; skipped | Unavailable; no invented measurements |
| Marrow blast percentage | Diagnostic Moelle cytology/cytospin; currently no eligible diagnostic marrow records | `diag_bm_blast_pct` on diagnostic rows; recorded Excel percentage fractions ×100 | Skipped until both cohorts supply diagnostic measurements |
| CIRCALL selection | Not applicable | Existing CIRCALL subject_key in memory; source sheet `cohorte_lal`, `timepoint=diag`, plasma present sample IDs; positive recorded cfDNA | No cross-cohort identity linkage; patient-level records are concatenated with cohort labels |
| Missingness and repeats | Existing retrospective preparation unchanged; no follow-up fallback | Missing/nonpositive cfDNA not log-analysed; valid repeat cfDNA measurements use patient medians; conflicting diagnostic metadata fail | Per-predictor complete pairs and skipped reasons are exported; not a common complete-case restriction across all eight variables |
| Inference | Previously selected peripheral-blast regression retained by default | Same selected regression with HC3 where estimable | Pooled views are descriptive, with cohort-colored points and no additional p-values; no independent or causal effect claim |
| Longitudinal boundary | Yield over time, MRD, kinetic counts and their phase rules remain in sample analysis | Same boundary | Changing MRD logic cannot relabel diagnosis metadata or introduce follow-up measurements |

`diagnosis_availability.csv` accounts for all eight requested variables in each
selected scope. Full-profile outputs are under `cfdna_associations/retrospective/`,
`circall/` and `pooled/`; no plot is fabricated for an unavailable field. The CLI
`--circall PATH` adds the second source; omitting it preserves the previous
retrospective-only entry point. `--no-pool-cohorts` disables association pooling.
Full/longitudinal canonical pooling is a separate setting and scientific question.
The snapshot is `archive/migrations/diagnosis_cohorts_20261001T143518Z/`.

## Approved statistical simplification — October 1, 2026

The investigator authorized the audit fixes and explicitly selected peripheral blood
blasts as the default regression and diagnosis versus TP1/TP2 as longitudinal
comparisons. This section supersedes earlier descriptions of the testing battery;
inputs, preparation, identity, measured endpoints, descriptive eligibility and
kinetics remain unchanged. Earlier runs are retained evidence, not equivalent runs
of this revised scientific plan.

| Decision | Rule | Rationale and source |
| --- | --- | --- |
| Longitudinal question | One categorical-visit patient random-intercept ML model per cohort; default contrasts diagnosis→TP1 and diagnosis→TP2 | Investigator selected these follow-ups; categorical time avoids inventing calendar spacing |
| Sparse follow-up | CIRCALL TP2 remains in descriptions and counts but is omitted from the fitted model and tests; default `longitudinal-descriptive-visits = [circall:tp2]` | Investigator accepted descriptive reporting with only three patients and two diagnosis pairs; explicit visit decision, not an automatic numerical threshold |
| Other model visits | Earlier established visits remain in the model to describe the observed repeated measurements; no additional contrasts by default | Preserve categorical trajectory structure while reducing hypothesis tests; `longitudinal-followups` exposes the tested visits |
| Observation unit | Existing eligible sample records, patient random intercept; no new aggregation | Retain established measurement and duplicate handling; within-visit repeats still share the patient effect |
| Controls | Adult/pediatric reference retained in figures/counts, excluded from patient models and testing | Audit identified unresolved age/source comparability; no newly inferred control adjustment |
| Multiplicity | BH across available planned contrasts within each cohort; `primary_contrasts` is an exact copy of `mixed_contrasts` | One scientific family per cohort; confidence intervals remain ordinary pointwise 95%, not simultaneous intervals |
| Removed tests | No sample Welch, patient-median Welch or Mann–Whitney battery in active runs | Repeated patients violate the independent-group comparisons; legacy helpers remain available only as retained implementation evidence |
| Pooling | Full/longitudinal profiles enable exploratory pooled plasma inference; direct CLI default remains false. Shared visits diag/TP1/TP2; two diagnosis-to-follow-up contrasts with BH within the pooled family; no cohort covariate | Investigator subsequently explicitly requested re-enabling pooled comparisons. Cohort-specific inference remains; cross-cohort protocol/time-window limitations still apply |
| Handling/recovery | Existing eligible pairs and scatter plots; Pearson and Spearman coefficients, without correlation p-values | Repeated patients, changing visits and arithmetic coupling prevent extraction-effect claims; no new recovery regression without protocol clarification |
| cfDNA predictor | `predictors = [peripheral_blast_percent]` by default; remaining fields receive descriptive summaries | Explicit investigator choice; optional predictors require an explicit CLI/config selection |
| Association inference | Separate log10-outcome OLS for each selected predictor; all continuous selections use HC3, optional categorical models retain conventional OLS and one omnibus test; BH across all selected predictor tests within each cohort | Consistent heteroskedasticity-robust continuous-model uncertainty; no reference-category hypothesis battery; unavailable tests count as p=1 for adjustment only and remain unavailable in exports |
| Association effects | Coefficient and ordinary 95% CI; geometric fold change per 10 percentage points for percentage predictors, otherwise per recorded unit | Report interpretable effect size; no claim of arithmetic-mean change, covariate-adjusted independence or causation |
| Diagnostics | Residual/Q-Q plots, aggregate leverage/Cook distance for OLS; mixed-model convergence, variance components and sanitized numerical warnings | Remove routine Shapiro, Harvey–Collier and duplicate Breusch–Pagan tests; diagnostics require review, not a pass/fail p-value gate |
| Numerical fit acceptance | Require convergence, finite likelihood/parameter uncertainty, positive finite residual variance, and usable fitted values/residuals; otherwise try the next existing optimizer (lbfgs, Powell, Nelder–Mead) and record attempts | The revised patient-only run exposed a spurious converged lbfgs result with infinite likelihood and singular covariance in both cohorts; Powell and Nelder–Mead agreed on finite solutions. Same model and ML criterion, no statistical fallback model |
| Numerical tails | Two-sided Wald p-values use `2 * norm.sf(abs(z))` | Avoid cancellation from `1 - cdf`; does not change the intended statistical test |
| Kinetics/MRD/bootstrap | Established descriptive blood counts, MRD and whole-patient bootstrap unchanged; normalized model still opt-in | No need to add models to descriptive questions |

Missingness remains observational: models and bootstrap intervals do not remove
selection bias. Small samples and boundary estimates limit Wald inference even
when software converges. No random slopes, outlier removal, new detection limits,
age matching, assay corrections or multivariable selection were added by default.
The compatibility sensitivity switches remain opt-in, outside the primary family.
The default association predictor was selected during exploratory review, not
preregistered. With one selected test per cohort BH leaves its p-value unchanged;
there is no study-wide correction across cohorts or workflows. See the
[verified archive comparison](statistical_questions.md#verified-comparison-with-the-retrospective-archive--october-1-2026)
for the distinct rationales for diagnostic and handling associations.

Rollback snapshot: `archive/migrations/statistical_simplification_20261001T115744Z/`.
It contains code/configuration/documentation/tests and hashes, excluding clinical
inputs and outputs. Restore only reviewed changed files after checking for later
edits; retain both earlier and new results. No dependency or environment-lock change.

## Analysis views retained independently of testing — October 1, 2026

The investigator clarified that statistical simplification must not remove analyses.
All six cfDNA predictor views are therefore always generated. `--predictors` selects
hypothesis tests only: the selected predictor retains regression uncertainty and BH
inference; other continuous predictors retain patient scatter plots, descriptive
least-squares trends, slopes and Pearson/Spearman coefficients, and categorical
predictors retain distributions, patient dots and group summaries. These descriptive
outputs have no hypothesis p-values or significance labels. Sparse/constant data
retain their points or a clear unavailable annotation without a fitted trend.
Handling/recovery reports likewise retain both Pearson and Spearman coefficients
without p-values. Eligibility, transformations and patient aggregation are unchanged.
The removed duplicate Welch/Mann–Whitney test grids remain excluded. The snapshot
is `archive/migrations/restore_descriptive_views_20261001T140212Z/`.

## Pooled plasma comparisons re-enabled — October 1, 2026

The investigator explicitly requested turning pooled comparisons back on after
reviewing the simplified plan. Only `pool-cohorts` changed in the full and
longitudinal profiles. Existing model, eligibility, patient identities, descriptive
visit exclusions and the single cfDNA predictor are preserved. This adds pooled
diagnosis→TP1 and diagnosis→TP2 contrasts; it does not restore the old test battery.
The kinetics-only profile remains descriptive. Pre-change snapshot: `archive/migrations/enable_pooled_20261001T133601Z/`.

## Descriptive longitudinal trend figures — October 1, 2026

The investigator approved additional median/CI figures after reviewing the
longitudinal audit. These are descriptive additions; existing boxes, models,
tests, corrections, eligibility and pooling analyses are unchanged. The bootstrap
and sparse-visit display are project-specific choices, not a newly adopted
published longitudinal model.

| Decision | Rule | Rationale and source |
| --- | --- | --- |
| Target statistic | Median across raw-scale patient/visit medians; same eligible observations and aggregation as the existing boxes | Investigator approved preserving the box summaries; differs from median-of-logs inference for even numbers of repeats |
| Resampling | Whole patient histories within each cohort, with replacement; missing visits remain missing | Approved patient-level bootstrap preserves dependence across visits; no cross-cohort pooling |
| Intervals | Pointwise 95% percentile intervals; 10,000 draws, seed 42 by default; CLI/config expose count, seed and method | Reproducible descriptive uncertainty, not patient spread, simultaneous coverage, or a significance test; independent stable cohort streams recorded |
| Empty bootstrap visits | Omit empty draws only from that visit's quantiles; export valid/empty draw counts | No invented follow-up values; conditioning is explicit and sparse follow-up remains a limitation |
| Sparse visits | CIRCALL TP2 has dots and median but no interval or incoming shading; fewer than two patients also yields no interval | Investigator explicitly approved omitting CIRCALL TP2 shading after the selected run showed only three patients; no patient observations excluded |
| Time and controls | Existing categorical labels/log y-axis; straight segments are visual guides; pooled controls retain individual dots and a median, separate from the trend | No new calendar-time mapping or fitted curve; existing control selection retained |
| Interpretation | Observed-visit summaries; no missingness adjustment or causal interpretation | Changing participant composition can change medians; bootstrap does not remove selection bias |

## Retrospective inventory consolidation — October 1, 2026

At the investigator's request, canonical and association defaults now select
`input/cfDNA_inventaire_retrospective.xlsx`, identified by the investigator as the
updated version of `input/cfdna_associations/cfDNA_inventaire_2025.xlsx`.
The association catalog pins the updated workbook's SHA-256; both workbooks pass
the association loader's required-column checks. Preparation, matching, eligibility,
and model rules remain workflow-specific and unchanged. Updated source values may
change results; equivalence to historical results is not assumed. The older workbook
and historical run provenance remain retained evidence.

## Kinetics consolidation — October 1, 2026

At the investigator's request, the default kinetics workflow now uses the existing
`canonical` blood-count and MRD approach, published under `sample_analysis/kinetics/`.
`configs/pipeline_all.json` no longer selects the separate normalized model;
`configs/pipeline_kinetics.json` selects descriptive kinetics for both cohorts and
CIRCALL MRD through the same canonical engine. The investigator clarified that
`blast_kinetics_workflow/data/blast_kinetics_data.xlsx` is retrospective and
`input/CIRCALL_wbc_blast_count_01102026.xlsx` is CIRCALL, and confirmed that
retrospective `num_blast` is in ×10⁹/L, matching the CIRCALL count unit.
CIRCALL calculations remain unchanged; retrospective counts now receive the same
descriptive preparation instead of the former default normalized-model analysis.
The normalized-kinetics column above documents the explicitly selectable compatibility
workflow; its profile, sources, CLI/JSON name, and historical results are retained.

| Decision | Rule | Rationale and source |
| --- | --- | --- |
| Default kinetics owner | Canonical blood counts and MRD; one `sample_analysis/kinetics/` result tree | Investigator requested consolidation prioritizing the existing sample-analysis kinetics results |
| Blood-count plot scale | Linear time, logarithmic y by default; measured zeros retained in data and summaries but not displayed on log axes; connecting lines break at zero; no pseudocount | Investigator approved semilog display on October 1, 2026, then requested removal of the separate zero-marker row; `--kinetics-y-scale linear` restores linear display; recorded counts and summaries unchanged |
| Measurements and inference | Recorded blast/WBC counts in ×10⁹/L; zeros retained; missing counts remain missing; no normalization, winsorization or fitted blast model | Preserve `analysis/sample_analysis/blood_counts.py` and the prioritized run's approach |
| Diagnostic baseline | Latest measured day ≤1; preserve recorded later days; overlay through day 8 only | Existing canonical configuration, unchanged |
| MRD | Retain TP1/TP2 rules; assigned display fractions 1e-8 for negative and 1e-6 for unknown significance | Existing `analysis/sample_analysis/mrd.py`; display conventions, not measured detection limits |
| Retrospective eligibility | All recorded days; zeros retained; no positive day-1 requirement, minimum two observations, or day-15 cutoff | Investigator requested applying the sample-analysis approach to the retrospective source; earlier normalized-model eligibility is not carried over |
| Retrospective identity and exports | Preserve case-sensitive trimmed surname grouping; source-qualified digest only in memory; no retrospective row-level export | Preserve original matching while separating cohorts and maintaining kinetics privacy safeguards |
| Cohort combination | Joint figures and cohort-labeled aggregate summaries; no cross-cohort linkage or pooled statistical fit | Investigator identified the sources as retrospective and CIRCALL; common count units explicitly confirmed |
| Additional endpoints | WBC remains CIRCALL-only; retrospective MRD now comes from its inventory via the phase-paired module below; no WBC reconstruction from blast percentages | MRD is a separate inventory annotation, not derived from the retrospective blast-count source |
| Recorded counts | Use supplied counts directly; do not derive/replace from blast_fraction | Audit count/fraction discrepancies remain unresolved but do not require altering recorded counts |
| Compatibility and rollback | Explicit normalized-model invocation remains supported; prior outputs and sources remain in place | Preserve established entrypoints and scientific provenance |

The pre-change code/configuration/documentation snapshot is
`archive/migrations/kinetics_consolidation_20261001/`. Restore only reviewed files
from that snapshot after checking for later edits; never reset the working tree
or overwrite clinical inputs/results. The focused profile, retrospective descriptive adapter and its synthetic tests are new files.

## Retrospective input reformat and relocation — October 1, 2026

At the investigator's request, the active retrospective source is now
`input/retrospective_blast_count_01102026.xlsx`, replacing the previous
`blast_kinetics_workflow/data/blast_kinetics_data.xlsx` location. The archived
original remains byte-identical under
`archive/retired/blast_kinetics_workflow_20261001/data/`.

| Source field or sheet | Active workbook | Scientific effect |
| --- | --- | --- |
| `cleandata` | `blast` | All 224 rows retained in order; active analysis sheet |
| `D1 date`, `sample_date` | `tt_d1_date`, `num_date` | Recorded dates unchanged |
| `num_blast` | `blast_count_x10*9/L` | Recorded counts and confirmed units unchanged |
| `lastname` | `lastname` | Existing trimmed, case-sensitive grouping unchanged; no new identifiers |
| `day`, `num_log` formulas | Same fields, remapped cell references and preserved cached values | No recalculation or scientific transformation |
| `percent_blast` and other metadata | Retained; unheaded notes become `source_note` | No percentage-to-fraction conversion or metadata inference |
| `test` | `source_test` | All 26 rows retained as unused source evidence |
| WBC | No fabricated sheet | Retrospective WBC remains unavailable |

Both the descriptive profiles and explicit normalized-model profiles select the
new source and headers. No cohort eligibility, baseline, time-window, model or
plotting setting changes in this migration. The whole former folder is retained
under `archive/retired/`, and old manifests are not rewritten. File hashes and
old/new locations are recorded in `archive/migrations/retrospective_input_20261001/`;
the separate code-only rollback snapshot excludes clinical data and outputs.

## Retrospective MRD by treatment phase — October 1, 2026

The investigator requested a retrospective MRD module and corrected the initial
TP1-only interpretation: pair `MRD_IgTCR` with `treatment_phase`. The numeric scale
was confirmed to match CIRCALL. These decisions supersede the earlier CIRCALL-only
MRD scope; blood counts and unrelated statistical methods remain unchanged.

| Decision | Rule | Rationale and source |
| --- | --- | --- |
| Source/visits | Explicit retrospective inventory, `Inventaire`; `MRD_IgTCR` paired with recorded `treatment_phase` tp1/tp2; other phases excluded | Investigator's corrected mapping; no inferred TP1-only annotation or calendar dates |
| Identity | Existing canonical retrospective surname-based subject_key, kept in memory | Preserve established within-cohort identity; no cross-cohort linkage |
| Numeric unit | Residual fraction, same as CIRCALL; measured log10 reduction = -log10(fraction) | Investigator clarified scale; 0.001 corresponds to a 3-log reduction |
| Pos NQ | Positive nonquantifiable, with optional reported `<` upper bound; scientific encodings such as 10-4 and 5.10-5 parsed explicitly | Preserve updated source category; a bound is not a measurement, uncertain-significance category, or inferred detection limit |
| Negative/missing | Negative retains configured assigned display fraction; blank/na/n/a remain missing | Existing display convention; no invented measured value or detection limit |
| Repeats/conflicts | Within each selected patient/visit, numeric > pos NQ > negative; take the highest numeric residual fraction or highest reported pos NQ bound within a category. Missing remains missing. Identical annotations collapse; resolved disagreements are counted | Investigator explicitly replaced the earlier stop rule with worst-outcome priority. No averaging; a pos NQ bound remains nonquantifiable. `--retrospective-mrd-duplicate-policy worst` is the default; `error` preserves strict mode. CIRCALL rules are unchanged |
| Scope/denominator | Select `tissue = Moelle` (trimmed, case-insensitive exact match), then TP1/TP2; include identified patient/visit groups from those rows | Investigator explicitly added the marrow filter; exposed through `--retrospective-mrd-tissue` and recorded in profiles/settings. No inferred scheduled-visit denominator or cfDNA-dose filtering |
| Output | Separate retrospective visit summaries and figure; only quantified pairs connected; bounds shown distinctly; unbounded pos NQ counted but not positioned | Descriptive module; no MRD hypothesis tests, cohort pooling, or synthetic D1 observation |
| Privacy | No retrospective patient-level MRD export; conflict review contains only workbook/cell references, visit and category labels | Clinical identifiers stay out of logs and shared exports; authoritative workbook retains annotations |

The Moelle-filtered source had four discordant patient/visit groups, all TP1.
The investigator subsequently authorized worst-outcome priority, which resolves
those groups while preserving the original workbook and reporting resolution counts.
The earlier conflict-review files are historical audit evidence. The pre-priority
snapshot is `archive/migrations/mrd_worst_outcome_20261001T141558Z/`.
The code/documentation snapshot is `archive/migrations/retrospective_mrd_20261001T134324Z/`.
It excludes clinical inputs and outputs; preserve later edits when reviewing rollback.

## Descriptive blood counts and MRD within canonical

Blood counts retain recorded units ×10⁹/L and zeros, with no baseline normalization.
The established diagnostic baseline is day ≤1; the latest diagnostic measurement
is selected by default. Recorded later days remain intact; the overlay's day-8
maximum is a display window. These are different questions from normalized kinetics.

CIRCALL MRD_TP1/TP2 are descriptive fractions relative to the diagnostic clone.
Identical repeats collapse; conflicts fail. Negative and unknown-significance
categories have explicit display fractions (1e-8 and 1e-6), not inferred measured
values or assay detection limits. No new MRD association model is introduced.

## Retired historical execution

The legacy runner was removed at the investigator’s request on October 1, 2026.
Its source workbooks, completed results, and migration snapshots remain local evidence.
Legacy CLI/JSON selection now fails; historical calculations are not rerun by active profiles.
The cleanup changes environment ownership, not the scientific rules in the table above.

## Unresolved interpretation — no automatic resolution

- Cohort timepoint labels do not establish equivalent calendar windows; CIRCALL
  random-slope sensitivity lacks an agreed numeric TP mapping.
- Exploratory combined inference has no cohort covariate; it is enabled in the full
  and longitudinal profiles at the investigator’s request. Adult/pediatric controls
  remain descriptive without age adjustment. CIRCALL TP2 stays excluded from the
  pooled fit, so its TP2 measurements come only from the retrospective cohort.
- CIRCALL Maxwell wells may be split above 5 mL; combining wells and choosing 50/60 µL
  are unconfirmed. Retrospective manual extraction details are also incomplete.
  No well counts or revised recovery endpoint are inferred.
- Matching rules and endpoints differ across workflows. A common subject model or
  preparation layer requires separate equivalence evidence and review. Environment
  consolidation and its validation are recorded in the cleanup report.
- An observational association does not establish a handling effect or its absence.

## Approved descriptive pooled MRD — October 1, 2026

The investigator requested pooled trajectories and approved stacked patient-status
bars after clarification that diagnosis is an assumed disease-positive reference,
not 100% blast cells. This adds an optional descriptive view; the separate cohort
outputs and their source preparation rules above remain applicable.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Scope | Concatenate existing CIRCALL and retrospective MRD preparations; retain cohort-qualified identities, no cross-cohort linkage or inference | Investigator's pooled-plot request |
| Denominator | Fixed union of patients retained by either preparation; complete TP1/TP2 grid for display, with absent visits marked missing. This is not the entire enrolled cohort or an inferred scheduled-visit population | Approved patient-status bars with missing follow-up kept separate |
| Diagnosis | Assumed disease-positive category for all included patients; trajectory reference fraction 1, never a measured blast-cell fraction | Investigator approved the explicit reference interpretation |
| Categories | Quantified positive, positive nonquantifiable, uncertain significance, negative, missing remain distinct; no new positivity thresholds | Preserve source annotations |
| Trajectories | Cohort colors, shared phase labels without inferred calendar days; reported bounds shown as open triangles without connecting segments; unbounded positive NQ counted only; missing visits not bridged | Avoid representing bounds or absent results as measured changes |
| Display | Existing configured uncertain/negative levels; dotted lines touch assigned levels; seed 42 for jitter | Existing display conventions |
| Exports | Aggregate counts/percentages by cohort and pooled, figures, settings; no pooled patient-level export | Preserve retrospective privacy rule |
| Configuration | `--pool-mrd` opt-in CLI; enabled in full, kinetics, and focused MRD profiles independently of plasma pooling | Requested reusable plots |

Percentages describe this observed MRD population. Missing follow-up and cohort
visit-window differences prevent interpreting a trend as a treatment-effect estimate.
Pre-change code/configuration/documentation are retained in
`archive/migrations/pooled_mrd_20261001/`; no clinical inputs or outputs were copied.

## Pooled longitudinal trend companion — October 1, 2026

At the investigator's explicit request, `python -m analysis.sample_analysis.pooled_trend
--run-dir <retained-run>` adds `longitudinal/trendlines_pooled.png` using that run's
prepared inventory and recorded bootstrap settings. The original figures and run
metadata remain intact; `.audit/supplements/pooled_trend/manifest.json` records the
additive publication, source hashes, code, environment, and validation.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Statistic | One median across concatenated cohort-qualified patient/visit medians; cohort-colored dots, no identity linkage or new inference | Requested pooled data and one shared trendline |
| Intervals | Whole pooled patient histories resampled with replacement using the retained draw count/seed; pointwise percentile intervals; TP2 interval omitted to preserve the sparse-follow-up display restriction | Existing descriptive method adapted to the requested pooled population |
| Eligibility/time | Existing longitudinal eligibility and categorical labels; observed visits only, controls separate; all available visits retained | Companion to the specified plot; no missingness adjustment or calendar-time equivalence claim |

Cohort composition varies across visits; the line is descriptive and does not
establish a treatment effect. The prior contract is retained in
`archive/migrations/pooled_trend_20261001/`.

## Pooled MRD positive nonquantifiable display — October 1, 2026

At the investigator’s explicit request, all pooled-trajectory positive
nonquantifiable results, with or without a reported upper bound, are positioned
at the assigned fraction 1e-6. This supersedes the earlier pooled bound-position
rule only; source annotations and bounds, status counts, cohort-specific plots,
and measured fractions remain unchanged. Open markers distinguish positive NQ;
segments touching them remain omitted. This is a display convention, not a
measurement, detection limit, or imputed quantitative result.

| Rule | Rationale | Source |
| --- | --- | --- |
| `--mrd-positive-nq-level` defaults to 1e-6 and is recorded in pooled settings | Display every positive NQ result at a common, explicit assigned level | Investigator request, October 1, 2026 |

## Stacked pooled MRD display — October 1, 2026

At the investigator’s request, diagnosis reference and quantified positive share
one “Quantifiable blasts” color/legend entry; uncertain significance and positive
nonquantifiable share “Pos NQ”. Missing segments and their legend entry are hidden,
with the fixed pooled denominator retained. These are display groupings only:
aggregate source categories and the assumed (not measured) diagnosis reference
remain preserved. Pre-change code and contract: `archive/migrations/mrd_status_display_20261001/`.

## Peripheral-blast Spearman sensitivity — October 1, 2026

The investigator requested Spearman as a sensitivity analysis alongside the
existing primary HC3 regression. It uses the identical complete diagnosis-level
patient pairs, separately within each cohort; pooled views remain descriptive.

| Rule | Rationale | Source |
| --- | --- | --- |
| Spearman rho with average ranks for ties; two-sided SciPy asymptotic p-value | Assess monotonic association alongside the primary linear association; approximate inference can be inaccurate in small cohorts | Investigator request to add Spearman sensitivity; scipy.stats.spearmanr |
| One peripheral-blast sensitivity per cohort, only when that predictor is selected; `--spearman-sensitivity` enabled by default, `--no-spearman-sensitivity` disables | Explicit, recorded scope; no new tests of unselected predictors | Investigator-authorized scope |
| Unadjusted sensitivity p-value, identified separately from primary regression/BH results | Diagnostic robustness comparison, not an additional route to declare significance | Project-specific implementation |
| Fewer than three complete pairs or constant variable: unavailable with reason | Avoid undefined rank inference; preserve observations and primary results | Statistical estimability |

The log transform preserves positive cfDNA ranks. These results are exploratory:
the method was added after inspecting the association plot. They do not establish
causation, and an approximate p-value is particularly limited in the small CIRCALL
cohort. Preparation, pooling, primary regression, and its correction are unchanged.

## Canonical pooled longitudinal trendline — October 1, 2026

The investigator requested making the existing pooled trendline a standard
canonical artifact. Full and longitudinal runs now generate and publish
`longitudinal/trendlines_pooled.png` when `--pool-cohorts` is enabled and both
cohorts are selected. The existing companion remains available for retained runs.
The established pooled medians, whole-patient bootstrap, seed, missingness,
controls, and TP2 interval omission are unchanged. Numeric tick labels retain
logarithmic spacing. Pooled summary/settings remain in the engine audit directory;
the figure is validated and indexed with the other canonical publications.

## Canonical yield/WBC panels — October 1, 2026

The investigator requested standard publication of the approved two-panel figure:
pooled yield above CIRCALL WBC. Canonical runs containing both longitudinal and
kinetics tasks, both cohorts, and `--pool-cohorts` generate and validate
`longitudinal/yield_wbc_panels.png` and `.pdf`. The full profile meets these
conditions; focused single-workflow profiles do not add missing analyses.

The figure reuses prepared patient/visit yield values, pooled median/interval
summaries, and selected CIRCALL WBC observations. All WBC points and actual-day
coordinates remain intact. WBC ticks are labelled D1, D4, D8, D15, TP1 (D29),
and TP2 (D71); yield retains its categorical spacing and control reference.
The axes do not imply shared time spacing. Both y-axes use logarithmic spacing
and ordinary numeric labels. This display-only integration changes no scientific
calculations, matching, exclusions, bootstrap rules, or uncertainty interpretation.
Panel settings and retention counts are recorded in the canonical audit output.

## Aligned yield/WBC visits — October 1, 2026

The investigator subsequently requested aligning time points across the composite
panels. This supersedes the composite's independent x-axis display above.
Both panels use the same equally spaced visit anchors D1, D4, D8, D15,
TP1 (D29), and TP2 (D71), with a yield-only Control position when available.
WBC display positions interpolate linearly between the corresponding day anchors;
values outside the anchors extrapolate using the nearest interval, so no late
measurements are clipped. The figure identifies the segmented time scale.
Original recorded days, all selected points, y-values, yield summaries, and
statistical calculations remain unchanged. This is nominal visit alignment,
not new confirmation of cross-cohort calendar-time equivalence.

## Additional diagnosis comparisons and WBC units — October 1, 2026

The investigator requested diagnostic cfDNA associations with absolute peripheral
blast count, marrow blast percentage, and WBC, separately and pooled where
applicable. Retrospective `GB_per_L` was explicitly confirmed as ×10⁹/L (G/L),
matching CIRCALL. `--retrospective-wbc-unit x10^9/L` records that confirmation;
the full and focused association profiles now select it. Unknown-unit runs still
skip pooled WBC. Existing per-patient diagnosis preparation is unchanged.

| Rule | Rationale | Source |
| --- | --- | --- |
| Pool diagnostic WBC when both cohorts supply pairs and the retrospective unit is confirmed | Same count unit; retain cohort-colored points and descriptive Pearson/Spearman coefficients | Investigator unit confirmation |
| Use existing diagnostic marrow percentages; label plots “Bone marrow blasts (%)” | Explicitly describe the existing tissue-specific endpoint; retain `tumor_fraction_percent` internal field/path for compatibility | Investigator requested comparison |
| Do not derive absolute peripheral blast counts or borrow kinetics measurements | The investigator explicitly withdrew permission for WBC × blast-fraction derivation; neither selected inventory has a recorded absolute-count field | Latest investigator correction |
| Keep missing retrospective diagnosis marrow and corresponding pooled marrow comparisons skipped | No follow-up substitution or invention of diagnosis measurements | Existing approved eligibility |

Regression selection, Spearman sensitivity scope, and pooled descriptive-only
inference are unchanged. At review, WBC has 16 CIRCALL and 5 retrospective pairs;
marrow percentage has 16 CIRCALL and no retrospective pairs. Coverage and skip
reasons remain recorded in `diagnosis_availability.csv`.

## Shared sample definitions — October 5, 2026

The investigator clarified these definitions while manually harmonizing the two
October 5 inventories. They guide the forthcoming shared parsing rules; the
existing adapters and selected run profiles have not yet been migrated.

| Rule | Definition and rationale | Source |
| --- | --- | --- |
| Row meaning | One row represents one sample in both inventories. A shared collection can yield separate plasma and cellular samples; do not infer a row merge or new duplicate-resolution rule. | Investigator clarification, October 5, 2026 |
| `volume_ml` | Volume used for extraction. A plasma mass/volume endpoint therefore refers to plasma used for extraction; this column alone does not establish total volume received. Earlier references to initial plasma volume must be read with this clarified meaning. | Investigator explicitly selected “Volume used for extraction” |
| Retrospective cellular blood specimen | `tissue = Sang` with `nucleic_acid = celDNA` represents a blood cell pellet, equivalent in specimen meaning to CIRCALL `compartment = blood pellet`. This establishes specimen correspondence, not assay equivalence or permission for additional pooling. | Investigator explicitly confirmed the blood-pellet equivalence |
| Identifier scope | Defer A2G, sample-ID and DNA-ID normalization and matching changes. One-row-per-sample intent does not authorize rewriting identifiers. | Investigator requested leaving these fields alone |
| Mechanical cleanup | Trim surrounding whitespace in explicitly selected label fields into new workbook copies. Report text dates and nonnumeric measurement annotations for review; retain their values and all formula caches. | Investigator authorized scripted cell-content cleanup |

The reproducible helper is `python -m analysis.workbook_cleanup --input <files>
--output-dir <fresh-folder>` in Conda `pre_analysis`. Its report records source and
output hashes, changed cell locations, review locations, command and execution
times. Input workbooks remain authoritative until corrected copies are explicitly
adopted. Assay provenance for cellular measurements moved into shared DNA columns
still requires confirmation before changing their analytical treatment.

## Approved workbook column harmonization — October 5, 2026

The investigator approved harmonizing the cleaned workbook copies. The exact
header aliases and specimen mappings are versioned in
[`configs/definitions/workbook_harmonization.json`](../configs/definitions/workbook_harmonization.json).

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Shared names | `timepoint`, `specimen_type`, `extraction_input_volume_ml`, and consistent lowercase DNA/cfDNA measurement names with `ml`/`ul` unit spelling. Header changes do not rescale values. | Investigator approval of the proposed common names |
| Specimen labels | Use `plasma`, `blood pellet`, `CSF`, and `bone marrow`; map retrospective `Sang` only when `nucleic_acid = celDNA`. Preserve missing markers and report any unapproved combinations without guessing. | Approved blood-pellet equivalence and established marrow/CSF mappings |
| Scope | Retrospective `Inventaire`; CIRCALL `cohorte_lal`, `cohorte_control`, and the corresponding measurement headers in `template`. Keep cohort identifiers, MRD layouts and assay-specific headers. Retain any existing pg/µL input column under normalized spelling rather than deleting its measurements. | Harmonize common meanings while preserving source evidence |
| Preservation | Keep every row and column position, numeric value, formula, cached result, identifier and workbook extension. Only approved text cells change. Existing formula errors require their own correction. | Structural migration only; no new pooling or scientific analysis |
| Adoption | Produce new `_harmonized.xlsx` copies with source/configuration/code hashes and an explicit mapping report. Existing analysis readers and run profiles still use their earlier schema until migrated separately. | Preserve current execution interfaces and avoid silently changing selected sources |

Run `conda run -n pre_analysis python -m analysis.workbook_harmonization
--retrospective <cleaned-retrospective.xlsx> --circall <cleaned-circall.xlsx>
--output-dir <fresh-folder>`. The output report lists header changes, specimen
cell locations, unresolved mappings and verification. Reversing only the approved
cell edits reproduces the original XML; every other ZIP member is byte-identical.
Original and cleaned source copies are retained for rollback.

At the investigator's subsequent request, the harmonized copies were moved into
`input/cfDNA_inventaire_retrospective_05102026.xlsx` and
`input/inventaire_CIRCALL_05102026.xlsx`, replacing the previous files at those
paths. The replaced workbooks were first archived under
`archive/migrations/harmonized_input_adoption_20261005T130516Z/`. Its
[relocation record](../archive/migrations/harmonized_input_adoption_20261005T130516Z/relocation.json)
records all former/current paths and confirms unchanged hashes for adopted and
archived files. Earlier audit reports are retained as historical evidence; use
the relocation record to resolve their former paths. Existing analysis profiles
and adapters have not yet been migrated to the new input schema.

## Layer 1 integrity contract — October 5, 2026

The investigator approved the read-only integrity workflow and its grouped Excel
reports. This contract covers source review only; analytical eligibility and
scientific models remain in their existing workflow contracts.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Sources | Explicit harmonized October 5 inventories; retrospective patients, CIRCALL patients and optional CIRCALL controls. Count workbooks, templates and donors are outside v1. | Investigator-selected initial scope |
| Required structure | Common sample/specimen fields and ten extraction/DNA measurement headers; patient sheets additionally require timepoint. Missing values remain distinct from missing columns. | Approved Layer 1 plan |
| Measurement checks | Five approved DNA/cfDNA calculations with rtol=1e-9 and atol=1e-12; nonnegative physical measurements, cfDNA fraction in [0,1], positive volume when normalizing plasma mass. These checks report findings and never filter or rewrite samples. | Existing consistency tolerance and investigator-approved formula/validation plan |
| Missingness | Preserve measured zeros, source missing markers and intentionally empty formula results. Missing inputs and future visits alone do not fail validation. Report artificial formula zeros, absent caches and unavailable checks distinctly. | Approved guarded-formula and integrity rules |
| Severity | Definite structural/formula/arithmetic failures are errors; ambiguous dates, annotations and uncertain references require review. Field definitions and rule severities are versioned in the rules JSON. | Investigator approved reporting all findings and returning failure on definite errors |
| Report grouping | Workbook + sheet + field + rule + severity. Count each distinct affected cell once per group; count structural problems once per scope; unique affected data rows are counted separately. | Investigator's occurrence-count requirement |
| Reference display | Show every cell reference for 1–9 occurrences; show none for 10 or more, including exactly 10. No detailed Excel tab bypasses this boundary. Full sanitized findings remain in audit JSON. | Investigator explicitly selected fewer than ten |
| Privacy and identifiers | Only workbook/sheet/cell locations identify records in reports. Defer identifier validation, normalization, matching and deduplication; omit source text/identifier values from reports and logs. | Investigator chose sheet/cell locations and deferred identifier work |
| Execution | Standalone and master entrypoints share checks. Publish valid reports even when quality fails; errors yield nonzero final exit, reviews alone do not. Independent cohorts continue. Default analysis profiles and downstream gating are unchanged. | Investigator's selected execution policy |

See [the integrity guide](data_integrity.md) and
[versioned rules](../configs/definitions/data_integrity.json). Historical and
current-source reports require separate source hashes; issue counts are not fixed
cohort expectations. The implementation snapshot is
`.maintenance/layer1_implementation_20261005T132145Z/` and excludes clinical data
and output artifacts.

## Explicit extraction state and unknown values — October 5, 2026

The investigator requested a single not-extracted status column and blank
extraction-dependent entries when extraction has not occurred. They confirmed
that an entered extraction method on such rows is incorrect, and explicitly
requested preserving numeric volume contradictions for review.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Status source | Move explicit `pas extrait`/`PAS EXTRAIT` notes from extraction_date to `extraction_status = not_extracted`. Add the shared column to both inventories, CIRCALL controls and template. Other rows remain unclassified; do not infer extraction completion from missingness or measurements. | Investigator's requested consolidation |
| Dependent text | Clear date/method and nonnumeric extraction-dependent annotations on explicitly not-extracted rows. Preserve the archived originals and cell-level change record. | Investigator confirmed the method/status combination is impossible |
| Numeric contradictions | Preserve every number, including 12 extraction-input volumes and one elution volume, and report `extraction_state_conflict`. Do not infer which numeric value or status is wrong. | Investigator selected “Preserve the numbers and flag conflicts” |
| Unknown marker | `?` means explicitly unknown. Retain this marker on other rows and report it in Coverage separately from missing, zero and not-applicable values; do not classify it as a malformed number/date. | Investigator clarification |
| Applicability | Approved derived calculations are not applicable for rows explicitly marked not_extracted. Still check recorded values/formulas and report contradictions or Excel errors. No scientific filtering is added to analytical workflows. | Consequence of the approved extraction-state definition |
| Preservation | Keep identifiers, numeric values and all formulas/caches unchanged, including formulas whose displayed result is blank. Keep sampling, tissue and collection metadata. | Investigator's deferred identifier scope and numeric preservation decision |

The helper `python -m analysis.extraction_status` takes explicit retrospective and
CIRCALL sources and writes fresh copies. Its
[correction report](../archive/results/compatibility_20261007T073346593956Z/spreadsheet/extraction_status_20261005/correction_report.json)
records the approved cell changes. Corrected workbooks were adopted into the
existing October 5 input paths; the prior sources are retained under
`archive/migrations/extraction_status_20261005/`, with hashes and paths in its
[relocation record](../archive/migrations/extraction_status_20261005/relocation.json).
Earlier report counts describe the prior source/rule hashes, not the corrected
inputs. Assay/protocol metadata outside the explicit correction remains unresolved.

## Contextual integrity reporting — October 5, 2026

The investigator clarified that identifying logic inconsistencies is the purpose
of Layer 1, including those on future/uncollected sample rows. Existing errors are
retained; reporting now distinguishes their category and context.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Future rows | Retain formula errors and artificial-zero errors on rows with blank CIRCALL sample IDs. Add the established future-visit context without inferring receipt or suppressing failures. | Investigator clarification |
| Not-extracted contradictions | A populated extraction-dependent value contradicts explicit not_extracted status and is a logic error. Keep all preserved numeric values; do not decide automatically which entry is wrong. | Investigator's inconsistency-checking purpose and earlier numeric-preservation instruction |
| Recognized annotations | Distinguish workflow notes, aliquot counts supplied in volume fields and written-unit measurements as specific review findings. No unit conversion or aliquot-volume inference is performed. | Investigator requested meaningful inconsistency reporting |
| Unknown versus contradictory | `?` remains explicit unknown in Coverage. Unknown alone is not a malformed measurement; formula errors caused by missing/unknown operands remain reportable. | Investigator's confirmed unknown-marker meaning |
| Counts and grouping | Retain all rule-occurrence counts; add distinct cell/row counts, categories and aggregate row context. Do not change grouping keys or the fewer-than-ten reference-display boundary. | Investigator's count requirement and contextual reporting clarification |

The existing source corrections were completed and archived before these reporting
changes. Reporting itself remains read-only. The earlier report outputs are kept
as evidence under their recorded source/rule hashes.


## Layer 2 patient identity revision — October 6, 2026

The investigator replaced the proposed opaque RETRO-ID migration with the existing
inclusion identifiers. The retrospective `inclusion_id` column is renamed
`patient_id`; existing values are authoritative and unchanged. For empty or literal
`na` cells, reuse an existing ID for the exact stored lastname–firstname–DOB tuple
when unambiguous; otherwise assign `unk-NNN-lastinitial-firstinitial`, continuing
after the highest existing number. Actual Excel DOB dates are compared by date;
spelling/case differences and text dates are not silently normalized. Conflicting
IDs or incomplete identities require review rather than speculative matching.

`analysis.patient_ids` performs this explicit correction with a fresh local backup,
cell-level ZIP patches and package/source verification. The October 6 application
filled 63 cells with 11 new IDs (numbers 006–016). The source and correction evidence
are under `archive/migrations/retrospective_patient_ids_20261006/`. Existing IDs,
name/DOB fields, other measurements, formulas and caches were preserved. Name removal
is a separate pending step; it must not run automatically during statistics.
Layer 2 uses recorded patient_id rather than deriving patients from names or requiring
a RETRO prefix. The former seven-group RETRO-code review proposal is superseded.

## Layer 2 descriptive statistics — October 6, 2026

The investigator approved the Layer 2 plan, subsequently replacing its RETRO-code
identity migration with the patient-ID revision above. Implemented as a separately
selected workflow; no legacy analysis/default profile is migrated implicitly.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Observation/population | One row per sample, patient counts from recorded cohort-qualified IDs; patients represented in the inventory, not a registry enrollment denominator. No row merging or patient weighting. Numbering-only rows excluded from sample counts and counted as skipped. | Approved Layer 2 plan |
| Identity/centers | Retrospective patient_id from inclusion IDs plus manually initiated unk IDs; all retrospective samples RDB. CIRCALL existing protocol IDs, 001 RDB / 002 TRS; unknown prefixes remain unknown. No cross-cohort linkage. | Investigator October 6 revision and planning answers |
| Gate | Run Layer 1 on current source hashes. Any error blocks the cohort; included controls belong to CIRCALL gate. Reviews permit execution. Both cohorts required for pooled results. | Investigator selected cohort-level error-free gate |
| Receipt | Present actual sample ID proves receipt; early receipt included in measurements but excluded from due percentages until planned date. | Investigator planning answers |
| Deadlines | CIRCALL diag/D4/D8/D15/TP1 only: midnight Europe/Paris plus 72 elapsed hours. Exactly 72 remains pending; later absence is missed. Future rows remain not due. | Investigator planning answers and approved plan |
| Manual fallback | With no reliable applicable date, literal na means missed; blank/? unassessed. Timing has priority before TP1. Retrospective has ID counts only, not expected/missed rates. | Investigator explicit na clarification |
| Denominator | Per displayed deadline/manual classification population: received + missed. Pending, future, early and unassessed excluded; all counts remain visible. Never pool receipt percentages. | Investigator planning answers |
| Measurements | Received samples only. Preserve zero, unknown, unavailable caches, intentional empty results and qualified text distinctly. No imputation/unit guessing/recalculation. Blank extraction status remains unclassified. | Approved plan |
| Statistics | Sample n, patient n, unavailable n, mean, n−1 SD, median, linear-interpolated quartiles, min/max. Sum only mass and volume. No inference or patient averaging. | Approved sample-summary choice |
| Pooling | Plasma and CSF extraction-input volumes separately; six plasma total-DNA/cfDNA concentration/mass/ng-per-mL endpoints separately. Shared diag/TP1/TP2 visits, visible cohort contributions. | Investigator metric-specific approvals |
| Other metrics | cfDNA fraction/size and other-specimen DNA cohort-specific; cellular/albumin fields stay distinguishable. Blood-volume analyses and retrospective elution-volume summaries excluded. | Approved plan, existing exclusions |
| Controls | Separate CIRCALL control descriptions, no patient receipt percentage or patient pooling. | Investigator control choice |
| Reports | Excel plus raw-scale sample distributions and receipt bars as PNG/PDF; pseudonymous missed checklist only. No names/DOB/free text. Blocked reports publish before nonzero exit. | Approved plan |

Prepared observations retain source-row locations and hashed subject keys for
reconciliation. Measurement figures label sample and participant counts, keep raw
scales and cohort colors, and do not imply calendar-equivalent visits or independent
samples. Sources and artifact publication checksums are reverified after execution.


## Available specimen volume correction — October 6, 2026

The investigator explicitly superseded the earlier extraction-input definition for
both inventories: plasma volume is available plasma after centrifugation, and CSF
volume is the available specimen volume. Neither indicates that extraction occurred.
The legacy header `extraction_input_volume_ml` remains for source compatibility, but
its definition and Layer 2 volume units now describe available specimen volume.
It is removed from extraction-dependent fields: a number on a not_extracted row is
valid, and an empty volume is missing rather than extraction-inapplicable.

Existing ng/mL formulas are retained, arithmetically dividing DNA mass by that
recorded available volume. The investigator subsequently confirmed that, when extraction occurs, the entire
recorded available volume is used; the existing ng/mL denominator is therefore
appropriate for extracted samples. Availability alone still provides no evidence
of extraction. No measurement, formula or extraction status was altered by this
definition correction.


## Retrospective controls included — October 6, 2026

The investigator identified `input/cfDNA_donors.xlsx` as the retrospective controls
and explicitly authorized their inclusion in Layers 1 and 2. Both run profiles
select this file, sheet `Feuil1`, through `donors`; the source is independently hashed.
Layer 1 checks its sparse schema and recorded numeric/formula fields, distinguishing
its source from Inventaire in the retrospective report. Its definite errors block
the retrospective scope when controls are selected; excluded controls do not gate it.

Layer 2 retains the established legacy mapping `Conc ng/mL  plasma` →
`dna_ng_per_ml_plasma` for plasma control descriptions. Each donor record supplies
a control observation, with distinct donor counts derived in memory from Donor.
Names/labels are never exported; audit identity keys are hashed. No sample-ID-based
receipt claim or scheduled receipt percentage is made for these records. Center,
visit schedule, extraction status, actual protocol volumes and other endpoints
remain unavailable, rather than being inferred from conversion constants.
Controls have their own tab/figures and remain excluded from patient summaries
and pooled patient results. Controls from the two cohorts are not pooled.


## Concentration plot display — October 6, 2026

The investigator requested logarithmic y-axes for all Layer 2 concentration plots.
The five concentration endpoints (DNA/cfDNA ng/µL and ng/mL, plus albumin ng/µL)
now use base-10 logarithmic axes in all cohort, pooled and control figures. This is
a display change: stored values and descriptive tables remain on the original scale.
Nonpositive values are counted explicitly but not placed on a logarithmic axis;
boxplots summarize positive values, with that restriction labeled on affected
figures. No pseudocount or analytical exclusion is introduced. Non-concentration
plots remain linear. Redundant internal group labels are removed from subtitles.

## Layer 3 diagnosis cfDNA associations — October 6, 2026

The investigator approved this first Layer 3 increment and its preparation changes
in the attached implementation plan. This is a separately selected read-only
`advanced_analysis` workflow, using harmonized sources and the existing association
statistical functions. The older `cfdna_associations`, canonical and normalized
kinetics contracts/defaults remain applicable to their established entrypoints.
Rules and mappings are versioned in `configs/definitions/advanced_analysis.json`
(`diagnosis-2`) and included in input/provenance hashes. These preparation and
pooling decisions are project-specific adaptations, not a claim of published-method
equivalence to clinical results prepared from different sources or identities.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Explicit sources | Retrospective cfDNA_inventaire_retrospective_05102026.xlsx / Inventaire; CIRCALL inventaire_CIRCALL_07102026.xlsx / cohorte_lal; optional integrity-only cohorte_control and explicit cfDNA_donors.xlsx / Feuil1. Shared raw/cached reader; no Layer 2 summary dependency, kinetics borrowing or modification-time selection. | Approved Layer 3 plan; investigator-selected October 7 CIRCALL update |
| Identity and diagnosis | Retrospective patient_id and CIRCALL circall_id, trimmed without case folding and qualified by cohort. Preserve recorded codes; no names/DOB fallback or cross-cohort linkage. Only timepoint=diag. Invalid diagnosis participant IDs are preparation errors. | Approved identity/diagnosis changes; existing Layer 2 identifier convention |
| Outcome receipt/filters | Present nonformula sample ID; blank, na, ? and configured missing/unknown tokens are not receipt evidence. Retrospective plasma + cfDNA + Roche with case-insensitive filtering; CIRCALL diagnosis plasma without added tube filter. No planned-date gate. | Approved receipt/filter changes |
| Endpoint and repeats | Recorded cfdna_ng_per_ml_plasma only. Uniformly select one eligible diagnosis plasma row with an available numeric outcome per patient, including zero candidates. Missing/unknown, qualified text and unavailable caches are not numeric candidates; negatives remain errors. If all outcomes are unavailable, select one eligible row for audit/metadata but retain an unavailable outcome. Use one selection across all predictors; never redraw for zero or incomplete clinical values. No imputation or endpoint recalculation. | Investigator approved random one-sample selection October 7, replacing patient-median aggregation |
| Sample selection | Shipped sample-selection-seed = 123, exposed in profiles and standalone CLI. Independent Python RNG per cohort-qualified patient, seeded with the configured seed, cohort and patient hash. Sort candidates by hashed cohort/patient/sample identity, using source row for identical-ID ties. Distinct-ID row reordering and unrelated patients do not change a selection. Selected rows/hashes remain local audit evidence; count unselected numeric samples separately. Repeated collections are not declared duplicate records. | Investigator-approved reproducible random selection; explicit implementation and privacy rules |
| Log eligibility | Positive selected outcomes and predictor-specific complete pairs. Count nonpositive outcomes and unavailable outcomes; no pseudocount or common complete-case restriction. Original-scale descriptions retain selected zeros. | Retained zero-handling rules applied to selected samples |
| Volume | extraction_input_volume_ml records available plasma/CSF; entire recorded volume was used when extracted. Recorded ng/mL remains appropriate; no recalculation and never blood_volume_ml as denominator. | Investigator's October 6 volume clarification |
| Sex/age | Retrospective selected diagnosis plasma row; missing selected values remain unavailable, without borrowing from other rows. Both unavailable in CIRCALL; age is not derived. | Sample-level pairing for approved one-sample selection |
| Subtype | Retrospective first nonmissing genetic_subtype across diagnosis; expose patient discordance counts. CIRCALL concordant diagnosis metadata; conflicts block. Recorded categories remain distinct; unknown/missing tokens unavailable. | Approved Layer 3 mapping and retained conflict rules |
| WBC | Retrospective GB_per_L on the selected diagnosis plasma row, with no cross-row fallback; CIRCALL concordant diag_blood_wbc_x10*9/L. Both confirmed ×10⁹/L in the shipped profile; CLI unit confirmation is recorded. No retrospective historical availability count is hard-coded. | Investigator-confirmed units; sample-level pairing for approved one-sample selection |
| Peripheral blasts | Retrospective cytology, falling back to cytospin_% only if unavailable on the same selected plasma row; no cross-row substitution. CIRCALL concordant diag_blood_blast_pct at diagnosis. Validate recorded numeric fractions in [0,1], multiply once by 100. A qualified unused fallback does not replace/invalidate valid primary cytology. | Existing tissue-specific fallback and clinical validation; pairing for approved one-sample selection |
| Marrow blasts | Retrospective diagnosis bone marrow cytology/cytospin median, joined by patient_id; CIRCALL concordant diag_bm_blast_pct. Same [0,1] validation and conversion. Receipt required for outcome only. | Existing marrow aggregation/matching, updated retrospective availability |
| Clinical validation | Missing/unknown clinical values remain unavailable. Malformed selected numeric annotations, nonfinite/negative values and fractions outside [0,1] block rather than silently becoming plausible measurements. | Approved validation safeguard |
| Deferred measurements | Absolute peripheral/marrow blast counts and hematocrit unavailable. No WBC × fraction derivation; Hb_g_per_dL is hemoglobin. | Investigator's explicit non-derivation rules |
| Primary models | Separate existing log10(cfDNA) ~ predictor ordinary least-squares regression; no patient random effect or mixed-effects model. HC3 continuous uncertainty, conventional categorical omnibus when selected, ordinary 95% intervals. Default family contains peripheral_blast_percent only; additional predictors require a later decision. | Existing statistical engine; approved Layer 3 plan; current primary predictor reconfirmed October 7 |
| Fit acceptance | Preserve ≥3 complete observations, ≥2 predictor values, ≥1 residual degree of freedom and finite standard-error/p-value checks. Unestimable fits have explicit skipped reasons and retain available points. | Existing fit_regression checks |
| Effect sizes/BH | Continuous fold change per 10 percentage points for blast predictors, otherwise per recorded unit. BH over configured predictor family within cohort; unavailable tests use p=1 for adjustment only, exported inference remains unavailable. No cross-cohort or study-wide correction. | Existing engine conventions |
| Descriptions/sensitivity | All six predictor views retained independently of testing. Descriptive log10 least-squares trends and Pearson/Spearman coefficients have no extra tests. Selected peripheral-blast Spearman uses existing two-sided asymptotic test, explicitly unadjusted secondary analysis. | Existing engine conventions and approved sensitivity |
| Pooling/controls | Both patient cohorts must complete; each predictor needs positive pairs in both cohorts with comparable units. Cohort colors retained; descriptive only, no pooled fit inference. Controls affect whole-cohort integrity only and never enter patient models or pooling. | Approved Layer 3 scope |
| Integrity/exit | Same whole-cohort Layer 1 checks as Layer 2, including selected control sources. Reviews permit execution; errors block only affected cohort. Publish available aggregate/blocked reports before final nonzero on structural, data-quality or execution failures. Unavailable predictors/fits are limitations, not failures. | Approved independent-cohort gate and publication requirements |
| Presentation/privacy | Excel 2021-compatible literal aggregate workbooks with six tabs; original ng/mL on log y-axes; WBC and marrow blast percentage comparisons also use log x-axes. Nonpositive predictor values are counted but omitted from the log display only, retained in models/tables; no pseudocount or log-predictor model transformation. Back-transformed log10 fits/CIs. Categorical boxes calculated on log10 scale before coordinate transformation. No source identifiers, names/DOB or notes in engine result frames; hashed row evidence/coordinates and residual diagnostics local under .audit. | Approved reporting/privacy requirements; investigator-requested log–log WBC and marrow blast percentage displays, October 6, 2026 |
| Determinism/provenance | Separate seeds for sample selection and categorical display jitter. Record resolved selection seed in options and report definitions, source/definition/rule/code/lock hashes, actual package versions, command, ISO execution timestamps and publication checksums; verify source bytes after execution. Fresh destinations only. | Existing shared provenance; approved random-selection reproducibility |

The October 7 review confirmed diagnosis-only scope and the current primary
peripheral blood blast percentage association, with additional predictors deferred.
The investigator subsequently approved selecting one diagnosis sample at random,
replacing patient-median aggregation while retaining ordinary regression and the
secondary patient-level Spearman analysis. This gives each patient one observation
and preserves the selected plasma row's clinical pairing, but discards repeats from
inference and introduces dependence on the selected seed. Do not select a primary
seed by inspecting statistical significance. Inference using all repeats, mixed
models and dependence-aware correlation testing remain deferred scientific choices.

The scoped pre-change implementation snapshot is
`archive/migrations/layer3_before_20261006T100400Z/implementation_before.tar.gz`,
with file hashes and Git HEAD/status. It excludes clinical data and outputs.
Rollback requires reviewing subsequent edits and restoring only affected
implementation files; preserve all inputs, runs and the snapshot. No dependency,
environment-lock, legacy entrypoint/default or clinical-workbook change is included.

## Layer 4 disease tracking — October 6, 2026

The investigator approved implementation of the descriptive first release in
the [Layer 4 plan](layer4_implementation_plan.md), requiring self-contained
scientific methods so old helper modules can later be archived. Layer 4 therefore
owns its MRD parser, repeat resolution, count preparation, summaries and plotting;
it uses only retained shared infrastructure. Method-origin hashes and an identical-
observation synthetic reference record the port. Existing canonical/normalized
entrypoints remain separately available. No clinical source was corrected.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Scope and sources | Descriptive MRD and recorded blood counts, using explicit October 5 inventories, the October 1 CIRCALL count workbook and active retrospective blast workbook. Selected CIRCALL and donor controls affect inventory integrity only. No Layer 2/3 results consumed; no normalized fit or disease inference in this release. | Investigator-approved Layer 4 plan and self-containment instruction |
| MRD identity and selection | Retrospective patient_id, timepoint TP1/TP2, specimen_type bone marrow, MRD_IgTCR; CIRCALL circall_id with MRD_TP1/TP2 metadata across identified records. Recorded IDs trimmed without case folding and qualified by cohort. No name/DOB fallback, sample receipt or cfDNA outcome restriction. | Approved harmonized field/recorded-ID migration |
| MRD populations | Retrospective identified selected patient/visit groups, including missing annotations; CIRCALL patients with at least one nonmissing clinical follow-up result. Report source population/availability separately; do not substitute an enrollment roster or force a common complete-case population. | Retained source-specific methods |
| MRD values | Quantitative fractions strictly greater than zero and at most 1; negative remains categorical. Missing/unknown markers, intentional empty formulas and unavailable caches remain unavailable and distinguishable. Unknown source marker is distinct from clinical uncertain significance. Invalid fractions, numeric zero and unsupported clinical annotations block the cohort. | Retained clinical checks plus approved harmonized unavailable-state handling |
| Retrospective MRD repeats | Identical repeats collapse; default numeric > positive NQ > negative, then highest numeric fraction or highest bound within category. Count resolved disagreements. Optional error policy preserves strict conflicts. Bounds never become measured fractions or measured log reductions. | Previously approved retrospective method, now implemented locally |
| CIRCALL MRD categories | Retain quantified, negative, uncertain significance and missing; nonmissing conflicts block. CIRCALL positive nonquantifiable annotations remain unsupported and block the cohort pending source review. No automatic category extension or source rewrite. | Investigator explicitly chose Keep CIRCALL blocked pending source review during implementation |
| MRD displays | Cohort negative assigned 1e-8 and uncertain significance assigned 1e-6; source/pooled diagnosis reference 1 is assumed, not measured. Retrospective positive NQ displayed at a reported bound, unbounded results counted without positions. Pooled positive NQ assigned 1e-6. Settings exposed in CLI/profile; measured, bounded and assigned values remain separate. Jitter seed 42 by default. | Retained display conventions; versioned Layer 4 definition and shipped profile |
| MRD connections and pooling | Retrospective lines connect quantified pairs only. CIRCALL/pooled dotted segments touch negative/uncertain assigned levels; missing visits and positive NQ are not bridged. Compatible pooling uses fixed union of retained source-specific MRD populations and nominal Diagnosis/TP1/TP2, no shared calendar-day claim or inference. Retain prior displayed status grouping and hidden missing segments; tables retain all categories and fixed denominators. | Approved MRD trajectory and pooled display methods |
| Count identity | CIRCALL recorded circall_id; retrospective trimmed, case-sensitive surname within count source only, represented by a source-qualified hash in memory. Retrospective surname collisions remain a limitation. No count-to-inventory MRD or cross-cohort linkage, registry intersection or global summed patient denominator. | Approved isolated compatibility basis; no new name matching |
| Count units and validation | Recorded blast/WBC counts in explicitly confirmed ×10⁹/L, no WBC × fraction derivation. Retain genuine zero; reject negative/nonfinite counts, missing/invalid measured days and duplicate measured subject/day/measurement rows. Unknown/empty/cache-unavailable counts remain unavailable; saved source dates and coordinates retained in memory without day recalculation. Retrospective longitudinal WBC unavailable. | Retained count rules plus approved source-state distinction |
| Count summaries and display | Source-row-weighted descriptive mean/median/range and observation/patient/availability counts; no patient averaging or inferential uncertainty. Record all measured days. Diagnostic display defaults to latest recorded day ≤1, without changing stored values/days. Full recorded-range and separate through-day-8 views have explicit counts; windows never globally filter source summaries. | Existing diagnostic selection and approved full-range presentation addition |
| Count axes and comparison | Linear recorded-day x-axis and log y-axis by default, explicit linear option. Zeros counted but omitted on log display; lines break at zero; no pseudocount or invented floor. Joint blast figures retain separate cohorts and denominators; no pooled count summaries or fit. | Retained count display and comparison rules |
| Integrity and errors | Whole-cohort inventory check including selected controls plus selected clinical/count checks. Reviews permit execution; errors block the affected cohort. Valid empty analyses are unavailable, not execution failures. Full execution publishes independent and blocked reports before final nonzero on quality/infrastructure failure. Validate-only reports definite errors without publishing; the later unified-orchestration amendment below governs the all-layers launcher. | Approved Layer 4 gate and independent reporting semantics |
| Privacy and validation | No MRD/count patient tables, even hashed, exported under audit or visible results. Names, DOB, identifiers and notes remain out of logs, filenames, workbooks and figures. Validation reconstructs observations in memory from explicit hashed sources; aggregate reports, literal workbook values and artifact publication checksums must reconcile. | Retained stricter disease row-export restrictions and investigator-approved archival objective |
| Provenance and dependencies | Record settings, source/definition/method/code/lock hashes, actual package versions, commands and ISO execution timestamps. Explicit retained-file code hashes and isolated tests verify operation without legacy scientific directories. Fresh destinations and source hashes are rechecked. Shared Conda files relocated during implementation to environments/ with unchanged bytes/dependencies. | Existing audit infrastructure and self-containment instruction; relocation verified against checkpoint |

The implementation snapshot is
`archive/migrations/layer4_before_20261006T134427Z/implementation_before.tar.gz`.
It includes relevant existing/untracked implementation files and excludes clinical
inputs and outputs. Restore only reviewed affected files after checking later edits;
retain sources, runs and migration evidence. The environment relocation was observed
during this task and preserved; active path references were adjusted without lock
regeneration. Future normalized modeling requires a separately selected increment
and a local implementation consistent with the self-containment requirement.

## Unified layered orchestration — October 6, 2026

The investigator requested one layered run manifest and explicit independent
failure handling while preserving the CIRCALL MRD hold. This amendment supersedes
the shell launcher's earlier preflight-all/stop-on-first-quality-failure policy.
It changes dispatch and reporting scope, not cohort eligibility, source selection,
clinical interpretation, pooling, statistical settings or the hold itself.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Selection | `run_all_layers.sh` invokes `run.py --config configs/pipeline_layers.json` once, selecting Layers 1–4 in order. Combined options match the existing individual profiles, checked by a parity test. The later default-cutover amendment below governs plain `run.py`. | Investigator's unified-orchestration instruction; existing integrated runner |
| Run identity and location | One root manifest with unique run ID, resolved configuration, per-layer execution and quality states, source/code/launcher hashes, native evidence and publication index. New default is `outputs/layered/run_<timestamp>/`; explicit CLI output takes precedence over configured output, then the default. Existing destinations are refused. Single-layer and historical destinations remain unchanged. | Requested unified manifest; existing publication safeguards |
| Preflight infrastructure | Validate configuration, worker availability and source-state metadata before execution. A malformed configuration, unavailable worker or invalid preflight record aborts before creating execution outputs. No resume is introduced. | Existing integrated preflight safety boundary |
| Preflight quality | Preserve each layer's established preflight depth. Layers 1–3 preflight does not certify whole-cohort clinical validity; execution performs their gates. Layer 4 reports clinical quality during preflight. `--validate-only` publishes nothing and returns nonzero on known quality errors; it does not launch a full run. | Existing layer contracts; truthful validation scope |
| Full execution and holds | After successful infrastructure preflight, reported quality holds do not prevent full execution. Each layer applies its unchanged cohort gates and publishes validated independent/blocked reports. The CIRCALL MRD hold still blocks its Layer 4 cohort and dependent pooling/comparisons; it does not suppress Layers 1–3 or clean retrospective disease reports. | Investigator requested preservation of the hold and unified failure handling; existing independent-report contracts |
| Failure continuation | A worker, validation or publication failure marks that workflow failed and preserves available audit evidence; subsequent independent workflows are still attempted. A report-complete workflow may retain `quality_status: errors_found`. Any selected failure or quality hold makes the overall run failed with nonzero exit. Unavailable analyses in valid sources remain limitations. | Existing integrated runner semantics extended to the all-layers command |
| Changed sources and interruption | Recheck source/configuration hashes before and after work and at finalization; changed inputs invalidate affected workflows or the configuration/run. An interrupt stops execution, terminates the active worker group and marks remaining workflows not run. No successful final status may conceal these events. | Existing provenance and interruption safeguards |

The pre-change implementation and documentation checkpoint is
`archive/migrations/unified_layers_before_20261006T152102522851Z/`.
Rollback restores only reviewed affected files after checking subsequent changes;
retain all historical and partial runs. Synthetic acceptance covers a successful
four-layer invocation and one with the CIRCALL-style MRD hold, using the actual
shell command in an isolated repository without older scientific packages.
Failure tests also cover worker errors, changed sources, interruption and
preflight infrastructure errors. No clinical annotation or source workbook was
changed to make the all-layers command complete successfully.

## Layered default cutover — October 7, 2026

The investigator authorized making the unified layered pipeline the default and
aligning current documentation and repository instructions. This supersedes the
October 6 orchestration amendment's retention of the old implicit default.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Default selection | Plain `python run.py`, including integrated `--validate-only` and `--output-dir` usage without a profile, selects `configs/pipeline_layers.json`. It agrees with `run_all_layers.sh`: Layers 1–4, one run identity and manifest under `outputs/layered/`. | Investigator-authorized default cutover |
| Scientific scope | The selected layered profiles retain their existing inputs, identities, measurements, thresholds, models and controls. This default changes which established workflows are selected; it does not assert equivalence to the older combined results or migrate missing capabilities. | Existing layer contracts and replacement coverage |
| Compatibility | `--config configs/pipeline_all.json` explicitly selects the former combined default with unchanged options and sources. Existing individual profiles, workflow IDs and direct analysis flags remain supported, including canonical routing for older flags without `--config`. No older package is archived or retired. | Investigator required compatibility until validated migration |
| Failure and publication | Preserve unified failure handling, fresh destinations and the CIRCALL MRD hold. Validate-only reports known holds without publication; full execution preserves independent results and blocked reports with a nonzero overall result. Single-layer and historical locations are unchanged. | Unified layered orchestration contract |

The pre-change checkpoint is
`archive/migrations/layered_default_before_20261007T065636726624Z/`.
Rollback restores only reviewed changed implementation/documentation files after
checking subsequent edits; profiles and clinical sources are unchanged. Planned
longitudinal, correlation and combined-panel migrations remain outstanding as
recorded in [replacement coverage](replacement_coverage.md).

## Shared sample annotations and receipt revision — October 7, 2026

During the layer-by-layer review, the investigator requested deriving extraction
from DNA-ID presence, simplifying missing annotations, restricting available volume
to plasma/CSF and reversing receipt deadline logic. These are project-specific
scientific definitions. The request to make these adjustments includes the
preceding cross-layer corrections; statistical models remain unchanged.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Extraction basis | An actual filled `dna_id` means yes; blank or a recognized missing/unknown marker means no. Missing DNA-ID columns, formula IDs and Excel errors remain unassessed. Recorded `extraction_status` is refreshed to yes/no in selected sheets and derived again during Layers 1/2; explicit conflicting yes/no labels are logic errors. No inference from measurement values. | Investigator: “you just check if dna_id is filled” |
| Extraction applicability | For derived no, extraction-dependent recorded values remain logic errors and arithmetic checks are inapplicable. Available plasma/CSF volume remains independent of extraction. Preserve measurements rather than deciding which conflicting entry is correct. Donors without DNA IDs have unavailable extraction classification. | Revised basis and retained contradiction-preservation rule |
| Canonical annotations | Exact literal `na`, `n/a`, `none`, `nan`, `-`, `sk`, `?`, including case/outer-whitespace variants, become `na` in selected inventories/template/controls and donors. Blanks, numeric values, formulas and caches remain unchanged; names/DOB and actual IDs are preserved. This intentionally collapses literal unknown and missing annotations in adopted sources; original distinctions remain recoverable from backups. Historical parser aliases stay readable. Other clinical annotations, including MRD uncertain significance and unsupported positive-NQ categories, remain unchanged. | Investigator requested “na” for all selected markers |
| Receipt evidence | Actual sample ID means received. Literal `na` alone establishes explicit missingness. Blank or other noncanonical unavailable IDs remain unassessed; an elapsed deadline alone cannot establish missingness. After adoption, previous literal missing/unknown markers become explicit `na` under this convention. | Investigator requested missingness first, then timing |
| Overdue window | Only explicit `na` on CIRCALL diag/D4/D8/D15/TP1 rows with a real planned date becomes missed after more than 72 elapsed hours from midnight Europe/Paris. Exactly 72 remains pending; before the planned date it is not yet due. An inapplicable/unavailable date leaves `na` marked missing with lateness unassessed. Retrospective retains ID-based counts without scheduled receipt rates. | Requested reversal; existing visit scope, clock and boundary retained |
| Receipt denominator | Received + overdue missed within classification basis. Undated marked missing, blank/unknown, pending, future and early receipt remain visible but outside that denominator. No pooled receipt percentage. Formula-quality checks remain independent. | Consequence of revised missingness rule and retained denominator convention |
| Specimen volume | Available volume applies only to plasma and CSF in integrity semantics and descriptive measurements. Other specimen rows remain preserved and their volume checks are unavailable. Plasma ng/mL calculations still apply only to plasma. | Investigator: “this should only be for csf and plasma” |
| Total amount | `cfdna_total_ng` is total amount of cfDNA in the extract, in ng; retain fraction × total DNA amount. Definitions change, not values or units. | Investigator clarification |
| Later layers | Layers 3/4 receive amended integrity gates and canonical source markers; their outcome receipt, MRD selection, models, units and hold remain as defined. No sample-receipt/extraction filter is added to clinical MRD. | Cross-layer scope request and retained clinical eligibility |
| Preservation and Git | Verify explicit sources; prepare original backups and all patched copies before adoption. Reverse patches reproduce original ZIP members. Keep clinical files/results/archive outside Git; preserve dirty tracked/untracked implementation before edits. No reset/clean or remote publication. | Repository safeguards and investigator request to verify Git use |

Canonical `na` denotes an unavailable value; it alone does not establish
measurement inapplicability. Layer 2 derives inapplicability from extraction or
specimen context, including keeping unavailable available-volume entries missing
independently of extraction status.

The pre-change implementation checkpoint is
`archive/migrations/shared_rules_before_20261007T081707606067Z/`, containing 195
code/configuration/documentation/test/environment files with hashes, HEAD, status
and tracked/staged diffs, excluding clinical data, credentials and outputs.
Use `conda run -n pre_analysis python -m analysis.sample_annotations
--retrospective <inventory.xlsx> --circall <circall.xlsx> --donors <donors.xlsx>
--output-dir <fresh-migration-folder> [--adopt]` with the explicit versioned
`configs/definitions/sample_annotations.json` selection. Originals are separately
backed up under that destination. Rollback requires reviewing later edits and
restoring only affected implementation/source files from their checkpoints.
Retain existing results and migration evidence.

## CIRCALL control/template formula repair — October 7, 2026

The investigator requested repairing equations on `cohorte_control` and
`template` in the selected October 5 CIRCALL workbook. Explicit sheet selection
in `analysis.repair_inventory_formulas` repairs existing five-endpoint DNA/cfDNA
formulas regardless of current cached quality. Use the approved operand columns,
numeric-input guards, positive plasma-volume denominator and plasma-only ng/mL
scope. Genuine measured numeric values and nonformula blanks remain untouched.
Template planned-date/day expressions retain their recorded references, offsets
and day-one convention, with numeric Excel-date guards to avoid invented results
when dates are unavailable. No treatment schedule or clinical interpretation is
changed, and the patient sheet remains byte-identical.

The command is `conda run -n pre_analysis python -m analysis.repair_inventory_formulas
--circall input/inventaire_CIRCALL_05102026.xlsx --sheets cohorte_control template
--output-dir <fresh-migration-folder> --adopt`. Omission of `--sheets` retains the
older defect-row correction scope. Original workbooks are backed up; unchanged
cells/caches/extensions are verified. Edited formula caches are cleared and Excel
is instructed to rebuild its calculation chain; open, recalculate and save in
Excel before relying on derived results. No calculated cache is invented by Python.
The implementation checkpoint is
`archive/migrations/control_template_formulas_before_20261007/`; it records
pre-change HEAD and the affected helper/test/contract hashes and excludes clinical
data. Source backups and correction/validation records stay outside Git.

## Layer 2 measurement and pooled display review — October 7, 2026

The investigator requested excluding albumin/DIN, combining pooled plot bins,
and pooling cfDNA fragment sizes during Layer 2 review. These changes supersede
the corresponding measurement/display rows in the October 6 Layer 2 contract.
The investigator then confirmed three receipt labels plus a separate overdue
flag, and moving center detail to audit evidence. Worksheet/content redesign
remains explicitly deferred until after these modifications.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Metric exclusions | Remove `MNC_albumin_ng_per_uL` and `MNC_DIN` from Layer 2 metrics, tables, availability summaries and figures. Preserve source values and original Layer 1 integrity scope; other DNA measurements remain selected. | Investigator: “exclude these” |
| Pooled bins | One combined distribution per metric and nominal visit, using all eligible samples from both cohorts. Cohort-colored points share the bin and retain a legend. Concentration boxes use positive values under the retained log display; tables retain genuine zeros. Metrics/units and specimens remain separate. No new inferential model or patient averaging. | Investigator: pooled endpoints are plotted together, not in separate bins |
| Fragment size | Extend pooled `cfdna_avg_size_bp` to plasma and CSF separately, using the existing shared diag/TP1/TP2 visits and received-sample rules. Within each specimen, combine cohort contributions even when DNA-type metadata are unavailable in one cohort; do not impute metadata. Retain cohort-colored points and contribution counts. | Investigator explicitly requested merged fragment sizes with clear cohort colors; existing metric specimen/visit scope |
| Receipt categories | Received (actual sample ID), Marked missing (literal na), Unassessed (blank/unknown ID). A separate overdue flag requires the retained applicable CIRCALL visit/date and more than 72 elapsed hours; exactly 72 is not overdue. Early/future/pending timing remains recorded in audit observations, without extra receipt categories. Measurements still include early received samples. | Investigator confirmed “three labels plus overdue flag” |
| Timed percentages | Only reliable applicable timing supplies rates: due received + overdue missing. Early receipt, pending/future marked missing and unassessed receipt stay outside that denominator. Untimed rows show counts only, fixing the former received-only 100% manual rate. Main receipt rows distinguish all-category counts from assessed numerator/overdue counts. | Confirmed retention of the timed denominator; earlier review identified undated 100% issue |
| Main grouping | Inventory/receipt counts show one overall total plus specimen-by-visit breakdown; measurement summaries show metric/specimen/visit with existing applicable DNA-type distinctions. Full previous center and overlapping views, plus pooled cohort contributions, remain under `tables.audit_detail` in native statistics JSON. Audit observations retain source metadata. These details are excluded from visible workbook rows; source population and sample weighting do not change. | Investigator confirmed moving center detail to audit evidence |
| Reports | Preserve current worksheet selection pending the requested worksheet-by-worksheet review. Do not infer a full workbook redesign from measurement/plot changes. | Investigator requested report review after other modifications |

The scientific settings are versioned as `sample-statistics-3` in
`configs/definitions/sample_statistics.json`. The pre-change scoped implementation
snapshot is `archive/migrations/layer2_simplification_before_20261007T110719Z/`;
it records the affected file hashes and Git HEAD/status without clinical inputs,
outputs or credentials. Original measurements, identity rules, integrity holds,
controls, model scope and historical results are preserved.

## Audited October 7 CIRCALL equation correction

After the read-only audit of the investigator-selected
`input/inventaire_CIRCALL_07102026.xlsx`, the investigator explicitly requested
fixing the file. The audit identified 504 incorrect patient-sheet equations and
983 unguarded date formulas; 208 day results had unavailable source dates.

| Rule | Decision and rationale | Source |
| --- | --- | --- |
| Scope | Restrict edits to the cell locations in an explicit equation audit whose input hash matches the current workbook. Preserve all other formulas, measured numeric values, identifiers, metadata and sheets. Archive the original before adoption and verify reverse XML patches and reopened cells. | Investigator request to fix the audited file; existing preservation safeguards |
| Derived endpoints | Replace the 168 incorrect DNA ng/mL formulas with guarded mass/plasma-volume division; replace 84 cfDNA amount and 84 cfDNA ng/mL formulas with fraction × the corresponding total-DNA endpoint. Use the approved operand headers and plasma applicability. | Approved five-equation contract and audited wrong operands |
| Assay fields | Clear only the 84 recognized, audited fraction formulas and 84 fragment-size formulas whose caches are blank and whose derivations have incompatible units. Leave missing cells rather than inventing fraction/size measurements. Existing numeric assay observations remain unchanged; the original invalid formulas remain in the backup and correction log. The opt-in clearing flag requires a source-matched audit. | Investigator authorized correction following explicit audit findings; assay definitions |
| Dates | Add numeric-input guards to the 436 planned-date and 547 treatment-day expressions, retaining references, offsets and day-one convention. Do not infer collection dates or retain derived day caches when source dates are unavailable. | Requested repair of audited equations; existing missing-date safeguards |
| Unchanged assumptions | Retain the control/template formulas already verified and the auxiliary subtype weighting expressions. Their fixed 85%/15% scientific assumptions remain outside this repair's validation. Retain extraction-status/data-quality gates; equation correction does not resolve missing IDs or conflicting methods. | Audited scope and no unsupported scientific changes |

Run the existing repair CLI with `--sheets cohorte_lal --audit <equation-audit.json>
--clear-invalid-assay-formulas --adopt`, explicit `--circall` and a fresh
`--output-dir`. Edited formula caches are cleared and Excel is instructed to
recalculate. Open/recalculate/save in Excel before consuming derived results.
The pre-change code/test/contract snapshot is
`archive/migrations/circall_oct7_repair_before_20261007T115811Z/` and excludes
clinical data and outputs. The original workbook and correction evidence are
retained separately under the source repair destination, outside Git.

## Layered CIRCALL inventory selection — October 7, 2026

The investigator explicitly selected `input/inventaire_CIRCALL_07102026.xlsx`
for the four-layer rerun. After the older October 5 file was removed locally,
`./run_all_layers.sh` still selected its missing path. The combined layered
profile and four individual layer profiles now explicitly select the requested
October 7 workbook, preserving combined/individual parity. The October 7-specific
profile remains reproducible; earlier manifests and runs remain unchanged.
Retrospective, donors and count sources, matching rules, models, thresholds,
quality holds and output policies remain as defined. No modification-time source
selection or quality-gate bypass is introduced. The scoped pre-change profile/
documentation checkpoint is
`archive/migrations/layered_inventory_selection_before_20261007T120922Z/`.

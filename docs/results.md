# Read layered results

Start with `<run>/.audit/run_manifest.json`. It distinguishes report completion,
blocked cohorts and failed work. A workbook can validly report a quality hold;
its presence alone does not establish a successful analysis. The
[audit guide](audit_guide.md) explains validation, logs and artifact hashes.

| Layer folder in a combined run | Workbook per available cohort/scope | Detailed interpretation |
| --- | --- | --- |
| `01_data_integrity/` | `integrity_report.xlsx` | [Integrity findings and coverage](layers/data_integrity.md) |
| `02_sample_statistics/` | `statistics.xlsx` | [Receipt, DNA measurements and participant comparisons](layers/sample_statistics.md) |
| `03_advanced_analysis/` | `associations.xlsx` | [Diagnosis associations](layers/advanced_analysis.md) |
| `04_disease_modeling/` | `disease_modeling.xlsx` | [MRD and recorded counts](layers/disease_modeling.md) |

Every new run uses the four numbered layer folders above. Historical single-layer
runs may have cohort/scope folders directly under their root; readers retain support.
Only selected, available scopes publish. Source/audit evidence and logs remain
under `.audit`; existing results are never reorganized by the configuration layer.

## Figure presentation

New plots omit titles, subtitles and descriptive footers. Axis labels, units,
legends and in-panel data/statistical annotations remain. Calendar-volume exclusion
counts are retained immediately below their legend. Pooled plots show total
n for the plotted group or visit, without cohort-specific count labels or a second
participant-count label. Cohort colours and markers remain identifiable. The
observation unit is unchanged: sample plots count samples, patient analyses count
patients. Workbook tables and detailed audit counts are unchanged. Interpretive
caveats and statistical details remain in the workbooks and guides below.

## Questions and limits

All active plot exporters use 12-point Arial for axes, ticks, legends and data
annotations, with at least 18 points between the lowest axis content and legends.
Arial must be installed on the rendering system. Titles and descriptive footers
remain omitted; existing result files are preserved rather than rewritten.

DNA and cfDNA per-mL plots with timepoints on the x-axis share the same visual
style and visit labels: Diagnosis, D4, D8, D15, TP1 (D29) and TP2 (D71), where
those visits are selected. Each endpoint retains its existing visit eligibility,
controls, sample counts and statistical tests.

Layer 1 identifies structural, formula and interpretation problems. Definite
errors hold affected cohorts; review findings remain visible. Its occurrence
counts are not counts of unique patients or samples.

Layer 2 reports sample receipt and recorded measurements. Sample summaries retain
their observation unit. The separately approved DNA-per-mL comparisons reduce
repeats to participant medians, use the configured independent/paired methods,
and apply Holm correction within their defined families. They do not implement
the older longitudinal mixed model. Read [comparison details](layers/sample_statistics.md#comparing-controls-and-timepoints)
before interpreting stars, repeated visits or pooled controls.

Layer 3 selects one reproducible diagnosis plasma sample per patient and analyzes
the enabled cohort/outcome/predictor pairs. Its approved matrix has 61 switches
across five outcomes; missing or unestimable comparisons remain unavailable.
Primary p-values are unadjusted under the current contract. Continuous regressions
use HC3 uncertainty; categorical comparisons use the approved omnibus method.
Pooled views are descriptive. Arithmetic dependence among DNA endpoints and
handling variables, sparse observations, sample selection and confounding limit
interpretation. This differs from the older single-primary-predictor workflow.

Layer 4 describes MRD and recorded blood counts with distinct populations and
identity boundaries. It does not link those populations or normalize measured
counts to baseline. Assigned MRD display levels are not measured quantities.
The former positive-NQ category hold was superseded by the October 8 amendment;
invalid annotations, invalid sensitivities and conflicting metadata still impose holds.

Longitudinal mixed models, bootstrap trajectories, combined yield/WBC panels and
normalized kinetics are [historical functionality](replacement_coverage.md).
They are archived and require a separately scoped addition before future use. Scientific decisions and limitations remain in
[the contracts](workflow_contracts.md).

## Point symbols

In CIRCALL-only figures, orange triangles identify TRS and orange squares identify
RDB, using the established center mapping in the
[Layer 2 definition](../configs/definitions/sample_statistics.json). Unknown centers
use orange circles. Retrospective-only points are blue with their existing shapes.
Pooled and cohort-comparison marker conventions remain unchanged. In CIRCALL MRD
trajectories, shape identifies center; assigned vertical levels, hollow uncertain
results and line styles retain their clinical display meanings. Positive NQ remains
counted without a numerical position.

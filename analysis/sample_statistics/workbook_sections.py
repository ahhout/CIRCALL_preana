"""Worksheet data shared by Excel export and independent row reconciliation."""
from dataclasses import dataclass
import json

from .labels import MEASUREMENT_LABELS, RECEIPT_LABELS
from .report_records import display_order, display_timepoint, inventory_records, measurement_records


@dataclass
class Section:
    records: list
    empty: str = 'No applicable observations'
    title: str | None = None
    hidden: tuple = ()

    def rows(self):
        return self.records or [{'Status': self.empty}]

    def headers(self):
        return list(dict.fromkeys(key for row in self.rows() for key in row))


def cell_value(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def status_text(result):
    return f'Status: {result["status"]} | Assessment: {result["metadata"].get("assessment_time", "Unavailable")}'


NOTES = [
    ('Observation unit', 'One inventory row is one sample. Repeats are retained; patients are counted distinctly within each view.'),
    ('Population', 'Patients represented in the inventory, not a verified enrollment roster. Main counts show the overall total, center totals and specimen/timepoint breakdown. These views overlap; never sum across them.'),
    ('Receipt', 'Three labels: Received, Marked missing (literal na), Unassessed (blank/unknown ID). Overdue is a separate flag, not another receipt category. Early receipt is excluded from timed percentages until the planned date.'),
    ('Deadline', 'Diagnosis/D4/D8/D15/TP1 only. Planned date midnight Europe/Paris, then 72 elapsed hours. Exactly 72 hours remains pending.'),
    ('Fallback', 'Without a reliable applicable planned date, literal na remains marked missing with lateness unassessed; it is excluded from the overdue percentage denominator.'),
    ('Overdue status', 'Overdue unreceived samples are Marked missing when explicitly na, otherwise Late. Late is a follow-up flag while receipt remains unassessed. Both require reliable applicable CIRCALL timing beyond 72 hours; future, untimed and retrospective records are not flagged.'),
    ('Percentage', 'Timed received / (timed received + overdue explicitly marked missing). Late remains outside this denominator; it is not confirmed missingness. Future/pending/unassessed/early rows stay excluded. Marked-missing percentages refer to the overdue subset, not all na rows.'),
    ('Retrospective', 'ID-based receipt counts only; no expected-sample rates. All retrospective samples are attributed to RDB.'),
    ('Assessment', 'Current workbook snapshot evaluated at the recorded assessment timestamp; not reconstructed historical receipt.'),
    ('Extraction', 'Derived from dna_id: filled actual ID means yes; blank/missing ID means no. Missing columns, formula IDs and Excel errors are unavailable. Recorded measurements do not substitute for a DNA ID.'),
    ('Missing annotations', 'Canonical literal marker na means unavailable. Applicability comes from extraction/specimen context. Empty cells and formulas remain unchanged; historical aliases remain readable.'),
    ('cfDNA total amount', 'cfdna_total_ng is the total amount of cfDNA in the extract, in ng.'),
    ('Quantities', 'Received samples only, including early arrivals. Genuine zero retained. No imputation or Excel recalculation.'),
    ('Volumes', 'The legacy extraction_input_volume_ml field records available plasma after centrifugation or available CSF, independently of extraction status. For extracted samples the entire recorded available volume was used. Plasma and CSF remain separate.'),
    ('Calendar volumes', 'Additional CIRCALL plasma/CSF available-volume plots use recorded collection dates, received samples and individual sample points. Genuine zeros remain. No planned-date substitution, time jitter, smoothing, tests or performance thresholds. Missing volume and missing collection-date exclusions are reported separately; dates remain local audit metadata.'),
    ('Mass and concentration plots', 'Logarithmic y-axis in original units for DNA/cfDNA total ng and concentrations in ng/µL and ng/mL. Nonpositive observations are counted but not plotted; boxes use positive values. Tables retain genuine zeros, with no pseudocount.'),
    ('Summaries', 'Sample-based mean, sample SD (n-1), median, linearly interpolated quartiles, min/max. Totals only for mass/volume.'),
    ('Pooling', 'Plasma DNA endpoints, plasma/CSF available volumes and cfDNA fragment size; shared diag/TP1/TP2 timepoints in tables. DNA-per-mL patient figures show only Diagnosis, D4, D8, D15, TP1 (D29) and TP2 (D71), including single-cohort timepoints. Validated selected CIRCALL and retrospective controls share one Controls reference bin before Diagnosis. Specimens stay separate. One combined box per metric/timepoint, or across eligible timepoints for overall-display metrics, with cohort-colored points; tables retain cohort contributions.'),
    ('Excluded measurements', 'Albumin concentration and DNA integrity number are excluded from Layer 2 descriptions and plots; original source fields remain preserved.'),
    ('Retrospective donor mapping', 'Donor workbook plasma ng/mL endpoint maps to dna_ng_per_ml_plasma, preserving the established workflow. Other metrics and timing metadata are not inferred. Controls are inventory records, not an assessed scheduled-receipt population.'),
    ('Controls', 'Separate descriptive reference; excluded from patient counts, receipt percentages and patient pooling.'),
    ('Unknown categories', 'Unapproved timepoint/specimen labels are unclassified; no unrestricted source text is exported.'),
    ('DNA-type metadata', 'The legacy assay key records nucleic_acid labels, not a measured assay identity. not_recorded means that label is unavailable, not that the DNA measurement is missing. It is omitted from plot subtitles.'),
    ('Privacy', 'Only the missed checklist uses approved pseudonymous patient IDs. No names, DOB, sample IDs or source free text are exported.'),
]

def worksheet_sections(result, d):
    tables = result.get('tables', {})
    complete = result['status'] == 'complete'
    empty = 'No applicable observations' if complete else 'Blocked: see Inventory for reasons'
    records = display_order(inventory_records(tables, include_specimen_totals=result['scope']=='circall'), d) if complete else [
        {'Issue': row.get('field', ''), 'Reason': row.get('issue', row.get('reason', '')), 'Occurrences': row.get('occurrences')}
        for row in result.get('blocking', [])]
    yield 'Inventory', 'Overall, center and specimen/timepoint rows overlap. Overdue includes Late and overdue Marked missing. Rate = due received / (due received + overdue Marked missing); Late is excluded. Denominators are in hidden columns.', [Section(records, empty, hidden=('Due received', 'Timed denominator'))]
    hidden = ('Mean', 'SD', 'Minimum', 'Maximum', 'Total', 'Available patients', 'Received samples')
    measures = display_order(measurement_records(tables), d) if complete else []
    yield 'Measurements', 'Received samples only; zeros retained. Q1–Q3 describe the middle 50%. DNA label is recorded metadata. Additional statistics are in hidden columns and Reference.', [Section(measures, empty, hidden=hidden)]
    if 'comparisons' in result:
        records=[]
        for row in result['comparisons'] if complete else []:
            labels=d['metrics'][row['field']].get('plot_visit_labels',{})
            records.append({'Cohort':row['cohort'],'Measurement':MEASUREMENT_LABELS[row['field']],
                            'Specimen':row['specimen'],'Comparison':f'{labels.get(row["visit_1"],row["visit_1"])} vs {labels.get(row["visit_2"],row["visit_2"])}',
                            'Test':row['test'],'n1':row['n_1'],'n2':row['n_2'],'Matched pairs':row['paired_n'],
                            'Median 1':row['median_1'],'Median 2':row['median_2'],
                            'Raw p':row['p_value'],'Holm p':row['p_adjusted'],'Stars':row['significance'],
                            'Status':row['status'],'Reason':row['reason'],'Method':row['p_method'],
                            'Family size':row['family_size']})
        yield 'Comparisons', 'One median per participant/timepoint. Controls: independent Mann–Whitney U; patient timepoints: paired Wilcoxon. Holm correction includes all planned tests; pooled tests combine cohorts.', [Section(records, empty)]
    if result['scope'] != 'pooled' and result['include_controls']:
        controls = result.get('controls', {})
        summary = [{'Specimen': row.get('specimen', 'All specimens'), 'Timepoint': row.get('visit', 'All timepoints'),
                    'Participants': row['patients'], 'Control records': row['samples'], 'Received': row['received_samples']}
                   for row in controls.get('summary', [])]
        sections = [
            Section(display_order(summary, d) if complete else [], empty, 'Control inventory'),
            Section(display_order(measurement_records(controls), d) if complete else [], empty,
                    'Control measurements', hidden),
        ]
        yield 'Controls', 'Controls remain outside patient descriptive counts; their approved comparison tests are in Comparisons.', sections
    if result['scope'] == 'circall':
        missed = [{'Patient': row['patient_id'], 'Center': row['center'], 'Timepoint': display_timepoint(row['visit']),
                   'Specimen': row['specimen'], 'Status': RECEIPT_LABELS.get(row['status'], row['status'].capitalize()),
                   'Source worksheet': row['sheet'], 'Source row': row['row']}
                  for row in sorted(tables.get('missed', []), key=lambda row: row['status']!='late')]
        yield 'Overdue', 'Late: overdue and not explicitly na. Marked missing: overdue and explicitly na. Late rows appear first; filter Status to follow up. Only approved patient pseudonyms appear here.', [
            Section(missed if complete else [], 'No overdue samples' if complete else empty,
                    hidden=('Source worksheet', 'Source row'))]
    raw = [{'section': 'Metadata', 'field': key, 'value': value} for key, value in result['metadata'].items()]
    raw += [{'section': 'Blocking', **row} for row in result.get('blocking', [])]
    for key in ('summary', 'receipt', 'measurements', 'availability'):
        raw += [{'section': key, **row} for row in tables.get(key, [])]
    for key in ('summary', 'receipt', 'measurements', 'availability'):
        raw += [{'section': 'controls_' + key, **row} for row in result.get('controls', {}).get(key, [])]
    raw += [{'section': 'Definitions', 'field': key, 'description': value} for key, value in NOTES]
    raw += [{'section': 'Metrics', 'field': key, 'description': value} for key, value in d['metrics'].items()]
    raw += [{'section':'Comparisons',**row} for row in result.get('comparisons',[]) if complete]
    raw += [{'section':'Inference settings','field':key,'value':value} for key,value in d.get('inference',{}).items()]
    yield 'Reference', '', [Section(raw)]

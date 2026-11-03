"""Package existing analysis CSVs without recalculating statistics."""
import argparse
import logging
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from analysis.sample_analysis.reporting import workbook


def build(run_dir, output_dir=None):
    from analysis.outputs import engine_directory
    requested = Path(run_dir)
    run_dir = engine_directory(requested, 'canonical')
    if output_dir is None and requested != run_dir:
        output_dir = requested if requested.name == 'sample_analysis' else requested / 'sample_analysis'
    if not (run_dir / 'analysis_status.csv').is_file():
        raise ValueError(f'Missing analysis_status.csv in {run_dir}')
    output_dir = Path(output_dir) if output_dir else run_dir / 'spreadsheet'
    scopes = ('circall', 'retrospective', 'combined')
    paths = [output_dir / f'{scope}_statistics.xlsx' for scope in scopes]
    for path in paths:
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite {path}; choose a new output directory')
    tables = {scope: {} for scope in scopes}
    sources = {scope: [] for scope in scopes}

    def add(scope, name, data, source):
        tables[scope][name] = data
        sources[scope].append({'worksheet': name, 'rows': len(data), 'source_csv': source})

    shared = {'analysis_status': 'analysis_status.csv', 'inventory': 'inventory/availability.csv',
              'volumes': 'volumes/summary.csv', 'yield': 'yield/summary.csv',
              'correlations': 'yield/correlations.csv'}
    for name, relative in shared.items():
        path = run_dir / relative
        if not path.is_file():
            continue
        data = pd.read_csv(path)
        if 'cohort' not in data:
            raise ValueError(f'Missing cohort column: {relative}')
        if name == 'analysis_status':
            add('combined', name, data.loc[data.cohort.isin(['combined', 'all'])].copy(), relative)
        for scope in scopes[:2]:
            selected = data.loc[data.cohort.isin([scope, 'all'])].copy()
            add(scope, name, selected, relative)
    for scope in scopes[:2]:
        for path in sorted((run_dir / 'longitudinal' / scope).glob('*.csv')):
            data = pd.read_csv(path)
            relative = str(path.relative_to(run_dir))
            add(scope, path.stem, data, relative)
    for path in sorted((run_dir / 'pooled').glob('*.csv')):
        if path.stem != 'eligibility':
            add('combined', path.stem, pd.read_csv(path), str(path.relative_to(run_dir)))
    csf = run_dir / 'volumes/circall_csf_by_site.csv'
    if csf.is_file():
        add('circall', 'csf_volumes_by_site', pd.read_csv(csf), str(csf.relative_to(run_dir)))
    for dimension in ('compartment', 'timepoint'):
        path = run_dir / 'inventory' / f'missing_samples_by_hospital_{dimension}.csv'
        if path.is_file():
            add('circall', f'missing_by_site_{dimension}', pd.read_csv(path), str(path.relative_to(run_dir)))
    protocols = run_dir / 'prepared/extraction_protocols.csv'
    if protocols.is_file():
        data = pd.read_csv(protocols)
        for scope in scopes:
            selected = data if scope == 'combined' else data.loc[data.cohort.eq(scope)].copy()
            add(scope, 'extraction_protocols', selected, str(protocols.relative_to(run_dir)))
    mrd = run_dir / 'kinetics/mrd/circall_mrd_summary.csv'
    if not mrd.is_file():
        mrd = run_dir / 'mrd/circall_mrd_summary.csv'
    if mrd.is_file():
        data = pd.read_csv(mrd)
        add('circall', 'mrd_summary', data, str(mrd.relative_to(run_dir)))
    retrospective_mrd = run_dir / 'kinetics/mrd/retrospective_mrd_summary.csv'
    if retrospective_mrd.is_file():
        add('retrospective', 'mrd_summary', pd.read_csv(retrospective_mrd), str(retrospective_mrd.relative_to(run_dir)))
    for scope, path in zip(scopes, paths):
        notes = pd.DataFrame([
            {'item': 'Source run', 'description': str(run_dir.resolve())},
            {'item': 'Scope', 'description': scope},
            {'item': 'Control populations', 'description': 'CIRCALL cohorte_control: pediatric controls. cfDNA_donors.xlsx: adult controls. The current control reference pools both populations without age adjustment.'},
            {'item': 'Patient overlap', 'description': 'The investigator confirms that the retrospective and CIRCALL patient cohorts cannot overlap.'},
            {'item': 'Preanalytical purpose', 'description': 'Evaluate sample-handling choices and DNA recovery; observational associations do not establish absence of handling bias.'},
            {'item': 'Missing-sample tables', 'description': 'CIRCALL compact tables: missing / (present + missing), with blanks excluded. Affected patients: patients with at least one missing sample / all identified patients. Overall = RDB + TRS. Legacy 0/0 (0.0%) means no assessed records, not evidence of complete collection. Detailed inventory retains other sites.'},
            {'item': 'Methods', 'description': 'Pooled analyses calculated from shared plasma observations; see methods worksheet. No cohort adjustment.' if scope == 'combined' and 'methods' in tables[scope] else 'Existing cohort results; no recalculation during workbook packaging.'},
            {'item': 'Pooled availability', 'description': 'Pooled results included.' if 'methods' in tables['combined'] else 'Pooling is disabled by default; this workbook does not imply combined inference.'},
            {'item': 'Availability', 'description': 'Only available analysis files are included. Check analysis_status for failures or unavailable analyses.'},
            {'item': 'MRD', 'description': 'Descriptive MRD summaries only. Retrospective patient observations remain in memory; the source workbook retains annotations.'},
        ])
        workbook(path, {'README': notes, 'contents': pd.DataFrame(sources[scope]), **tables[scope]})
        from openpyxl import load_workbook
        book = load_workbook(path)
        for sheet in book:
            sheet.sheet_view.showGridLines = False
            for cell in sheet[1]:
                cell.fill = PatternFill('solid', fgColor='174D5B')
                cell.font = Font(color='FFFFFF', bold=True)
                cell.alignment = Alignment(wrap_text=True)
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.font = Font(color='00804A')
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                    if isinstance(cell.value, float):
                        cell.number_format = '0.000E+00' if 'p_value' in str(sheet.cell(1, cell.column).value) or 'p_adj' in str(sheet.cell(1, cell.column).value) else '0.####'
        book['README'].column_dimensions['B'].width = 100
        for row in range(2, book['README'].max_row + 1):
            book['README'].row_dimensions[row].height = 45
        book.save(path)
        logging.info('Wrote %s (%d analysis worksheets)', path, len(tables[scope]))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path, help='Existing canonical output run')
    parser.add_argument('--output-dir', type=Path, help='New destination; defaults to RUN/spreadsheet')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        build(args.run_dir, args.output_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

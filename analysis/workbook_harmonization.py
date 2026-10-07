"""Harmonize approved headers/specimen labels in fresh workbook copies."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
import warnings
from zipfile import ZipFile

from openpyxl import load_workbook

from analysis.workbook_cleanup import clean, digest, MISSING

ROOT = Path(__file__).resolve().parents[1]


def replacements(path, cohort, config):
    changes, headers, review = {}, [], []
    with ZipFile(path) as z:
        if any(n.startswith('xl/tables/') and n.endswith('.xml') for n in z.namelist()):
            raise ValueError('Excel table metadata requires a separate schema migration')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        wb = load_workbook(path, read_only=True, data_only=False)
        try:
            selected = config['selected_sheets'][cohort]
            if any(name not in wb.sheetnames for name in selected):
                raise ValueError('A configured source sheet is missing')
            for sheet in selected:
                iterator = wb[sheet].iter_rows()
                first = next(iterator, [])
                old = [c.value for c in first]
                aliases = dict(config['header_mapping'])
                if sheet == 'template':
                    aliases.update(config['template_header_aliases'])
                new = [aliases.get(h,h) for h in old]
                nonempty = [h for h in new if h]
                if len(nonempty) != len(set(nonempty)):
                    raise ValueError('Target column names collide')
                changes[sheet] = {}
                for cell,target in zip(first,new):
                    if target != cell.value:
                        changes[sheet][cell.coordinate] = (cell.value,target)
                        headers.append({'sheet':sheet,'cell':cell.coordinate,'old':cell.value,'new':target})
                specimen = next((i for i,h in enumerate(old) if h in ('tissue','compartment')), None)
                acid = old.index('nucleic_acid') if 'nucleic_acid' in old else None
                for row in iterator:
                    for cell in row:
                        if cell.data_type == 'f' and any('['+str(h)+']' in cell.value for h in aliases):
                            raise ValueError('Structured header references require explicit formula migration')
                    if specimen is None:
                        continue
                    cell = row[specimen]
                    label = cell.value
                    if label is None or str(label).strip().casefold() in MISSING:
                        continue
                    conditional = config['conditional_specimen_mapping']
                    if label == conditional['source_label']:
                        target = conditional['target_label'] if acid is not None and row[acid].value == conditional['required_nucleic_acid'] else None
                    else:
                        target = config['specimen_mapping'].get(label)
                    if target is None:
                        review.append({'sheet':sheet,'cell':cell.coordinate,'reason':'unapproved_specimen_mapping_kept_unchanged'})
                    elif target != label:
                        changes[sheet][cell.coordinate] = ('specimen_type',target)
            # Protect formulas that explicitly compare a renamed specimen label.
            changed_labels = {a:b for a,b in config['specimen_mapping'].items() if a.casefold()!=b.casefold()}
            changed_labels[config['conditional_specimen_mapping']['source_label']] = config['conditional_specimen_mapping']['target_label']
            for ws in wb:
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.data_type == 'f' and any(re.search('"'+re.escape(label)+'"',cell.value,re.I) for label in changed_labels):
                            raise ValueError('A formula explicitly uses a specimen label that changes; review before migration')
        finally:
            wb.close()
    return changes, headers, review


def harmonize(source,destination,cohort,config):
    changes,headers,review = replacements(source,cohort,config)
    result = clean(source,destination,config['selected_sheets'][cohort],text_changes=changes)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        wb=load_workbook(destination,read_only=True,data_only=False)
        try:
            for name,edits in changes.items():
                found={cell.coordinate:cell.value for row in wb[name].iter_rows() for cell in row if getattr(cell,'coordinate',None) in edits}
                if found != {key:value[1] for key,value in edits.items()}:
                    raise ValueError('Output text differs from the approved mapping')
        finally:
            wb.close()
    result.update(cohort=cohort,header_changes=headers,review_cells=review,
                  review_counts=dict(Counter(x['reason'] for x in review)),
                  specimen_label_changes=sum(v[0]=='specimen_type' for edits in changes.values() for v in edits.values()))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrospective',type=Path,required=True)
    parser.add_argument('--circall',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/definitions/workbook_harmonization.json')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():
        parser.error('Output directory must not exist')
    config=json.loads(args.config.read_text())
    if config.get('schema_version') != 1:
        parser.error('Unsupported mapping schema')
    # Validate both sources before publishing either copy.
    for cohort in ['retrospective','circall']:
        source=getattr(args,cohort)
        if not source.is_file():
            parser.error('An explicit input is missing')
        replacements(source,cohort,config)
    started=datetime.now(timezone.utc).isoformat()
    args.output_dir.mkdir(parents=True)
    report={'started_utc':started,'command':[sys.executable,*sys.argv],
            'config_path':str(args.config),'config_sha256':digest(args.config),
            'code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'analysis/workbook_cleanup.py']},
            'environment_lock_sha256':digest(ROOT/'environments/conda-linux-64.lock'),
            'packages':{'openpyxl':version('openpyxl')},'workbooks':[]}
    for cohort in ['retrospective','circall']:
        source=getattr(args,cohort)
        destination=args.output_dir/(source.stem.removesuffix('_cleaned')+'_harmonized.xlsx')
        result=harmonize(source,destination,cohort,config)
        report['workbooks'].append(result)
        print(json.dumps({'cohort':cohort,'output':str(destination),'header_changes':len(result['header_changes']),
                          'specimen_label_changes':result['specimen_label_changes'],'unresolved_specimen_cells':len(result['review_cells'])}))
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    with (args.output_dir/'harmonization_report.json').open('x') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write('\n')


if __name__=='__main__':
    main()

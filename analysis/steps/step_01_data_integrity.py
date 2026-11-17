"""Internal data-integrity engine with quality-aware reports."""
from analysis.data_integrity.step_03_validate import validate_results
import argparse
from pathlib import Path

from analysis.utils.source_state import sources, capture_sources, verify_source_states
from analysis.utils.retrospective_controls import inspect_with_controls
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from analysis.data_integrity.step_01_inspect import load_rules
from analysis.data_integrity.step_02_report import write_workbook


def arguments(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--workflow',choices=['data_integrity'],default='data_integrity')
    parser.add_argument('--inventory',type=Path)
    parser.add_argument('--circall',type=Path)
    parser.add_argument('--donors',type=Path,help='Explicit retrospective controls workbook; omitted means not selected')
    parser.add_argument('--cohort',choices=['all','retrospective','circall'],default='all')
    parser.add_argument('--include-controls',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--rules',type=Path,default=ROOT/'configs/definitions/data_integrity.json')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args(argv)
    if args.cohort in ('all','retrospective') and args.inventory is None:
        parser.error('Selected retrospective cohort requires --inventory')
    if args.cohort in ('all','circall') and args.circall is None:
        parser.error('Selected CIRCALL cohort requires --circall')
    for key in ('inventory','circall','donors','rules','output_dir'):
        value=getattr(args,key)
        if value is not None:setattr(args,key,value.expanduser().absolute())
    return args


def preflight(args):
    rules=load_rules(args.rules)
    inputs,states=capture_sources(args)
    settings={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items() if k not in ('output_dir','validate_only')}
    settings['rules_definition']=rules
    record=envelope('data_integrity',settings,inputs,
                    [ROOT/'run.py',*sorted((ROOT/'analysis').rglob('*.py'))],
                    ROOT/'environments/conda-linux-64.lock')
    record.update(source_states=states,status='complete',finished_utc=utc_now())
    verify_inputs(record['inputs']);verify_source_states(states)
    return record


def run(args):
    """Worker exit reports publication readiness; quality is a separate outcome."""
    record=preflight(args)
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=False)
    record.update(status='running',started_utc=utc_now(),finished_utc=None,cohorts=[],artifacts=[])
    write_json(output/'run_manifest.json',record)
    failures=[]
    rules=record['resolved_settings']['rules_definition']
    for cohort,path in sources(args).items():
        try:
            result=inspect_with_controls(path,cohort,args.include_controls,rules,getattr(args,'donors',None))
            if result.get('additional_sources'):
                result['additional_sources'][0]['sha256']=record['source_states']['retrospective_controls']['sha256']
            native=output/cohort
            native.mkdir()
            write_json(native/'findings.json',result)
            write_workbook(native/'integrity_report.xlsx',result,rules,record['source_states'][cohort]['sha256'])
            record['cohorts'].append({'cohort':cohort,'report_status':'complete',**result['summary']})
            for name in ('findings.json','integrity_report.xlsx'):
                p=native/name
                record['artifacts'].append({'path':str(p.relative_to(output)),'sha256':digest(p)})
        except Exception as error:
            failures.append(cohort)
            record['cohorts'].append({'cohort':cohort,'report_status':'failed','error_code':type(error).__name__})
        write_json(output/'run_manifest.json',record)
    try:
        verify_inputs(record['inputs']);verify_source_states(record['source_states'])
    except (ValueError,OSError):
        record.update(status='failed',error_code='SourceChanged',finished_utc=utc_now())
        write_json(output/'run_manifest.json',record)
        return 1
    record.update(status='complete',report_generation_status='partial' if failures else 'complete',
                  quality_status='errors_found' if failures or any(c.get('errors',0)>0 for c in record['cohorts']) else
                                 'review_needed' if any(c.get('reviews',0)>0 for c in record['cohorts']) else 'no_issues_detected',
                  finished_utc=utc_now())
    if not any(c['report_status']=='complete' for c in record['cohorts']):record['status']='failed'
    write_json(output/'run_manifest.json',record)
    return 0 if record['status']=='complete' else 1

"""Standalone and integrated data-integrity execution with quality-aware reports."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from analysis.source_state import sources, capture_sources, verify_source_states
from analysis.retrospective_controls import inspect_with_controls
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from .checks import load_rules, inspect_cohort, group_findings, summarize
from .reporting import write_workbook, validate_workbook


def default_output_dir():
    """Keep independently auditable runs under the requested Layer 1 root."""
    return ROOT/'outputs'/'layer1_data_integrity'/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))


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


def validate_results(output,record):
    output=Path(output)
    for item in record['artifacts']:
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or digest(output/path)!=item['sha256']:
            raise ValueError('Integrity report artifact mismatch')
    for cohort in record['cohorts']:
        if cohort['report_status']!='complete':continue
        result=json.loads((output/cohort['cohort']/'findings.json').read_text())
        if result['groups']!=group_findings(result['findings']) or result['summary']!=summarize(result['findings']):
            raise ValueError('Integrity audit groups do not reconcile')
        validate_workbook(output/cohort['cohort']/'integrity_report.xlsx',result)
    verify_source_states(record['source_states'])


def main(argv=None):
    args=arguments(argv)
    try:
        evidence=preflight(args)
        if args.output_dir is not None and (args.output_dir.exists() or any(p.is_symlink() for p in (args.output_dir,*args.output_dir.parents))):
            raise ValueError('Output destination must be fresh and not a symlink')
        if args.validate_only:
            print('Integrity preflight complete; workbook defects are reported during inspection')
            return 0
        args.output_dir=args.output_dir or default_output_dir()
        from analysis.outputs import run_standalone
        from analysis.worker import completion
        entry={'name':'data_integrity','options':{}}
        def execute(native):
            from copy import copy
            verify_inputs(evidence['inputs']);verify_source_states(evidence['source_states'])
            worker=copy(args);worker.output_dir=native
            return run(worker)
        return run_standalone('data_integrity',args.output_dir,evidence['resolved_settings'],execute,
                              lambda native:completion(entry,native))
    except (OSError,ValueError) as error:
        print(f'Integrity execution could not complete ({type(error).__name__}); review configuration and destination',file=sys.stderr)
        return 1

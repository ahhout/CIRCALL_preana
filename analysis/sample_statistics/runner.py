"""Independently runnable Layer 2 with an explicit per-cohort integrity gate."""
import argparse
from copy import copy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import sys

from analysis.retrospective_controls import inspect_with_controls
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from analysis.data_integrity.checks import inspect_cohort, load_rules
from analysis.source_state import capture_sources, sources, verify_source_states
from .core import load_definitions, assessment, prepare, aggregate
from .reporting import workbook, validate_workbook, figures


def default_output_dir():
    return ROOT/'outputs/layer2_sample_statistics'/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))


def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--workflow',choices=['sample_statistics'],default='sample_statistics')
    p.add_argument('--inventory',type=Path)
    p.add_argument('--circall',type=Path)
    p.add_argument('--donors',type=Path,help='Explicit retrospective controls workbook; omitted means not selected')
    p.add_argument('--cohort',choices=['all','retrospective','circall'],default='all')
    p.add_argument('--include-controls',action=argparse.BooleanOptionalAction,default=True)
    p.add_argument('--rules',type=Path,default=ROOT/'configs/definitions/data_integrity.json')
    p.add_argument('--definitions',type=Path,default=ROOT/'configs/definitions/sample_statistics.json')
    p.add_argument('--assessment-time',help='ISO timestamp with offset; defaults to current execution time')
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--validate-only',action='store_true')
    a=p.parse_args(argv)
    for cohort,field in [('retrospective','inventory'),('circall','circall')]:
        if a.cohort in ('all',cohort) and getattr(a,field) is None:p.error(f'Selected {cohort} requires --{field}')
    for field in ('inventory','circall','donors','rules','definitions','output_dir'):
        if getattr(a,field) is not None:setattr(a,field,getattr(a,field).expanduser().absolute())
    if a.assessment_time is not None:
        try:a.assessment_time=assessment(a.assessment_time).isoformat()
        except ValueError:p.error('Assessment timestamp requires ISO format and a UTC offset')
    return a


def preflight(args):
    rules=load_rules(args.rules)
    definitions=load_definitions(args.definitions)
    inputs,states=capture_sources(args)
    inputs['definitions']=args.definitions
    settings={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items() if k not in ('output_dir','validate_only')}
    settings.update(rules_definition=rules,statistics_definition=definitions)
    record=envelope('sample_statistics',settings,inputs,[ROOT/'run.py',*sorted((ROOT/'analysis').rglob('*.py'))],ROOT/'environments/conda-linux-64.lock')
    record.update(source_states=states,status='complete',finished_utc=utc_now())
    verify_inputs(record['inputs']);verify_source_states(states)
    return record


def run(args):
    args=copy(args)
    args.assessment_time=assessment(args.assessment_time).isoformat()
    record=preflight(args)
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=False)
    os.environ.setdefault('MPLCONFIGDIR', str(output/'.cache/matplotlib'))
    record.update(status='running',started_utc=utc_now(),finished_utc=None,cohorts=[],artifacts=[])
    write_json(output/'run_manifest.json',record)
    d=record['resolved_settings']['statistics_definition']
    rules=record['resolved_settings']['rules_definition']
    successful={}
    def publish_scope(scope, result, rows):
        native=output/scope
        native.mkdir(exist_ok=True)
        if result['status']=='complete':
            sanitized=[]
            for row in rows:
                item={k:v for k,v in row.items() if k not in ('patient_id','subject_key')}
                item['subject_key']=hashlib.sha256(row['subject_key'].encode()).hexdigest()
                if row['receipt']=='missed':item['patient_id']=row['patient_id']
                sanitized.append(item)
            write_json(native/'observations.json',sanitized)
        write_json(native/'statistics.json',result)
        workbook(native/'statistics.xlsx',result,d)
        if result['status']=='complete':
            figures(native/'figures', [r for r in rows if not r['control']], d, pooled=scope=='pooled')
            if scope!='pooled' and args.include_controls:
                figures(native/'figures'/'controls',[r for r in rows if r['control']],d,controls=True)
        validate_workbook(native/'statistics.xlsx',result,d)
        record['cohorts'].append({'cohort':scope,'report_status':'complete','statistics_status':result['status']})
        for path in sorted(native.rglob('*')):
            if path.is_file():record['artifacts'].append({'path':str(path.relative_to(output)),'sha256':digest(path)})
    for cohort,path in sources(args).items():
        result=dict(scope=cohort,status='blocked',include_controls=args.include_controls,blocking=[],tables={},
                    metadata=dict(cohort=cohort,assessment_time=args.assessment_time,source_sha256=record['source_states'][cohort]['sha256'],
                                  rules_sha256=digest(args.rules),definitions_sha256=digest(args.definitions)))
        try:
            integrity=inspect_with_controls(path,cohort,args.include_controls,rules,getattr(args,'donors',None))
            (output/cohort).mkdir()
            write_json(output/cohort/'integrity_findings.json',integrity)
            if cohort=='retrospective' and args.include_controls:
                result['metadata']['retrospective_controls_source']=str(args.donors) if args.donors else 'Not selected'
                result['metadata']['retrospective_controls_sha256']=record['source_states'].get('retrospective_controls',{}).get('sha256')
            result['metadata'].update(integrity_errors=integrity['summary']['errors'],integrity_reviews=integrity['summary']['reviews'])
            if integrity['summary']['errors']:
                result['blocking']=[{'reason':'layer1_errors','sheet':g['sheet'],'field':g['field'],'issue':g['issue'],'occurrences':g['count'], 'cell_references':', '.join(g['cells'])} for g in integrity['groups'] if g['severity']=='error']
                rows=[]
            else:
                rows,issues,skipped=prepare(path,cohort,args.include_controls,assessment(args.assessment_time),d)
                if cohort=='retrospective' and args.include_controls and args.donors is not None:
                    from analysis.retrospective_controls import observations
                    donor_rows,donor_issues=observations(args.donors,d)
                    rows.extend(donor_rows);issues.extend(donor_issues)
                result['metadata']['non_sample_rows_skipped']=skipped
                result['blocking']=issues
                if not issues:
                    result['status']='complete'
                    result['tables']=aggregate([r for r in rows if not r['control']],d)
                    if args.include_controls:result['controls']=aggregate([r for r in rows if r['control']],d)
                    successful[cohort]=rows
            result['metadata']['statistics_status']=result['status']
            publish_scope(cohort,result,rows)
        except Exception as error:
            # Do not propagate source/library text, which may contain identifiers.
            result.update(status='execution_failed',blocking=[{'reason':type(error).__name__}],tables={})
            result['metadata']['statistics_status']='execution_failed'
            successful.pop(cohort,None)
            try:publish_scope(cohort,result,[])
            except Exception:
                record['cohorts'].append({'cohort':cohort,'report_status':'failed','statistics_status':'execution_failed','error_code':type(error).__name__})
        write_json(output/'run_manifest.json',record)
    if args.cohort=='all':
        rows=[r for cohort in successful.values() for r in cohort if not r['control']]
        ready=set(successful)=={'retrospective','circall'}
        result=dict(scope='pooled',status='complete' if ready else 'blocked',include_controls=False,
                    metadata=dict(cohort='pooled',assessment_time=args.assessment_time,statistics_status='complete' if ready else 'blocked',
                                  source_sha256={k:v['sha256'] for k,v in record['source_states'].items()},rules_sha256=digest(args.rules),definitions_sha256=digest(args.definitions)),
                    blocking=[] if ready else [{'reason':'both_patient_cohorts_must_pass'}],
                    tables=aggregate(rows,d,pooled=True) if ready else {})
        try:publish_scope('pooled',result,rows if ready else [])
        except Exception as error:record['cohorts'].append({'cohort':'pooled','report_status':'failed','statistics_status':'execution_failed','error_code':type(error).__name__})
    verify_inputs(record['inputs']);verify_source_states(record['source_states'])
    record.update(status='complete' if any(c['report_status']=='complete' for c in record['cohorts']) else 'failed',
                  quality_status='no_issues_detected' if all(c['statistics_status']=='complete' for c in record['cohorts']) else 'errors_found',
                  report_generation_status='complete' if all(c['report_status']=='complete' for c in record['cohorts']) else 'partial',finished_utc=utc_now())
    write_json(output/'run_manifest.json',record)
    return 0 if record['status']=='complete' else 1


def validate_results(output,record):
    output=Path(output)
    d=record['resolved_settings']['statistics_definition']
    for item in record['artifacts']:
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or digest(output/path)!=item['sha256']:raise ValueError('Statistics artifact mismatch')
        if path.suffix=='.png':
            from PIL import Image
            with Image.open(output/path) as im:im.verify()
        if path.suffix=='.pdf' and not (output/path).read_bytes().startswith(b'%PDF-'):raise ValueError('Invalid PDF')
    for cohort in record['cohorts']:
        if cohort['report_status']=='complete':
            native=output/cohort['cohort']
            result=json.loads((native/'statistics.json').read_text())
            validate_workbook(native/'statistics.xlsx',result,d)
            if result['status']=='complete':
                rows=json.loads((native/'observations.json').read_text())
                if aggregate([r for r in rows if not r['control']],d,pooled=cohort['cohort']=='pooled') != result['tables']:
                    raise ValueError('Statistics tables do not reconcile with audit observations')
                if 'controls' in result and aggregate([r for r in rows if r['control']],d)!=result['controls']:
                    raise ValueError('Control tables do not reconcile')
    verify_inputs(record['inputs']);verify_source_states(record['source_states'])


def main(argv=None):
    args=arguments(argv)
    try:
        if args.output_dir is not None and (args.output_dir.exists() or any(p.is_symlink() for p in (args.output_dir,*args.output_dir.parents))):raise ValueError('Fresh output destination required')
        evidence=preflight(args)
        if args.validate_only:
            print('Statistics preflight complete; integrity and identity gates run during execution')
            return 0
        args.output_dir=args.output_dir or default_output_dir()
        from analysis.outputs import run_standalone
        from analysis.worker import completion
        def execute(native):
            verify_inputs(evidence['inputs']);verify_source_states(evidence['source_states'])
            worker=copy(args);worker.output_dir=native
            return run(worker)
        return run_standalone('sample_statistics',args.output_dir,evidence['resolved_settings'],execute,
                              lambda native:completion({'name':'sample_statistics','options':{}},native))
    except (OSError,ValueError) as error:
        print(f'Statistics execution unavailable ({type(error).__name__}); check configuration and destination',file=sys.stderr)
        return 1

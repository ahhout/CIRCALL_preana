"""Orchestrate preparation, independent cohort analyses, and local run evidence."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=str, ensure_ascii=False) + '\n')


def run(args):
    from .legacy import prepare_output
    from .policies import SETTINGS
    try:
        prepare_output(args.output_dir)
    except ValueError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    output=args.output_dir
    (output/'logs').mkdir()
    os.environ.setdefault('MPLCONFIGDIR',str(output/'.cache/matplotlib'))
    os.environ.setdefault('XDG_CACHE_HOME',str(output/'.cache'))
    os.environ['MPLBACKEND']='Agg'
    from .adapters import SOURCE_MAPPINGS, prepare
    from . import analyses, reporting
    from .policies import eligible, pooled_controls, PRIMARY, PAIRS
    from .preparation import MEASUREMENTS, RTOL, ATOL
    cohorts=['retrospective','circall'] if args.cohort=='all' else [args.cohort]
    tasks=['inventory','volumes','yield','longitudinal'] if args.analysis=='all' else [args.analysis]
    inputs={'circall':args.circall,'donors':args.donors}
    if 'retrospective' in cohorts:inputs['inventory']=args.inventory
    revision=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    manifest={'workflow':'canonical','status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
              'arguments':vars(args),'code_revision':revision.stdout.strip() if revision.returncode==0 else None,
              'code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'run.py',*sorted((ROOT/'pre_analysis').glob('*.py'))]},
              'python':sys.version,'executable':sys.executable,'environment_lock_sha256':digest(ROOT/'conda-linux-64.lock'),
              'settings':SETTINGS,'qc_tolerance':{'rtol':RTOL,'atol':ATOL},'inputs':{},'stages':[]}
    manifest_path=output/'run_manifest.json'
    write_json(manifest_path,manifest)
    def stage(name, function):
        entry={'stage':name,'status':'running'};manifest['stages'].append(entry);write_json(manifest_path,manifest)
        print(f'Running {name}',flush=True)
        try:
            with (output/'logs'/f'{name}.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                try:
                    value=function()
                except Exception:
                    traceback.print_exc()
                    raise
            entry['status']='complete'
            return value
        except Exception as error:
            entry['status']='failed';entry['error']=str(error)
            raise
        finally:
            write_json(manifest_path,manifest)
    events=[];audits=[]
    try:
        for key,path in inputs.items():
            if not path.is_file():raise ValueError(f'Workbook not found: {path}')
            manifest['inputs'][key]={'path':str(path),'sha256':digest(path)}
        frame,qc,schemas=stage('prepare',lambda:prepare(args.inventory,args.circall,args.donors,cohorts))
        preparation=output/'prepared';preparation.mkdir()
        reporting.table(preparation/'inventory.csv',frame)
        reporting.table(preparation/'discrepancies.csv',qc)
        controls=pooled_controls(frame)
        reporting.table(preparation/'pooled_controls.csv',controls)
        write_json(preparation/'source_mappings.json',SOURCE_MAPPINGS)
        write_json(preparation/'source_headers.json',schemas)
        statuses=[]
        for _,row in frame.iterrows():
            for metric in MEASUREMENTS:
                statuses.append({'record_id':row.record_id,'cohort':row.cohort,'compartment':row.compartment,
                                 'measurement':metric,'status':row[metric+'_status'],'qc_hold':row.qc_hold})
        import pandas as pd
        reporting.table(preparation/'measurement_availability.csv',pd.DataFrame(statuses))
        summary={'records_by_source':frame.groupby('source').size().to_dict(),'qc_hold_records':int(frame.qc_hold.sum()),
                 'pooled_measured_controls':len(controls),'controls_by_source':controls.groupby('control_source').size().to_dict(),
                 'identified_circall_plasma_formula_zeros':int((frame.cohort.eq('circall') & frame.compartment.eq('plasma')
                    & frame.sample_state.eq('present') & frame.dna_total_ng_status.eq('formula_zero_missing_inputs')).sum())}
        write_json(preparation/'summary.json',summary)
        for question in tasks:
            if question=='inventory':
                def inventory_task():
                    result=analyses.availability(frame)
                    reporting.table(output/'inventory/availability.csv',result)
                    reporting.workbook(output/'inventory/availability.xlsx',{'availability':result})
                    reporting.inventory_plot(result,cohorts,output/'inventory/coverage.png')
                    return result
                stage('inventory',inventory_task)
                events.append(dict(analysis='inventory',cohort='all',status='complete',reason=''))
            elif question=='volumes':
                def volume_task():
                    selected=[]
                    for cohort in cohorts:
                        data,audit=eligible(frame,cohort,'volumes');selected.append(data);audits.append(audit)
                    data=pd.concat(selected,ignore_index=True)
                    result=analyses.measurement_summary(data,analyses.VOLUME_METRICS)
                    reporting.table(output/'volumes/summary.csv',result)
                    reporting.workbook(output/'volumes/summary.xlsx',{'volumes':result})
                    for metric in analyses.VOLUME_METRICS:
                        reporting.volume_plot(data,cohorts,metric,output/'volumes'/f'{metric}.png')
                stage('volumes',volume_task)
                events.append(dict(analysis='volumes',cohort='all',status='complete',reason=''))
            elif question=='yield':
                def yield_task():
                    selected=[];correlations=[]
                    for cohort in cohorts:
                        data,audit=eligible(frame,cohort,'yield');selected.append(data);audits.append(audit)
                        corr,audit=analyses.correlations(frame,cohort);correlations.append(corr);audits.append(audit)
                    data=pd.concat(selected,ignore_index=True)
                    plasma_summary=analyses.measurement_summary(data,analyses.YIELD_METRICS[:3])
                    pellet=frame.loc[frame.cohort.isin(cohorts)&~frame.qc_hold&frame.record_id.str.endswith(':MNC')]
                    pellet_summary=analyses.measurement_summary(pellet,analyses.YIELD_METRICS[3:])
                    result=pd.concat([plasma_summary,pellet_summary],ignore_index=True)
                    corr=pd.concat(correlations,ignore_index=True)
                    reporting.table(output/'yield/summary.csv',result)
                    reporting.table(output/'yield/correlations.csv',corr)
                    reporting.workbook(output/'yield/summary.xlsx',{'yield':result,'correlations':corr})
                    for metric in analyses.YIELD_METRICS[:3]:
                        reporting.timepoint_plot(frame,cohorts,metric,output/'yield'/f'{metric}.png')
                    for x,y in PAIRS:
                        reporting.correlation_plot(frame,cohorts,x,y,output/'yield'/f'{x}_vs_{y}.png')
                stage('yield',yield_task)
                events.append(dict(analysis='yield',cohort='all',status='complete',reason=''))
            else:
                for cohort in cohorts:
                    destination=output/'longitudinal'/cohort
                    def model_task(cohort=cohort,destination=destination):
                        tables,audit,notes=analyses.longitudinal(frame,cohort,destination,
                           random_slope=args.mixed_random_slope_sensitivity,outlier_drop_n=args.mixed_outlier_drop_n)
                        audits.append(audit);events.extend(notes)
                        for name,data in tables.items():reporting.table(destination/f'{name}.csv',data)
                        if tables:reporting.workbook(destination/'statistics.xlsx',tables)
                        return bool(tables)
                    try:
                        has_tables=stage(f'longitudinal_{cohort}',model_task)
                        if has_tables:
                            events.append(dict(analysis='longitudinal',cohort=cohort,status='complete',reason='requested supported analyses completed; see individual availability entries'))
                    except Exception as error:
                        events.append(dict(analysis='longitudinal',cohort=cohort,status='failed',reason=str(error)))
                    meta=frame.loc[frame.cohort.eq(cohort)]
                    if not meta.mrd_status.ne('').any():
                        events.append(dict(analysis='MRD_annotations',cohort=cohort,status='unavailable',reason='actual MRD results are not mapped; assay availability is not an MRD result'))
                    if not meta.genetic_subtype.replace({'na':''}).ne('').any():
                        events.append(dict(analysis='subtype_annotations',cohort=cohort,status='unavailable',reason='genetic subtype unavailable'))
                def longitudinal_plots():
                    reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/subtypes.png',longitudinal=True,subtype=True)
                    reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/trajectories.png',longitudinal=True,connect=True,subtype=True)
                stage('longitudinal_plots',longitudinal_plots)
        if audits:reporting.table(preparation/'eligibility.csv',pd.concat(audits,ignore_index=True))
        reporting.table(output/'analysis_status.csv',pd.DataFrame(events))
        manifest['analysis_status']=events
        manifest['status']='failed' if any(e['status']=='failed' for e in events) else 'complete'
        for key,path in inputs.items():
            if digest(path)!=manifest['inputs'][key]['sha256']:
                raise RuntimeError('An input changed during the run; results require a fresh run')
        manifest['summary']=summary
    except Exception as error:
        manifest['status']='failed';manifest['error']=str(error)
        print(f'Error: {error}; see {output / "logs"}',file=sys.stderr)
    finally:
        manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
        write_json(manifest_path,manifest)
    print(f'{manifest["status"].capitalize()}: {output}',flush=True)
    return 0 if manifest['status']=='complete' else 1

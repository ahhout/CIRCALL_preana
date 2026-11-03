"""Orchestrate preparation, independent cohort analyses, and local run evidence."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from analysis.provenance import digest, write_json, git_state, package_versions, contract, settings_digest

ROOT = Path(__file__).resolve().parents[2]


def selection(args):
    cohorts = ['retrospective', 'circall'] if args.cohort == 'all' else [args.cohort]
    tasks = ['inventory', 'volumes', 'yield', 'longitudinal'] if args.analysis == 'all' else [args.analysis]
    retrospective_blasts = getattr(args, 'retrospective_blasts', None)
    if args.analysis == 'all':
        if 'circall' in cohorts or retrospective_blasts is not None:
            tasks.append('kinetics')
        tasks.append('mrd')
    if args.analysis == 'kinetics':
        tasks.append('mrd')
    inputs = {'circall': args.circall, 'donors': args.donors, 'extraction_protocols': args.extraction_protocols}
    if 'retrospective' in cohorts:
        inputs['inventory'] = args.inventory
    if 'kinetics' in tasks:
        if 'circall' in cohorts:
            inputs['blood_counts'] = args.blood_counts
        if retrospective_blasts is not None:
            inputs['retrospective_blasts'] = retrospective_blasts
    return cohorts, tasks, inputs


def run(args):
    from analysis.outputs import prepare_output
    from analysis.sample_analysis.policies import SETTINGS
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
    from analysis.sample_analysis.adapters import SOURCE_MAPPINGS, prepare
    from analysis.sample_analysis import analyses
    from analysis.sample_analysis import reporting
    from analysis.sample_analysis.policies import eligible, pooled_controls, PRIMARY, PAIRS, correlation_pairs
    from analysis.sample_analysis.preparation import MEASUREMENTS, RTOL, ATOL
    cohorts, tasks, inputs = selection(args)
    revision=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    manifest={'workflow':'canonical','status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
              'arguments':vars(args),'code_revision':revision.stdout.strip() if revision.returncode==0 else None,
              'code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'run.py',*sorted((ROOT/'analysis').rglob('*.py'))]},
              'python':sys.version,'executable':sys.executable,'environment_lock_sha256':digest(ROOT/'environments/conda-linux-64.lock'),
              'settings':SETTINGS,'qc_tolerance':{'rtol':RTOL,'atol':ATOL},'inputs':{},'stages':[]}
    manifest.update(schema_version=1, packages=package_versions(), scientific_contract=contract('canonical'),
                    command=[sys.executable, *sys.argv], environment_name=os.environ.get('CONDA_DEFAULT_ENV'),
                    resolved_settings={'arguments': vars(args), 'policies': SETTINGS}, **git_state())
    manifest['resolved_settings_sha256'] = settings_digest(manifest['resolved_settings'])
    manifest['plot_settings'] = {'kind': 'box', 'timepoints': reporting.PLOT_TIMEPOINTS,
                                 'diagnosis_as_d1': args.plot_diagnosis_as_d1,
                                 'cohort_layout': 'shared axes, adjacent boxes plus pooled boxes with cohort-colored points', 'subtype_colors': False,
                                 'timepoint_filter_scope': 'plots only; statistical model settings unchanged'}
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
            if not path.is_file():raise ValueError(f'Input not found: {path}')
            manifest['inputs'][key]={'path':str(path),'sha256':digest(path)}
        from analysis.sample_analysis import extraction
        protocol_config = stage('extraction_protocols', lambda: extraction.load_protocols(args.extraction_protocols))
        manifest['extraction_protocols'] = protocol_config
        frame,qc,schemas=stage('prepare',lambda:prepare(args.inventory,args.circall,args.donors,cohorts))
        frame = extraction.annotate(frame, protocol_config)
        preparation=output/'prepared';preparation.mkdir()
        write_json(preparation/'extraction_protocols.json',protocol_config)
        reporting.table(preparation/'extraction_protocols.csv', extraction.summary(protocol_config))
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
        import numpy as np
        basis=frame.loc[frame.compartment.eq('plasma'),['record_id','cohort','source','sample_id','source_row',
            'dna_total_ng','volume_ml',PRIMARY,'cfDNA_total_ng','dna_total_ng_status']].copy()
        basis['percentage_adjusted_endpoint']=basis.cfDNA_total_ng / basis.volume_ml.where(basis.volume_ml.gt(0))
        comparable=np.isfinite(basis[PRIMARY]) & np.isfinite(basis.percentage_adjusted_endpoint)
        basis['different_measurement_basis']=False
        basis.loc[comparable,'different_measurement_basis']=~np.isclose(basis.loc[comparable,PRIMARY],basis.loc[comparable,'percentage_adjusted_endpoint'],rtol=RTOL,atol=ATOL)
        reporting.table(preparation/'endpoint_basis.csv',basis)
        write_json(preparation/'reconciliation.json',{
            'primary_endpoint':'Recorded unadjusted total DNA / initial plasma volume, never percentage-adjusted',
            'source_revision':'Revised workbook versions are recorded by input hashes; canonical output equality to the old inputs is not expected',
            'measurement_basis_comparison':'Compares unadjusted and percentage-adjusted quantities in the current sources; it is not a comparison of old versus new file versions',
            'comparable_plasma_records':int(comparable.sum()),
            'records_with_different_measurement_basis':int(basis.different_measurement_basis.sum()),
            'identified_circall_formula_zeros_removed':summary['identified_circall_plasma_formula_zeros'],
            'pooled_controls_by_source':summary['controls_by_source'],
            'undosed_pediatric_plasma_records':int((frame.source.eq('pediatric_controls') & frame.compartment.eq('plasma') & frame[PRIMARY].isna()).sum()),
            'qc_holds':summary['qc_hold_records'],
            'parsing':'Direct CIRCALL-style numeric conversion; unavailable inputs propagate only to dependent quantities',
            'inventory':'Long-format compartment records; MNC assay columns are retained separately without copying plasma volume',
            'eligibility':'See eligibility.csv and manifest settings for question-specific retained cohort rules',
        })
        for question in tasks:
            if question=='inventory':
                def inventory_task():
                    result=analyses.availability(frame)
                    reporting.table(output/'inventory/availability.csv',result)
                    if 'circall' in cohorts:
                        reporting.table(output/'inventory/missing_samples_list.csv',
                                        analyses.missing_samples_list(frame))
                        for name, table in analyses.missing_samples_by_hospital(frame).items():
                            reporting.table(output/'inventory'/f'{name}.csv', table)
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
                    if 'circall' in cohorts:
                        csf = analyses.csf_volumes_by_site(frame)
                        reporting.table(output/'volumes/circall_csf_by_site.csv',csf)
                        reporting.csf_site_boxplot(frame, output/'volumes/circall_csf_by_site.png')
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
                    pellet_summary=analyses.blood_pellet_summary(frame,cohorts)
                    reporting.table(output/'yield/blood_pellet_summary.csv',pellet_summary)
                    pellet=frame.loc[frame.compartment.eq('blood pellet') & ~frame.qc_hold]
                    for cohort in cohorts:
                        metrics=(analyses.PELLET_COUNT_METRICS+analyses.YIELD_METRICS[3:]) if cohort=='retrospective' else analyses.YIELD_METRICS[:2]
                        for metric in metrics:
                            if pellet.loc[pellet.cohort.eq(cohort),metric].notna().any():
                                filename=f'{cohort}_{metric.removeprefix("mnc_")}.png'
                                reporting.blood_pellet_plot(pellet,[cohort],metric,output/'yield'/('blood_pellet_'+filename),diagnosis_as_d1=args.plot_diagnosis_as_d1)
                    result=pd.concat([plasma_summary,pellet_summary],ignore_index=True)
                    corr=pd.concat(correlations,ignore_index=True)
                    reporting.table(output/'yield/summary.csv',result)
                    reporting.table(output/'yield/correlations.csv',corr)
                    comparison=analyses.cohort_comparison(frame)
                    reporting.table(output/'yield/cohort_comparison.csv',comparison)
                    for metric in analyses.YIELD_METRICS[:3]:
                        reporting.timepoint_plot(frame,cohorts,metric,output/'yield'/f'{metric}.png',diagnosis_as_d1=args.plot_diagnosis_as_d1)
                        if len(cohorts)>1:
                            reporting.timepoint_plot(frame,cohorts,metric,output/'yield'/f'{metric}_pooled.png',diagnosis_as_d1=args.plot_diagnosis_as_d1,combine_cohorts=True)
                    for x,y in PAIRS:
                        selected_cohorts=[c for c in cohorts if (x,y) in correlation_pairs(c)]
                        if not selected_cohorts: continue
                        reporting.correlation_plot(frame,selected_cohorts,x,y,output/'yield'/f'{x}_vs_{y}.png',diagnosis_as_d1=args.plot_diagnosis_as_d1)
                stage('yield',yield_task)
                events.append(dict(analysis='yield',cohort='all',status='complete',reason=''))
            elif question=='kinetics':
                from analysis.sample_analysis import blood_counts
                stage('kinetics',lambda:blood_counts.run(args.blood_counts if 'circall' in cohorts else None,output/'kinetics',
                      baseline_day_max=args.baseline_day_max,baseline_selection=args.baseline_selection,
                      overlay_max_day=args.overlay_max_day, retrospective_path=args.retrospective_blasts,
                      retrospective_unit=args.retrospective_blast_unit, y_scale=args.kinetics_y_scale))
                for cohort in cohorts:
                    if cohort == 'circall' or args.retrospective_blasts is not None:
                        events.append(dict(analysis='kinetics',cohort=cohort,status='complete',reason='Recorded counts; diagnostic baseline; within-patient trajectories; no fitted model'))
            elif question=='mrd':
                from analysis.sample_analysis import mrd, retrospective_mrd, pooled_mrd
                # Preflight both cohorts before publishing either MRD result set.
                if 'retrospective' in cohorts:
                    retrospective_data = retrospective_mrd.observations(args.inventory, tissue=args.retrospective_mrd_tissue,
                        duplicate_policy=args.retrospective_mrd_duplicate_policy)
                if 'circall' in cohorts:
                    circall_data = mrd.observations(args.circall, unknown_level=args.mrd_unknown_level, negative_level=args.mrd_negative_level)
                if 'retrospective' in cohorts:
                    stage('mrd_retrospective',lambda:retrospective_mrd.run(args.inventory,output/'kinetics/mrd',
                          negative_level=args.mrd_negative_level, tissue=args.retrospective_mrd_tissue,
                          duplicate_policy=args.retrospective_mrd_duplicate_policy))
                    events.append(dict(analysis='mrd',cohort='retrospective',status='complete',reason='Patient/visit MRD_IgTCR paired with treatment_phase TP1/TP2; reported positive-nonquantifiable bounds; no inference'))
                if 'circall' in cohorts:
                    stage('mrd_circall',lambda:mrd.run(args.circall,output/'kinetics/mrd',
                          unknown_level=args.mrd_unknown_level,negative_level=args.mrd_negative_level,write_workbook=False))
                    events.append(dict(analysis='mrd',cohort='circall',status='complete',reason='Patient-level MRD_TP1/TP2; categorical results use explicit assigned display levels'))
                if args.pool_mrd and len(cohorts) == 2:
                    stage('mrd_pooled', lambda: pooled_mrd.run(circall_data, retrospective_data, output/'kinetics/mrd',
                          unknown_level=args.mrd_unknown_level, negative_level=args.mrd_negative_level, positive_nq_level=args.mrd_positive_nq_level))
                    events.append(dict(analysis='mrd', cohort='pooled', status='complete', reason='Descriptive trajectories and fixed-denominator patient-status bars'))
            else:
                for cohort in cohorts:
                    destination=output/'longitudinal'/cohort
                    def model_task(cohort=cohort,destination=destination):
                        tables,audit,notes=analyses.longitudinal(frame,cohort,destination,
                           random_slope=args.mixed_random_slope_sensitivity,outlier_drop_n=args.mixed_outlier_drop_n,diagnosis_as_d1=args.plot_diagnosis_as_d1,
                           followups=args.longitudinal_followups, descriptive_visits=args.longitudinal_descriptive_visits)
                        audits.append(audit);events.extend(notes)
                        for name,data in tables.items():reporting.table(destination/f'{name}.csv',data)
                        return bool(tables)
                    try:
                        has_tables=stage(f'longitudinal_{cohort}',model_task)
                        if has_tables:
                            events.append(dict(analysis='longitudinal',cohort=cohort,status='complete',reason='requested supported analyses completed; see individual availability entries'))
                    except Exception as error:
                        events.append(dict(analysis='longitudinal',cohort=cohort,status='failed',reason=str(error)))
                    meta=frame.loc[frame.cohort.eq(cohort)]
                    if not meta.genetic_subtype.replace({'na':''}).ne('').any():
                        events.append(dict(analysis='subtype_annotations',cohort=cohort,status='unavailable',reason='genetic subtype unavailable'))
                def longitudinal_plots():
                    reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/boxplots.png',longitudinal=True,diagnosis_as_d1=args.plot_diagnosis_as_d1)
                    reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/trajectories.png',longitudinal=True,connect=True,diagnosis_as_d1=args.plot_diagnosis_as_d1)
                    if len(cohorts)>1:
                        reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/boxplots_pooled.png',longitudinal=True,diagnosis_as_d1=args.plot_diagnosis_as_d1,combine_cohorts=True)
                        reporting.timepoint_plot(frame,cohorts,PRIMARY,output/'longitudinal/trajectories_pooled.png',longitudinal=True,connect=True,diagnosis_as_d1=args.plot_diagnosis_as_d1,combine_cohorts=True)
                stage('longitudinal_plots',longitudinal_plots)
                from analysis.sample_analysis import longitudinal_trends
                manifest['plot_settings']['longitudinal_trends'] = stage('longitudinal_trends', lambda:
                    longitudinal_trends.write(frame, cohorts, output/'longitudinal',
                        diagnosis_as_d1=args.plot_diagnosis_as_d1,
                        resamples=args.trend_bootstrap_resamples, seed=args.trend_bootstrap_seed,
                        method=args.trend_bootstrap_method))
                if args.pool_cohorts and len(cohorts) == 2:
                    from analysis.sample_analysis import pooled_trend
                    _, manifest['plot_settings']['pooled_longitudinal_trend'] = stage('pooled_longitudinal_trend', lambda:
                        pooled_trend.write(frame, output/'longitudinal',
                            manifest['plot_settings']['longitudinal_trends']))
        if args.pool_cohorts and len(cohorts) == 2 and {'longitudinal', 'kinetics'}.issubset(tasks):
            from analysis.sample_analysis import yield_wbc_panel
            def combined_yield_wbc():
                summary = pd.read_csv(output/'longitudinal/pooled_trendline_summary.csv').fillna({'interval_omission': ''})
                counts = pd.read_csv(output/'kinetics/circall_blood_count_observations.csv')
                count_settings = json.loads((output/'kinetics/plot_settings.json').read_text())
                return yield_wbc_panel.write(frame, summary, counts,
                    manifest['plot_settings']['longitudinal_trends'], count_settings, output/'longitudinal')
            manifest['plot_settings']['yield_wbc_panels'] = stage('yield_wbc_panels', combined_yield_wbc)
        if args.pool_cohorts and len(cohorts) == 2 and any(t in tasks for t in ('volumes','yield','longitudinal')):
            from analysis.sample_analysis import pooled
            manifest['pooling_settings'] = {'timepoints': args.pooled_timepoints, 'cohort_adjustment': False,
                'scope': 'shared plasma measurements; original eligibility and patient keys; controls once'}
            events.extend(stage('pooled', lambda: pooled.run(frame, output/'pooled', tasks,
                args.pooled_timepoints, diagnosis_as_d1=args.plot_diagnosis_as_d1,
                followups=args.longitudinal_followups, descriptive_visits=args.longitudinal_descriptive_visits)))
        if audits:reporting.table(preparation/'eligibility.csv',pd.concat(audits,ignore_index=True))
        reporting.table(output/'analysis_status.csv',pd.DataFrame(events))
        from analysis.sample_analysis.stats_workbooks import build
        stage('statistics_workbooks', lambda: build(output))
        manifest['analysis_status']=events
        manifest['status']='failed' if any(e['status']=='failed' for e in events) else 'complete'
        if manifest['status'] == 'complete':
            from analysis.artifacts import canonical as validate_artifacts
            validate_artifacts(output, args)
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

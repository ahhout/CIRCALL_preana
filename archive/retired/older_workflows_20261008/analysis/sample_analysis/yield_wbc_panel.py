"""Compose retained pooled yield and WBC views without changing time coordinates."""
from analysis.figure_layout import remove_plot_text
import argparse
from pathlib import Path
import json

import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from analysis.sample_analysis import reporting, blood_counts
from analysis.sample_analysis.policies import PRIMARY, eligible, pooled_controls
from analysis.outputs import engine_directory
from analysis.provenance import ROOT, envelope, digest, utc_now, write_json, verify_inputs


def aligned_days(days, *, offset):
    """Piecewise-linear display coordinates; extrapolate instead of clipping days."""
    anchors = np.array([1., 4., 8., 15., 29., 71.])
    positions = np.arange(len(anchors), dtype=float) + offset
    values = np.asarray(days, dtype=float)
    result = np.interp(values, anchors, positions)
    result = np.where(values < anchors[0], positions[0] + (values-anchors[0])/(anchors[1]-anchors[0]), result)
    return np.where(values > anchors[-1], positions[-1] + (values-anchors[-1])/(anchors[-1]-anchors[-2]), result)


def write(frame, summary, counts, settings, counts_settings, output):
    """Render the canonical panels from existing prepared data and summaries."""
    output = Path(output)
    conventions={'panels':['Pooled DNA yield','CIRCALL WBC'],
                 'yield_x':'Existing equally spaced visit categories',
                 'wbc_x':'Piecewise-linear display between day anchors 1, 4, 8, 15, 29, 71; extrapolate outside anchors; all selected points retained',
                 'shared_labels':['D1','D4','D8','D15','TP1 (D29)','TP2 (D71)'],
                 'wbc_tick_days':[1,4,8,15,29,71],
                 'control':'Yield-only reference; no WBC control measurement',
                 'y_axes':'Logarithmic spacing with ordinary numeric labels',
                 'jitter_seed':42,'inference':'Display composition only; no new analysis'}
    patients={}
    for cohort in ['retrospective','circall']:
        data,_=eligible(frame,cohort,'longitudinal')
        data=reporting.plot_data(data,diagnosis_as_d1=settings['diagnosis_as_d1'])
        data=data.loc[np.isfinite(data[PRIMARY]) & data[PRIMARY].gt(0)]
        patients[cohort]=data.groupby(['patient_key','plot_timepoint'],as_index=False)[PRIMARY].median()
    controls=pooled_controls(frame)
    controls=controls.loc[np.isfinite(controls[PRIMARY]) & controls[PRIMARY].gt(0),PRIMARY].to_numpy()
    visits=(['Control'] if len(controls) else [])+conventions['shared_labels']
    positions={v:i for i,v in enumerate(visits)}
    fig,(top,bottom)=reporting.plt.subplots(2,1,figsize=(13,12),sharex=True)
    rng=np.random.default_rng(42)
    if len(controls):
        top.scatter(rng.uniform(-.08,.08,len(controls)),controls,color=reporting.COLORS['control'],s=18,alpha=.65)
        top.plot([-.15,.15],[np.median(controls)]*2,color=reporting.COLORS['control'],lw=2)
    for cohort,data in patients.items():
        top.scatter(data.plot_timepoint.map(positions).to_numpy()+rng.uniform(-.07,.07,len(data)),data[PRIMARY],
                    color=reporting.COLORS[cohort],s=18,alpha=.4)
    x=summary.plot_timepoint.map(positions).to_numpy(float)
    top.plot(x,summary['median'],color='#303030',marker='o',lw=2)
    top.fill_between(x,summary.ci95_low.to_numpy(float),summary.ci95_high.to_numpy(float),color='#606060',alpha=.2,linewidth=0)
    for row in summary.loc[summary.interval_omission.ne('')].itertuples():
        top.annotate('no CI',(positions[row.plot_timepoint],row.median),xytext=(0,-20),textcoords='offset points',ha='center',fontsize=8)
    reporting.format_log_yaxis(top)
    top.set_xticks(range(len(visits)),visits)
    top.set_title('A  Pooled DNA yield — median and pointwise 95% bootstrap interval',loc='left')
    top.set_ylabel(reporting.LABELS[PRIMARY])
    top.set_xlabel('Visit categories')
    top.grid(axis='y',alpha=.18)
    displayed_counts = counts.copy()
    displayed_counts['display_day'] = aligned_days(counts.display_day, offset=int(bool(len(controls))))
    blood_counts.draw(bottom,displayed_counts,'wbc',baseline_day_max=counts_settings['diagnostic_baseline_day_max'],y_scale='log')
    bottom.set_xticks(range(len(visits)), visits)
    selected_days = displayed_counts.loc[displayed_counts.measurement.eq('wbc') & displayed_counts.selected_for_plot, 'display_day']
    bottom.set_xlim(min(-.45, selected_days.min()-.2), max(len(visits)-.55, selected_days.max()+.2))
    top.tick_params(axis='x', labelbottom=True)
    bottom.set_title('')
    bottom.set_title('B  CIRCALL WBC counts over time',loc='left')
    bottom.set_xlabel('Aligned visits — segmented time scale')
    bottom.tick_params(axis='x',labelsize=9)
    handles=[Line2D([],[],color=reporting.COLORS[c],marker='o',linestyle='',label=label)
             for c,label in [('retrospective','Retrospective yield'),('circall','CIRCALL yield / WBC'),('control','Controls (yield only)')]]
    handles.append(Line2D([],[],color='#303030',marker='o',lw=2,label='Pooled yield median'))
    fig.legend(handles=handles,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.035))
    fig.text(.5,.012,'Visits align across panels; WBC days are positioned proportionally within each visit interval (unequal day spans).\n'
             'All selected WBC measurements retained, including after D71; log-axis zeros remain unplotted. TP2 yield interval omitted.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.105,1,1),h_pad=3)
    output.mkdir(parents=True, exist_ok=True)
    remove_plot_text(fig)
    fig.savefig(output/'yield_wbc_panels.png',dpi=180,bbox_inches='tight')
    fig.savefig(output/'yield_wbc_panels.pdf',bbox_inches='tight')
    reporting.plt.close(fig)
    selected=counts.loc[counts.measurement.eq('wbc') & counts.selected_for_plot]
    assert len(selected)==sum(len(c.get_offsets()) for c in bottom.collections)
    conventions.update(wbc_points_retained=len(selected), yield_visit_summaries=len(summary))
    write_json(output/'yield_wbc_panel_settings.json', conventions)
    return conventions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output-name', default='yield_wbc_panels', choices=['yield_wbc_panels', 'yield_wbc_panels_final', 'yield_wbc_panels_aligned'])
    args=parser.parse_args()
    root=args.run_dir.resolve()
    engine=engine_directory(root,'canonical')
    summary_path=engine/'longitudinal/pooled_trendline_summary.csv'
    if not summary_path.exists():
        summary_path=root/'.audit/supplements/pooled_trend/pooled_trendline_summary.csv'
    settings_path=engine/'longitudinal/trendline_settings.json'
    inputs={'yield_summary':summary_path,'yield_settings':settings_path,
            'prepared':engine/'prepared/inventory.csv',
            'counts':engine/'kinetics/circall_blood_count_observations.csv',
            'count_settings':engine/'kinetics/plot_settings.json'}
    audit=root/'.audit/supplements'/args.output_name
    destination=root/'sample_analysis/longitudinal'/f'{args.output_name}.png'
    if audit.exists() or destination.exists():
        parser.error('Panel output already exists; refusing replacement')
    original={p:digest(p) for p in root.rglob('*') if p.is_file()}
    settings=json.loads(settings_path.read_text())
    counts_settings=json.loads(inputs['count_settings'].read_text())
    conventions={'panels':['Pooled DNA yield','CIRCALL WBC'],
                 'yield_x':'Existing equally spaced visit categories',
                 'wbc_x':'Piecewise-linear display between day anchors 1, 4, 8, 15, 29, 71; extrapolate outside anchors; all selected points retained',
                 'shared_labels':['D1','D4','D8','D15','TP1 (D29)','TP2 (D71)'],
                 'wbc_tick_days':[1,4,8,15,29,71],
                 'control':'Yield-only reference; no WBC control measurement',
                 'y_axes':'Logarithmic spacing with ordinary numeric labels',
                 'jitter_seed':42,'inference':'Display composition only; no new analysis'}
    record=envelope('canonical',conventions,inputs,
                    [Path(__file__),ROOT/'analysis/sample_analysis/reporting.py',ROOT/'analysis/sample_analysis/blood_counts.py',ROOT/'analysis/sample_analysis/policies.py'],
                    ROOT/'environments/conda-linux-64.lock')
    frame=pd.read_csv(inputs['prepared'],low_memory=False)
    summary=pd.read_csv(summary_path).fillna({'interval_omission':''})
    counts=pd.read_csv(inputs['counts'])
    validation = write(frame, summary, counts, settings, counts_settings, audit)
    verify_inputs(record['inputs'])
    assert all(digest(p)==h for p,h in original.items())
    import shutil
    shutil.copy2(__file__,audit/'create_yield_wbc_panel.py')
    publications=[]
    for ext in ['png','pdf']:
        source=audit/f'yield_wbc_panels.{ext}'
        target=destination.with_suffix('.'+ext)
        shutil.copy2(source,target)
        publications.append({'path':str(target.relative_to(root)),'source':str(source.relative_to(root)),'sha256':digest(target)})
    record.update(status='complete',finished_utc=utc_now(),publications=publications,
                  validation={'wbc_points_retained':validation['wbc_points_retained'],'yield_visit_summaries':len(summary),'original_files_unchanged':len(original)})
    write_json(audit/'manifest.json',record)
    print('Created',destination)
    print('Retained WBC points:',validation['wbc_points_retained'])

if __name__=='__main__':
    main()

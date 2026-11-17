"""Select and export the established Layer 2 figure families."""
from collections import defaultdict

from analysis.utils.plot_style import save_figure
from ..calendar_volumes import calendar_groups, calendar_coverage
from .calendar_volumes import calendar_figure
from .distributions import grant_figure
from .receipt import receipt_figure


def figures(destination, rows, d, pooled=False, controls=False, reference_controls=(), comparisons=(), pdf_output=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    artifacts=[]
    def save(fig, name, grant=False):
        if not grant:fig.tight_layout()
        for ext in (('png','pdf') if pdf_output else ('png',)):
            path=destination/f'{name}.{ext}'
            path.parent.mkdir(parents=True, exist_ok=True)
            save_figure(fig,path)
            artifacts.append(path)
        plt.close(fig)
    if not pooled and rows:
        fig=receipt_figure(rows, controls)
        save(fig,'receipt_status')
    for field, definition in d['metrics'].items():
        groups=defaultdict(list)
        reference_cohorts=definition.get('reference_control_cohorts',[])
        references=[dict(r,visit=definition['reference_control_visit']) for r in reference_controls
                    if not controls and r.get('control',False) and r['cohort'] in reference_cohorts]
        for r in [*rows,*references]:
            reference=not controls and r.get('control',False) and r['cohort'] in reference_cohorts
            if r['receipt'] not in ('received','received_early') or r['specimen'] not in definition['specimens'] or r['cohort'] in definition.get('exclude_cohorts',[]):
                continue
            if not controls and not reference and 'plot_visits' in definition and r['visit'] not in definition['plot_visits']:
                continue
            if pooled and not reference and (r['specimen'] not in definition['pool'] or
                           definition.get('pooled_plot_visits')!='all' and r['visit'] not in d['pooled_visits']):
                continue
            value=r['measurements'][field]['value']
            if value is not None:
                assay = 'specimen_volume' if field=='extraction_input_volume_ml' else 'cfDNA_size' if pooled and field=='cfdna_avg_size_bp' else 'plasma_DNA' if r['specimen']=='plasma' else r['assay']
                groups[(r['specimen'],assay)].append(r)
        for (specimen,assay), group in sorted(groups.items()):
            overall=definition.get('plot_grouping')=='overall'
            visits=['Overall'] if overall else [v for v in d['visits']+['control','unclassified'] if any(r['visit']==v for r in group)]
            if not controls and 'plot_visits' in definition:
                visits=([definition['reference_control_visit']] if any(r.get('control',False) for r in group) else [])+definition['plot_visits']
            fig=grant_figure(group,field,definition,visits,pooled,controls,d['plot_jitter_seed'],comparisons,
                             scope='pooled' if pooled else rows[0]['cohort'] if rows else None)
            suffix=f'__{assay}' if sum(key[0]==specimen for key in groups)>1 else ''
            save(fig,f'{specimen.replace(" ","_")}/{field}{suffix}',grant=True)
    if not pooled and not controls:
        calendar = calendar_groups(rows, d)
        for coverage in calendar_coverage(rows, d):
            key = (coverage['cohort'], coverage['specimen'])
            fig = calendar_figure(calendar[key], coverage)
            save(fig, f"{coverage['specimen']}/extraction_input_volume_ml_by_collection_date", grant=True)
    return artifacts


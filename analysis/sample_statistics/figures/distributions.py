"""Sample distributions with established scales, control references and jitter."""
from analysis.figure_layout import remove_plot_text
from analysis.plot_style import COHORT_COLORS, COHORT_MARKERS, BOX_STYLE, style_axes
from ..labels import MEASUREMENT_LABELS


def grant_figure(group, field, definition, visits, pooled, controls, jitter_seed, comparisons=(), *, scope=None):
    """Original-unit distributions with deterministic display jitter only."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import LogLocator, NullFormatter, FuncFormatter
    import numpy as np
    import textwrap

    from analysis.plot_style import scatter_points, point_handles
    patient_cohorts = {r['cohort'] for r in group if not r.get('control', False)}
    inferred = patient_cohorts or {r['cohort'] for r in group}
    circall_only = not pooled and (scope == 'circall' if scope is not None else inferred == {'circall'})
    palette=COHORT_COLORS
    markers=COHORT_MARKERS
    cohorts=sorted({r['cohort'] for r in group})
    rng=np.random.default_rng(definition.get('plot_jitter_seed',jitter_seed))
    logarithmic=definition.get('plot_scale')=='log'
    overall=definition.get('plot_grouping')=='overall'
    compact=pooled
    fig,ax=plt.subplots(figsize=(max(7.8,2.4+len(visits)*1.05),5.8))
    fig.subplots_adjust(left=.12,right=.98,bottom=.23,top=.96)
    labels=[]
    visit_labels={'diag':'Diagnosis','d4':'Day 4','d8':'Day 8','d15':'Day 15','control':'Controls',
                  'unclassified':'Unclassified'}
    if field in ('dna_ng_per_ml_plasma', 'cfdna_ng_per_ml_plasma'):
        visit_labels.update({'d4':'D4', 'd8':'D8', 'd15':'D15',
                             'tp1':'TP1 (D29)', 'tp2':'TP2 (D71)'})
    visit_labels.update(definition.get('plot_visit_labels',{}))
    for i,visit in enumerate(visits):
        subset=group if overall else [r for r in group if r['visit']==visit]
        values=[r['measurements'][field]['value'] for r in subset]
        positive=[v for v in values if v>0] if logarithmic else values
        if positive:
            ax.boxplot([positive],positions=[i],widths=.5,showfliers=False,manage_ticks=False,
                       **BOX_STYLE)
        for cohort in cohorts:
            rows=sorted((r for r in subset if r['cohort']==cohort and
                         (not logarithmic or r['measurements'][field]['value']>0)),
                        key=lambda r:r['measurements'][field]['value'])
            points=[r['measurements'][field]['value'] for r in rows]
            scatter_points(ax,i+rng.uniform(-.17,.17,len(points)),points,cohort,
                           [r.get('center','unknown') for r in rows],circall_only=circall_only,
                       s=25,alpha=.7,edgecolors='white',linewidths=.35,zorder=3,label=cohort)
        name=visit_labels.get(visit,visit.upper() if visit.startswith('tp') else visit)
        label=textwrap.fill(name,14)+f'\nn={len(subset)} · P={len({r["subject_key"] for r in subset})}'
        if compact:label=textwrap.fill(name,14)+f'\nn={len(subset)}'
        labels.append(label)
    if logarithmic:
        ax.set_yscale('log',base=10,nonpositive='mask')
        ax.yaxis.set_major_locator(LogLocator(base=10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_: f'{value:,.0f}' if value>=1 else f'{value:g}'))
        ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(range(len(visits)),labels,fontsize=9)
    ax.set_xlim(-.6,len(visits)-.4)
    units={'dna_ng_per_ml_plasma':'DNA (ng/mL plasma)','cfdna_ng_per_ml_plasma':'cfDNA (ng/mL plasma)'}
    ax.set_ylabel(units.get(field,f"{MEASUREMENT_LABELS[field]} ({definition['unit']})"),fontsize=12,labelpad=10)
    ax.set_xlabel('Timepoint' if not controls and not overall else '',fontsize=11,labelpad=12)
    title='DNA yield per mL of plasma' if field=='dna_ng_per_ml_plasma' else MEASUREMENT_LABELS[field]
    specimen_label={'plasma':'Plasma','CSF':'CSF','blood pellet':'Blood pellet','bone marrow':'Bone marrow'}[group[0]['specimen']]
    population='Controls' if controls else 'Patient samples'
    reference=not controls and any(r.get('control',False) for r in group)
    if reference:population+=' + control references'
    ax.set_title(f'{title}\n{specimen_label} · {population}',
                 fontsize=15,fontweight='medium',pad=18)
    if compact:ax.set_title('')
    style_axes(ax)
    ax.tick_params(axis='x',length=0,pad=9)
    handles=[h for c in cohorts for h in point_handles(c,
             [r.get('center','unknown') for r in group if r['cohort']==c],circall_only=circall_only)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.55,.065),ncol=len(handles),frameon=False,fontsize=10)
    note='Box: median and IQR; whiskers: 1.5 × IQR. Points: samples. n: samples; P: participants.'
    if logarithmic:note+=' Log y-axis.'
    if pooled:note+='\nBoxes combine available samples across cohorts.' if overall else '\nCohort availability varies by timepoint; boxes combine available samples.'
    if reference:note+='\nControl cohorts share one reference distribution; excluded from patient summaries.'
    if logarithmic and any(r['measurements'][field]['value']<=0 for r in group):
        note+='\nNonpositive values are counted but not plotted; no pseudocount.'
    if not compact:fig.text(.55,.025,note,ha='center',va='top',fontsize=8,color='#52616B')
    if logarithmic and not any(r['measurements'][field]['value']>0 for r in group):
        ax.set_ylim(1,10)
        ax.text(.5,.5,'No positive values to plot',transform=ax.transAxes,ha='center')
    relevant=[r for r in comparisons if r['field']==field and r['specimen']==group[0]['specimen']]
    brackets=[]
    for result in relevant if not controls else []:
        if (result['field']!=field or result['specimen']!=group[0]['specimen'] or not result['display']
                or not result['significance'].startswith('*') or result['visit_2'] not in visits):
            continue
        reference_visits=[definition['reference_control_visit']]
        positions=[visits.index(v) for v in reference_visits if v in visits]
        if positions:
            brackets.append((sum(positions)/len(positions),visits.index(result['visit_2']),result['significance'],result.get('test','')))
    if brackets:
        fig.subplots_adjust(top=.68)
        if not compact:ax.set_title(ax.get_title(),y=1.42,pad=18)
        for level,(left,right,stars,test) in enumerate(brackets):
            y=1.04+level*.15
            ax.plot([left,left,right,right],[y,y+.025,y+.025,y],transform=ax.get_xaxis_transform(),
                    color='#243746',linewidth=1,clip_on=False)
            label=f'{stars}  {test}' if compact and level==len(brackets)-1 and test else stars
            ax.text((left+right)/2,y+.03,label,transform=ax.get_xaxis_transform(),
                    ha='center',va='bottom',fontsize=13,color='#243746')
    if relevant and not controls and not compact:
        note+='\nStars: Holm-adjusted participant-level tests; nonsignificant/unavailable brackets omitted.'
        if pooled:note+=' Controls and patient cohorts combined for testing.'
        elif reference:note+=' Tests use matching-cohort controls only.'
        fig.texts[-1].set_text(note)
    remove_plot_text(fig)
    return fig


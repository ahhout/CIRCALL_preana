"""Display-only log scaling must preserve zeros in analysis tables."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import pytest

from analysis.sample_statistics.core import aggregate,assessment,prepare
from analysis.sample_statistics.reporting import figures
from tests.fixtures.sample_statistics import fixture,D,ASOF

class PlotScaleTests(unittest.TestCase):
    def test_control_references_precede_diagnosis_without_mixing_samples(self):
        from matplotlib.figure import Figure
        field='dna_ng_per_ml_plasma'
        d={**D,'metrics':{field:D['metrics'][field]}}
        def row(cohort,control,value):
            return dict(cohort=cohort,control=control,specimen='plasma',assay='cfdna',
                        visit='control' if control else 'diag',receipt='received',subject_key=f'{cohort}:{control}',
                        measurements={field:dict(value=value)})
        references=[row('circall',True,5),row('retrospective',True,999)]
        for scope in ('circall','retrospective','pooled'):
            rows=[row(c,False,20) for c in (['circall','retrospective'] if scope=='pooled' else [scope])]
            before=deepcopy([rows,references]);seen=[]
            def capture(fig,path,**kwargs):
                if Path(path).stem!=field or Path(path).suffix!='.png':return
                ax=fig.axes[0];ticks=[t.get_text() for t in ax.get_xticklabels()]
                suffix='' if scope=='pooled' else ' · P=2'
                self.assertEqual(ticks[0],'Controls\nn=2'+suffix)
                suffix='' if scope=='pooled' else f' · P={len(rows)}'
                self.assertEqual(ticks[1],f'Diagnosis\nn={len(rows)}'+suffix)
                self.assertEqual(len(ticks),7)
                points=[tuple(p) for c in ax.collections for p in c.get_offsets()]
                self.assertEqual(sorted(p[1] for p in points),[5]+[20]*len(rows)+[999])
                self.assertTrue(all(abs(x-(0 if y in (5,999) else 1))<.2 for x,y in points))
                seen.append(True)
            with TemporaryDirectory() as temp,patch.object(Figure,'savefig',capture):
                figures(Path(temp),rows,d,pooled=scope=='pooled',reference_controls=references)
            self.assertEqual(len(seen),1)
            self.assertEqual([rows,references],before)

    def test_grant_dna_plot_keeps_single_cohort_visits_and_values(self):
        from matplotlib.figure import Figure
        field='dna_ng_per_ml_plasma'
        rows=[dict(cohort=c,control=False,specimen='plasma',assay='cfdna',
                   visit=v,receipt='received',subject_key=c,
                   measurements={field:dict(value=value)})
              for c,v,value in [('circall','diag',10),('retrospective','diag',20),
                                ('circall','d4',0),('circall','d4',30),('circall','tp2',40),('retrospective','relapse',999)]]
        d={**D,'metrics':{field:D['metrics'][field]}}
        before=deepcopy(rows);seen=[]
        def capture(fig,path,**kwargs):
            if Path(path).suffix!='.png':return
            ax=fig.axes[0]
            ticks=[t.get_text() for t in ax.get_xticklabels()]
            self.assertEqual([t.split('\n')[0] for t in ticks],['Diagnosis','D4','D8','D15','TP1 (D29)','TP2 (D71)'])
            self.assertEqual(ticks[1],'D4\nn=2')
            self.assertEqual(ticks[2],'D8\nn=0')
            self.assertEqual(ax.get_yscale(),'log')
            points=[tuple(p) for collection in ax.collections for p in collection.get_offsets()]
            self.assertEqual(sorted(p[1] for p in points),[10,20,30,40])
            self.assertEqual(kwargs['dpi'],300)
            seen.append(points)
        with TemporaryDirectory() as temp,patch.object(Figure,'savefig',capture):
            figures(Path(temp),rows,d,pooled=True)
            figures(Path(temp),rows,d,pooled=True)
        self.assertEqual(seen[0],seen[1])
        self.assertEqual(rows,before)

    def test_overall_metrics_cover_all_applicable_scopes_and_specimens(self):
        from matplotlib.figure import Figure
        fields=('extraction_input_volume_ml','elution_volume_ul','cfdna_avg_size_bp','cfdna_fraction')
        with TemporaryDirectory() as temp:
            for field in fields:
                definition=D['metrics'][field]
                for specimen in definition['specimens']:
                    for scope,controls in [('circall',False),('retrospective',False),
                                           ('circall',True),('retrospective',True),('pooled',False)]:
                        with self.subTest(field=field,specimen=specimen,scope=scope,controls=controls):
                            cohorts=['circall','retrospective'] if scope=='pooled' else [scope]
                            rows=[dict(cohort=c,control=controls,specimen=specimen,assay='cfdna',
                                       visit=v,receipt='received',subject_key=c,
                                       measurements={field:dict(value=value)})
                                  for c in cohorts for v,value in [('diag',1),('tp1',2),('d4',3)]]
                            eligible=[r for r in rows if r['cohort'] not in definition.get('exclude_cohorts',[])
                                      and (scope!='pooled' or specimen in definition['pool'] and r['visit'] in D['pooled_visits'])]
                            seen=[]
                            def capture(fig,path,**kwargs):
                                if Path(path).stem!=field or Path(path).suffix!='.png':return
                                ax=fig.axes[0]
                                self.assertEqual([t.get_text() for t in ax.get_xticklabels()],
                                                 [f'Overall\nn={len(eligible)}'+('' if scope=='pooled' else f' · P={len({r["subject_key"] for r in eligible})}')])
                                values=[float(p[1]) for collection in ax.collections for p in collection.get_offsets()]
                                self.assertEqual(sorted(values),sorted(r['measurements'][field]['value'] for r in eligible))
                                seen.append(True)
                            before=deepcopy(rows)
                            with patch.object(Figure,'savefig',capture):
                                figures(Path(temp),rows,{**D,'metrics':{field:definition}},pooled=scope=='pooled',controls=controls)
                            self.assertEqual(rows,before)
                            self.assertEqual(len(seen),int(bool(eligible)))

    def test_pooled_size_combines_cohorts_in_each_specimen_bin(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/'synthetic.xlsx';fixture(source)
            prepared,_,_=prepare(source,'circall',True,assessment(ASOF),D)
            first=next(r for r in prepared if not r['control'] and r['receipt']=='received')
            rows=[]
            for specimen in ('plasma','CSF'):
                for cohort,values in [('retrospective',[100,120]),('circall',[180,200])]:
                    for index,value in enumerate(values):
                        row=deepcopy(first);row.update(specimen=specimen,cohort=cohort,subject_key=f'{cohort}:{index}',
                                                      assay='cfdna' if cohort=='retrospective' else 'not_recorded')
                        row['measurements']['cfdna_avg_size_bp']['value']=value;rows.append(row)
            d={**D,'metrics':{'cfdna_avg_size_bp':D['metrics']['cfdna_avg_size_bp']}}
            tables=aggregate(rows,d,pooled=True)
            by_visit=[r for r in tables['measurements'] if r['view']=='visit']
            self.assertEqual(len(by_visit),2)
            self.assertTrue(all(r['n']==4 and r['median']==150 for r in by_visit))
            boxes=[];points=[]
            from matplotlib.axes import Axes
            from matplotlib.figure import Figure
            original_box=Axes.boxplot;original_scatter=Axes.scatter
            def capture_box(ax,values,**kwargs):
                boxes.append((list(values[0]),kwargs['positions']))
                return original_box(ax,values,**kwargs)
            def capture_scatter(ax,x,y,**kwargs):
                points.append((list(x),kwargs['color'],kwargs['label']))
                return original_scatter(ax,x,y,**kwargs)
            with patch.object(Axes,'boxplot',capture_box),patch.object(Axes,'scatter',capture_scatter),patch.object(Figure,'savefig'):
                figures(Path(temp)/'figures',rows,d,pooled=True)
            self.assertEqual(len(boxes),2)
            self.assertTrue(all(sorted(values)==[100,120,180,200] and positions==[0] for values,positions in boxes))
            self.assertEqual({color for _,color,_ in points},{'#0072B2','#D55E00'})
            self.assertEqual({label for _,_,label in points},{'retrospective','circall'})
            self.assertTrue(all(all(abs(v)<=.17 for v in x) for x,_,_ in points))

    def test_albumin_and_din_are_excluded_from_layer2_metrics(self):
        self.assertNotIn('MNC_albumin_ng_per_uL',D['metrics'])
        self.assertNotIn('MNC_DIN',D['metrics'])

    def check(self,zero_only=False,controls=False,pooled=False,specimen="plasma"):
        with TemporaryDirectory() as temp:
            source=Path(temp)/'synthetic.xlsx';fixture(source)
            rows,issues,_=prepare(source,'circall',True,assessment(ASOF),D)
            first=deepcopy(next(r for r in rows if r['control']==controls and r['receipt']=='received'))
            first['specimen']=specimen
            first['assay']='not_recorded'
            second=deepcopy(first)
            for row,value in ((first,0),(second,0 if zero_only else 10)):
                row['measurements']['dna_concentration_ng_per_ul']['value']=value
            selected=[first,second];before=deepcopy(selected);seen={}
            from matplotlib.figure import Figure
            def capture(fig,path,**kwargs):
                if Path(path).suffix!='.png':return
                ax=fig.axes[0]
                seen[Path(path).stem]={'scale':ax.get_yscale(),'title':ax.get_title(),
                                      'ticks':[x.get_text() for x in ax.get_xticklabels()],
                                      'texts':[x.get_text() for x in ax.texts],
                                      'points':[float(v[1]) for c in ax.collections for v in c.get_offsets()]}
            with patch.object(Figure,'savefig',capture):
                figures(Path(temp)/'figures',selected,D,pooled=pooled,controls=controls)
            self.assertEqual(selected,before)
            for field,definition in D['metrics'].items():
                if field in seen:self.assertEqual(seen[field]['scale'],definition.get('plot_scale','linear'))
            for plot in seen.values():
                self.assertEqual(plot['title'],'')
            plot=seen['dna_concentration_ng_per_ul']
            self.assertNotIn('nonpositive', ' '.join(plot['ticks']))
            self.assertTrue(all(v>0 for v in plot['points']))
            table=aggregate(selected,D,pooled=pooled)
            concentration=next(r for r in table['measurements'] if r['field']=='dna_concentration_ng_per_ul' and r['view']=='visit')
            self.assertEqual(concentration['n'],2);self.assertEqual(concentration['mean'],0 if zero_only else 5)
            if zero_only:self.assertIn('No positive values to plot',plot['texts'])

    def test_blood_pellet_subtitle(self):self.check(specimen='blood pellet')
    def test_log_scale_and_zero_counts(self):self.check()
    def test_all_zero_concentration(self):self.check(zero_only=True)
    def test_controls_log_scale(self):self.check(controls=True)
    def test_pooled_log_scale(self):self.check(pooled=True)

@pytest.mark.parametrize('field', ['dna_ng_per_ml_plasma', 'cfdna_ng_per_ml_plasma'])
@pytest.mark.parametrize('scope', ['circall', 'retrospective', 'pooled'])
@pytest.mark.parametrize('controls', [False, True])
def test_per_ml_timepoint_style_preserves_existing_populations(tmp_path, field, scope, controls):
    from matplotlib.figure import Figure
    from matplotlib.text import Text
    from analysis.figure_layout import FONT_FAMILY, FONT_SIZE, LEGEND_GAP_POINTS
    d={**D,'metrics':{field:D['metrics'][field]}}
    visits=['control'] if controls else ['diag','d4','d8','d15','tp1','tp2','relapse']
    cohorts=['circall','retrospective'] if scope=='pooled' else [scope]
    rows=[dict(cohort=cohort,control=controls,specimen='plasma',assay='cfdna',
               visit=visit,receipt='received',subject_key=f'{cohort}-{visit}',
               measurements={field:dict(value=10+index)})
          for cohort in cohorts for index,visit in enumerate(visits)]
    before=deepcopy(rows)
    seen=[]
    def capture(fig,path,**kwargs):
        if Path(path).suffix!='.png' or Path(path).stem!=field:return
        ax=fig.axes[0]
        expected=visits
        if not controls:
            if field=='dna_ng_per_ml_plasma':expected=D['metrics'][field]['plot_visits']
            elif scope=='pooled':expected=D['pooled_visits']
        labels={'control':'Controls','diag':'Diagnosis','d4':'D4','d8':'D8','d15':'D15',
                'tp1':'TP1 (D29)','tp2':'TP2 (D71)','relapse':'relapse'}
        assert [t.get_text().split('\n')[0] for t in ax.get_xticklabels()]==[labels[v] for v in expected]
        points=[float(point[1]) for c in ax.collections for point in c.get_offsets()]
        assert sorted(points)==sorted(r['measurements'][field]['value'] for r in rows if r['visit'] in expected)
        assert ax.get_yscale()=='log'
        assert ax.get_ylabel()==('DNA' if field.startswith('dna_') else 'cfDNA')+' (ng/mL plasma)'
        for text in fig.findobj(Text):
            assert text.get_fontfamily()==[FONT_FAMILY] and text.get_fontsize()==FONT_SIZE
        renderer=fig.canvas.get_renderer()
        bottom=min(t.get_window_extent(renderer).y0 for t in ax.get_xticklabels())
        if ax.get_xlabel():bottom=min(bottom,ax.xaxis.label.get_window_extent(renderer).y0)
        gap=(bottom-fig.legends[0].get_window_extent(renderer).y1)*72/fig.dpi
        assert gap>=LEGEND_GAP_POINTS-.01
        assert len(ax.lines)>0 and not ax.get_title()
        seen.append(True)
    with patch.object(Figure,'savefig',capture):
        figures(tmp_path,rows,d,pooled=scope=='pooled',controls=controls)
    # Existing pooled cfDNA eligibility excludes the control visit; styling must
    # not create a new pooled control population.
    expected_plots=[] if controls and scope=='pooled' and field=='cfdna_ng_per_ml_plasma' else [True]
    assert seen==expected_plots and rows==before


if __name__=='__main__':unittest.main()

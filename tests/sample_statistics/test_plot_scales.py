"""Display-only log scaling must preserve zeros in analysis tables."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from analysis.sample_statistics.core import aggregate,assessment,prepare
from analysis.sample_statistics.reporting import figures
from tests.sample_statistics.test_statistics import fixture,D,ASOF

class PlotScaleTests(unittest.TestCase):
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
            self.assertEqual({color for _,color,_ in points},{'#247B89','#B75B28'})
            self.assertEqual({label for _,_,label in points},{'retrospective','circall'})
            self.assertTrue(all(set(x)=={0} for x,_,_ in points))

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
            for name,plot in seen.items():
                self.assertNotIn('plasma_DNA',plot['title'])
                self.assertNotIn('not_recorded',plot['title'])
                if name!='receipt_status':
                    label={'plasma':'Plasma','blood pellet':'Blood pellet'}[specimen]
                    self.assertEqual(plot['title'].split('\n')[1],label+' · '+('Controls' if controls else 'Patient samples'))
            plot=seen['dna_concentration_ng_per_ul']
            self.assertIn('nonpositive', ' '.join(plot['ticks']))
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

if __name__=='__main__':unittest.main()

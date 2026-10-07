"""Synthetic integrity rules, grouping, Excel/privacy and execution acceptance."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from analysis.data_integrity.checks import load_rules, inspect_cohort, group_findings, summarize
from analysis.data_integrity.reporting import write_workbook, validate_workbook
from analysis.data_integrity.runner import arguments, main, preflight, run
from analysis.provenance import ROOT, digest
from analysis.sample_io import read_sheet


def fixture(path, overrides=None, sheets=('Inventaire',), caches=None):
    rules=load_rules(ROOT/'configs/definitions/data_integrity.json')
    headers=rules['required']+['timepoint','dna_id','extraction_date','unknown_extra','extraction_status']
    good={'sample_id':'SYNTHETIC-1','specimen_type':'plasma','extraction_input_volume_ml':2,
          'elution_volume_ul':50,'dna_concentration_ng_per_ul':2,'dna_total_ng':100,
          'dna_ng_per_ml_plasma':50,'cfdna_fraction':.5,'cfdna_concentration_ng_per_ul':1,
          'cfdna_total_ng':50,'cfdna_ng_per_ml_plasma':25,'cfdna_avg_size_bp':170,
          'timepoint':'diag','dna_id':'SYNTHETIC-DNA','unknown_extra':'PRIVATE_SENTINEL'}
    wb=Workbook();wb.remove(wb.active)
    for name in sheets:
        ws=wb.create_sheet(name);ws.append(headers)
        for changes in overrides or [{}]:
            data={**good,**changes};ws.append([data.get(h) for h in headers])
        ws.cell(50,1).number_format='@'  # formatting only, never a sample
    if caches is None:
        wb.save(path)
    else:
        from io import BytesIO
        data=BytesIO();wb.save(data)
        with ZipFile(data) as zin,ZipFile(path,'w') as zout:
            for item in zin.infolist():
                raw=zin.read(item.filename)
                if item.filename=='xl/worksheets/sheet1.xml':
                    for coordinate,(kind,value) in caches.items():
                        pattern=rb'<c\b[^>]*\br="'+coordinate.encode()+rb'"[^>]*>.*?</c>'
                        def repl(m):
                            cell=m.group(0)
                            if kind=='str':cell=cell.replace(b'>',b' t="str">',1)
                            return re.sub(rb'<v\s*(?:/>|>.*?</v>)',b'<v>'+str(value).encode()+b'</v>',cell)
                        raw,n=re.subn(pattern,repl,raw,flags=re.S)
                        assert n==1
                zout.writestr(item,raw)
    return {h:__import__('openpyxl').utils.get_column_letter(i) for i,h in enumerate(headers,1)}


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'synthetic.xlsx'
        self.rules=load_rules(ROOT/'configs/definitions/data_integrity.json')

    def inspect(self,path=None,cohort='retrospective',controls=True):
        return inspect_cohort(path or self.source,cohort,controls,self.rules)

    def test_good_calculations_and_formatting_rows(self):
        fixture(self.source);before=digest(self.source)
        result=self.inspect()
        self.assertEqual(result['summary']['errors'],0)
        self.assertEqual(result['sheets'][0]['rows'],1)
        self.assertEqual(sum(c['assessed'] for c in result['coverage'] if c['check']=='arithmetic'),5)
        self.assertEqual(digest(self.source),before)
        self.assertTrue(any(c['reason']=='no_semantic_rule' for c in result['coverage']))

    def test_each_calculation_detects_inconsistent_value(self):
        for field in [c['output'] for c in self.rules['calculations']]:
            with self.subTest(field=field):
                fixture(self.source,[{field:999}])
                self.assertTrue(any(i['rule']=='arithmetic' and i['field']==field for i in self.inspect()['findings']))

    def test_empty_result_cells_keep_distinct_source_coordinates(self):
        cols=fixture(self.source,[{'dna_total_ng':None},{'dna_total_ng':None}])
        findings=[i for i in self.inspect()['findings'] if i['rule']=='missing_result' and i['field']=='dna_total_ng']
        self.assertEqual({i['cell'] for i in findings},{cols['dna_total_ng']+'2',cols['dna_total_ng']+'3'})
        self.assertEqual(group_findings(findings)[0]['count'],2)

    def test_zero_missing_future_decimal_qualifiers_dates_and_bounds(self):
        fixture(self.source,[{'dna_concentration_ng_per_ul':0,'dna_total_ng':0,'dna_ng_per_ml_plasma':0,
                              'cfdna_concentration_ng_per_ul':0,'cfdna_total_ng':0,'cfdna_ng_per_ml_plasma':0},
                             {h:None for h in self.rules['required'] if h!='specimen_type'},
                             {'elution_volume_ul':'50,0','cfdna_avg_size_bp':'<200','extraction_date':'ambiguous PRIVATE_DATE'},
                             {'cfdna_fraction':85,'extraction_input_volume_ml':0}])
        result=self.inspect();issues=result['findings']
        self.assertFalse(any(i['rule']=='false_zero' for i in issues))
        for rule in ['numeric_text','number_text','date_text','number_invalid','denominator']:
            self.assertTrue(any(i['rule']==rule for i in issues),rule)
        self.assertNotIn('PRIVATE_DATE',json.dumps(result))

    def test_caches_intentional_blank_missing_and_false_zero(self):
        cols=fixture(self.source)
        out=cols['dna_total_ng']
        fixture(self.source,[{'dna_total_ng':'=1*0','dna_concentration_ng_per_ul':None},
                             {'dna_total_ng':'=IF(FALSE,1,"")','dna_concentration_ng_per_ul':None},
                             {'dna_total_ng':'=1+2','dna_concentration_ng_per_ul':None}],
                caches={out+'2':('n',0),out+'3':('str','')})
        sheet=read_sheet(self.source,'Inventaire')
        self.assertEqual(sheet.rows[1][int(__import__('openpyxl').utils.column_index_from_string(out))-1].cached_type,'str')
        issues=self.inspect()['findings']
        self.assertTrue(any(i['rule']=='false_zero' and i['cell']==out+'2' for i in issues))
        self.assertFalse(any(i['rule']=='cache_missing' and i['cell']==out+'3' for i in issues))
        self.assertTrue(any(i['rule']=='cache_missing' and i['cell']==out+'4' for i in issues))

    def test_formula_reference_checks(self):
        cols=fixture(self.source)
        fixture(self.source,[{'dna_total_ng':'='+cols['dna_total_ng']+'2'},
                             {'cfdna_fraction':'='+cols['dna_id']+'3'},
                             {'dna_total_ng':'='+cols['elution_volume_ul']+'2'},
                             {'dna_total_ng':'=#REF!*2'}])
        found={i['rule'] for i in self.inspect()['findings']}
        self.assertTrue({'self_reference','identifier_reference','cross_row_reference','broken_reference'}<=found)

    def test_duplicate_missing_headers_and_unheaded_cells(self):
        fixture(self.source)
        wb=load_workbook(self.source);ws=wb.active
        ws.cell(1,2,'sample_id');ws.cell(1,3,None).value=None
        wb.save(self.source);wb.close()
        rules={i['rule'] for i in self.inspect()['findings']}
        self.assertTrue({'header_missing','header_duplicate','unheaded_data'}<=rules)

    def test_missing_and_unreadable_sources_and_controls(self):
        self.assertGreater(self.inspect()['summary']['errors'],0)
        self.source.write_text('not an xlsx')
        self.assertEqual(self.inspect()['findings'][0]['rule'],'file_unreadable')
        fixture(self.source,sheets=('cohorte_lal',))
        self.assertEqual(len(self.inspect(cohort='circall',controls=False)['sheets']),1)
        self.assertTrue(any(i['rule']=='sheet_missing' for i in self.inspect(cohort='circall')['findings']))

    def test_grouping_boundaries_sources_sheets_rules_and_structural(self):
        base={'source':'synthetic.xlsx','sheet':'Inventaire','field':'tube','rule':'whitespace',
              'severity':'review','issue':'Whitespace','action':'Trim','scope':None}
        for count in [0,1,9,10,11]:
            issues=[dict(base,cell=f'A{i+2}') for i in reversed(range(count))]
            groups=group_findings(issues+issues)
            self.assertEqual(len(groups),int(count>0))
            if count:
                self.assertEqual(groups[0]['count'],count)
                self.assertEqual(len(groups[0]['cells']),count if count<10 else 0)
                if count<10:self.assertEqual(groups[0]['cells'][0],'A2')
        issues=[dict(base,cell='A2'),dict(base,cell='A2',rule='category'),dict(base,cell='A2',sheet='controls'),
                dict(base,cell='A2',source='second.xlsx'),dict(base,cell=None,scope='missing_column')]
        self.assertEqual(len(group_findings(issues)),4)
        self.assertEqual(summarize(issues)['affected_rows'],3)

    def test_excel_groups_privacy_and_source_preservation(self):
        fixture(self.source,[{'extraction_date':'PRIVATE_SENTINEL'}]*10)
        result=self.inspect();output=self.root/'report.xlsx'
        write_workbook(output,result,self.rules,digest(self.source));validate_workbook(output,result)
        wb=load_workbook(output)
        self.assertEqual(wb.sheetnames,['Summary','Issues','Coverage','Definitions'])
        self.assertTrue(wb['Summary']._charts)
        for row in wb['Issues'].iter_rows(min_row=5,values_only=True):
            if row[5]>=10:self.assertIsNone(row[6])
        text=' '.join(str(c.value) for ws in wb for row in ws for c in row)
        self.assertNotIn('PRIVATE_SENTINEL',text);self.assertNotIn('SYNTHETIC-1',text)
        wb.close()

    def test_standalone_quality_exit_publishes_and_refuses_overwrite(self):
        fixture(self.source,[{'dna_total_ng':999}]);before=digest(self.source)
        out=self.root/'run'
        argv=['--inventory',str(self.source),'--cohort','retrospective','--output-dir',str(out)]
        with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
            self.assertEqual(main(argv),1)
            self.assertEqual(main(argv),1)
        self.assertTrue((out/'retrospective/integrity_report.xlsx').is_file())
        record=json.loads((out/'.audit/run_manifest.json').read_text())
        self.assertEqual(record['status'],'complete');self.assertEqual(record['quality_status'],'errors_found')
        self.assertEqual(digest(self.source),before)

    def test_preflight_defers_defects_and_validates_configuration(self):
        args=arguments(['--inventory',str(self.source),'--cohort','retrospective'])
        record=preflight(args)
        self.assertEqual(record['source_states']['retrospective']['availability'],'unavailable')
        self.assertNotIn('retrospective',record['inputs'])
        invalid=deepcopy(self.rules);invalid['reference_display_limit']=9
        rulefile=self.root/'rules.json';rulefile.write_text(json.dumps(invalid))
        with self.assertRaises(ValueError):load_rules(rulefile)

    def test_independent_report_generation_failure(self):
        fixture(self.source,sheets=('Inventaire','cohorte_lal','cohorte_control'))
        args=arguments(['--inventory',str(self.source),'--circall',str(self.source),'--output-dir',str(self.root/'native')])
        from analysis.data_integrity import runner
        original=runner.write_workbook
        def fail_one(path,result,*rest):
            if result['cohort']=='retrospective':raise ValueError('PRIVATE_SENTINEL')
            return original(path,result,*rest)
        with patch.object(runner,'write_workbook',side_effect=fail_one):self.assertEqual(run(args),0)
        record=json.loads((args.output_dir/'run_manifest.json').read_text())
        self.assertEqual(record['report_generation_status'],'partial')
        self.assertEqual(record['cohorts'][1]['report_status'],'complete')
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(record))

    def test_master_matches_standalone_and_missing_cohort_does_not_block(self):
        from analysis.pipeline import main as integrated
        fixture(self.source,[{'dna_total_ng':999}],sheets=('Inventaire','cohorte_lal','cohorte_control'))
        direct=self.root/'direct';master=self.root/'master'
        config=self.root/'profile.json'
        entry={'schema_version':1,'workflows':[{'name':'data_integrity','options':{
            'inventory':str(self.source),'circall':str(self.source),'cohort':'all'}}]}
        config.write_text(json.dumps(entry))
        with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
            self.assertEqual(main(['--inventory',str(self.source),'--circall',str(self.source),'--output-dir',str(direct)]),1)
            self.assertEqual(integrated(['--config',str(config),'--validate-only']),0)
            self.assertEqual(integrated(['--config',str(config),'--output-dir',str(master)]),1)
        for cohort in ['retrospective','circall']:
            relative=Path('.audit/workflows/01_data_integrity')/cohort/'findings.json'
            self.assertEqual(json.loads((direct/relative).read_text()),json.loads((master/relative).read_text()))
            self.assertTrue((master/cohort/'integrity_report.xlsx').is_file())
        entry['workflows'][0]['options']['inventory']=str(self.root/'missing.xlsx')
        config.write_text(json.dumps(entry));missing=self.root/'missing_run'
        with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
            self.assertEqual(integrated(['--config',str(config),'--output-dir',str(missing)]),1)
        self.assertTrue((missing/'circall/integrity_report.xlsx').is_file())
        record=json.loads((missing/'.audit/workflows/01_data_integrity/run_manifest.json').read_text())
        self.assertEqual(record['report_generation_status'],'complete')
        self.assertEqual(record['source_states']['retrospective']['availability'],'unavailable')

    def test_review_only_returns_success_and_controls_are_optional(self):
        fixture(self.source,[{'extraction_date':'needs_review'}],sheets=('cohorte_lal',))
        with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
            code=main(['--circall',str(self.source),'--cohort','circall','--no-include-controls',
                       '--output-dir',str(self.root/'warnings')])
        self.assertEqual(code,0)
        record=json.loads((self.root/'warnings/.audit/run_manifest.json').read_text())
        self.assertEqual(record['quality_status'],'review_needed')

    def test_excel_error_range_references_and_header_privacy(self):
        cols=fixture(self.source)
        fixture(self.source,[{'dna_total_ng':'=SUM(A2:Z2)','unknown_extra':'PRIVATE_SENTINEL'}])
        result=self.inspect()
        self.assertTrue(any(i['rule']=='self_reference' for i in result['findings']))
        self.assertTrue(any(i['rule']=='identifier_reference' for i in result['findings']))
        wb=load_workbook(self.source);ws=wb.active
        ws.cell(1,len(cols),'PRIVATE_HEADER');ws[cols['dna_total_ng']+'2']='#DIV/0!'
        wb.save(self.source);wb.close()
        result=self.inspect()
        self.assertTrue(any(i['rule']=='excel_error' for i in result['findings']))
        self.assertNotIn('PRIVATE_HEADER',json.dumps(result))

    def test_source_mutation_blocks_acceptance(self):
        fixture(self.source)
        args=arguments(['--inventory',str(self.source),'--cohort','retrospective'])
        evidence=preflight(args)
        self.source.write_bytes(b'changed source')
        from analysis.data_integrity.runner import verify_source_states
        with self.assertRaises(ValueError):verify_source_states(evidence['source_states'])

    def test_explicit_unknown_and_not_extracted_conflicts(self):
        blank={h:None for h in self.rules['extraction_dependent_fields']}
        fixture(self.source,[{**blank,'elution_volume_ul':'?','extraction_date':'?','cfdna_avg_size_bp':'?'},
                             {**blank,'extraction_status':'not_extracted','extraction_input_volume_ml':2,'elution_volume_ul':50}])
        result=self.inspect()
        self.assertFalse(any(i['rule'] in ['date_text','number_text','missing_result'] for i in result['findings']))
        conflicts=[i for i in result['findings'] if i['rule']=='extraction_state_conflict']
        self.assertEqual(len(conflicts),1)
        self.assertEqual(conflicts[0]['field'],'elution_volume_ul')
        self.assertEqual(conflicts[0]['severity'],'error')
        self.assertEqual(conflicts[0]['category'],'Logic')
        self.assertTrue(any(c['reason']=='explicit_unknown' and c['unavailable']==1 for c in result['coverage']))
        self.assertEqual(sum(c['unavailable'] for c in result['coverage'] if c['reason']=='not_applicable_not_extracted' and c['check']=='arithmetic'),5)

    def test_context_does_not_suppress_future_visit_formula_errors(self):
        cols=fixture(self.source,sheets=('cohorte_lal',))
        fixture(self.source,[{'sample_id':None,'dna_concentration_ng_per_ul':None,
                              'dna_total_ng':'=1*0'}],sheets=('cohorte_lal',),
                caches={cols['dna_total_ng']+'2':('n',0)})
        result=self.inspect(cohort='circall',controls=False)
        group=next(g for g in result['groups'] if g['rule']=='false_zero')
        self.assertEqual(group['severity'],'error')
        self.assertEqual(group['category'],'Formula')
        self.assertEqual(group['context_counts'],{'Blank sample ID; future visit under the cohort convention':1})
        self.assertGreater(result['summary']['error_cells'],0)

    def test_annotations_are_described_by_meaning(self):
        fixture(self.source,[{'extraction_date':'pas saisie dans hémal','elution_volume_ul':'à faire'},
                             {'extraction_input_volume_ml':'300µl'},
                             {'extraction_input_volume_ml':'2 aliquots'}])
        result=self.inspect()
        rules=[i['rule'] for i in result['findings']]
        self.assertEqual(rules.count('workflow_annotation'),2)
        self.assertEqual(rules.count('unit_annotation'),1)
        self.assertEqual(rules.count('aliquot_annotation'),1)
        self.assertNotIn('date_text',rules)
        self.assertNotIn('number_text',rules)

    def test_occurrences_and_unique_cells_rows_are_distinct(self):
        base={'source':'synthetic.xlsx','sheet':'Inventaire','field':'dna_total_ng',
              'rule':'excel_error','severity':'error','issue':'Excel error','action':'Review','cell':'F2','scope':None}
        findings=[base,dict(base,rule='self_reference'),dict(base,cell='F3'),dict(base,severity='review',rule='cross_row_reference')]
        summary=summarize(findings)
        self.assertEqual(summary['errors'],3)
        self.assertEqual(summary['reviews'],1)
        self.assertEqual(summary['error_cells'],2)
        self.assertEqual(summary['review_cells'],1)
        self.assertEqual(summary['affected_cells'],2)
        self.assertEqual(summary['error_rows'],2)

    def test_layer1_default_root_and_explicit_destination_precedence(self):
        from analysis.data_integrity.runner import default_output_dir
        from analysis import pipeline
        root=ROOT/'outputs/layer1_data_integrity'
        self.assertEqual(default_output_dir().parent,root)
        config=self.root/'profile.json'
        profile={'schema_version':1,'workflows':[{'name':'data_integrity','options':{
            'inventory':str(self.source),'cohort':'retrospective'}}]}
        config.write_text(json.dumps(profile))
        with patch.object(pipeline,'preflight',return_value={}) as check,redirect_stdout(StringIO()):
            self.assertEqual(pipeline.main(['--config',str(config),'--validate-only']),0)
            self.assertEqual(check.call_args.args[1].parent,root)
            profile['output-dir']='configured'
            config.write_text(json.dumps(profile))
            self.assertEqual(pipeline.main(['--config',str(config),'--validate-only']),0)
            self.assertEqual(check.call_args.args[1],self.root/'configured')
            self.assertEqual(pipeline.main(['--config',str(config),'--validate-only','--output-dir',str(self.root/'override')]),0)
            self.assertEqual(check.call_args.args[1],self.root/'override')


if __name__=='__main__':unittest.main()

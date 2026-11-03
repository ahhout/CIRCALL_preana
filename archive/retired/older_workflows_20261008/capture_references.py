"""Capture the October 8 retirement cases in a fresh evidence directory."""
import argparse
import json, os, pathlib, subprocess, sys
root=pathlib.Path.cwd(); sys.path.insert(0,str(root))
from analysis.pipeline import load_config
from analysis.provenance import digest
from tests.fixtures.advanced_analysis import sources as assoc_sources
from tests.disease_modeling.fixtures import sources as disease_sources, inventory
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--phase',choices=['baseline','candidate','verified'],required=True)
parser.add_argument('--evidence-root',type=pathlib.Path,required=True)
args=parser.parse_args()
base=args.evidence_root.resolve()
phase=args.phase
if phase=='baseline':
    base.mkdir(exist_ok=False)
    cases={}
    for blocked in (False,True):
        name='synthetic_blocked' if blocked else 'synthetic_success'
        src=base/'sources'/name
        (src/'associations').mkdir(parents=True); (src/'disease').mkdir()
        retro,circ,donors=assoc_sources(src/'associations')
        common=dict(inventory=str(retro),circall=str(circ),donors=str(donors),cohort='all')
        disease={k.replace('_','-'):str(p) for k,p in disease_sources(src/'disease').items()}
        if blocked: inventory(pathlib.Path(disease['circall']),'circall',[dict(circall_id='001-9001-X-Z',MRD_TP1='PRIVATE_BAD_CLINICAL_NOTE')])
        disease.update({'blood-count-unit':'x10^9/L','retrospective-blast-unit':'x10^9/L','jitter-seed':42,'pdf-output':True})
        cases[name]=dict(schema_version=1,workflows=[dict(name='data_integrity',options=common),dict(name='sample_statistics',options={**common,'assessment-time':'2026-10-08T12:00:00+00:00','pdf-output':True}),dict(name='advanced_analysis',options={**common,'retrospective-wbc-unit':'x10^9/L','sample-selection-seed':123,'pdf-output':True}),dict(name='disease_modeling',options=disease)])
    cases['clinical_current']=load_config(root/'configs/pipeline_layers.json')
    cases['clinical_current']['workflows'][1]['options']['assessment-time']='2026-10-08T12:00:00+00:00'
    (base/'profiles').mkdir()
    for name,config in cases.items(): (base/'profiles'/f'{name}.json').write_text(json.dumps(config,indent=2)+'\n')
results={}
for name in ('synthetic_success','synthetic_blocked','clinical_current'):
    target=base/phase/name
    target.parent.mkdir(parents=True,exist_ok=True)
    profile=base/'profiles'/f'{name}.json'
    args=['conda','run','--no-capture-output','-n','pre_analysis','python','-B','run.py','--config',str(profile),'--output-dir',str(target)]
    result={}
    for mode,command in [('preflight',args+['--validate-only']),('execution',args)]:
        log=base/phase/f'{name}_{mode}.log'
        with log.open('x') as stream: proc=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,check=False)
        result[mode]=dict(returncode=proc.returncode,log=str(log.relative_to(root)),command=command)
        print(phase,name,mode,proc.returncode,flush=True)
    manifest=json.loads((target/'.audit/run_manifest.json').read_text())
    expected=0 if name=='synthetic_success' else 1
    assert result['preflight']['returncode']==expected and result['execution']['returncode']==expected
    assert all(w['status']=='complete' for w in manifest['workflows'])
    if name!='synthetic_success':
        cohorts=manifest['workflows'][3]['provenance']['cohorts']
        assert next(c for c in cohorts if c['cohort']=='circall')['disease_status']=='blocked'
        assert next(c for c in cohorts if c['cohort']=='retrospective')['disease_status']=='complete'
    result['status']=manifest['status']; result['workflow_quality']={w['name']:w['quality_status'] for w in manifest['workflows']}
    results[name]=result
(base/phase/'capture.json').write_text(json.dumps(results,indent=2)+'\n')

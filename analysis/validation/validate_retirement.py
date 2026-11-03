"""Compare explicitly selected four-layer runs across implementation retirement."""
import argparse
import csv
import io
import json
from pathlib import Path
import re

import numpy as np
from openpyxl import load_workbook
from PIL import Image

from analysis.provenance import ROOT, digest, verify_inputs, write_json
from analysis.outputs import DIRECTORIES
from analysis.validation.validate_advanced_analysis import identifying_values, strings
from analysis.validation.validate_disease_modeling import private_values


# Execution metadata only; numerical evidence and resolved scientific settings stay exact.
VOLATILE = {'started_utc', 'finished_utc', 'command', 'code_sha256', 'code_revision',
            'code_dirty', 'run_id', 'artifacts', 'publications', 'resolved_settings_sha256'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized(value, run):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in VOLATILE:
                continue
            if key == 'scientific_contract':
                result[key] = {k: v for k, v in item.items() if k != 'sha256'}
            else:
                result[key] = normalized(item, run)
        return result
    if isinstance(value, list):
        return [normalized(v, run) for v in value]
    if isinstance(value, str):
        return value.replace(str(run), '<RUN>')
    return value


def workbook_contents(path, run):
    book = load_workbook(path, read_only=False, data_only=False)
    try:
        return [(sheet.title, sheet.freeze_panes, sheet.auto_filter.ref,
                 sorted(str(r) for r in sheet.merged_cells.ranges),
                 [[(normalized(c.value, run), c.data_type, c.number_format, c.style_id)
                   for c in row] for row in sheet]) for sheet in book]
    finally:
        book.close()


def verify_run(run, code_root):
    record = json.loads((run/'.audit/run_manifest.json').read_text())
    require(record['pipeline_kind'] == 'layered', 'Invalid retirement acceptance evidence')
    require([w['name'] for w in record['workflows']] == list(DIRECTORIES), 'Invalid retirement acceptance evidence')
    require(all(w['status'] == 'complete' for w in record['workflows']), 'Invalid retirement acceptance evidence')
    require(record['started_utc'] and record['finished_utc'], 'Invalid retirement acceptance evidence')
    counts = dict(indexed=0, publications=0, privacy_exports=0, code_hashes=0)
    index = json.loads((run/'.audit/artifact_index.json').read_text())
    for item in index['artifacts']:
        require(digest(run/item['path']) == item['sha256'], 'Artifact hash mismatch')
        counts['indexed'] += 1
    for item in index['publications']:
        require(digest(run/item['path']) == digest(run/item['source']) == item['sha256'], 'Publication mismatch')
        require(Path(item['path']).parts[0] in DIRECTORIES.values(), 'Unexpected publication location')
        counts['publications'] += 1
    require(record['publications'] == index['publications'], 'Invalid retirement acceptance evidence')
    for r in [record, *[w['provenance'] for w in record['workflows']]]:
        verify_inputs(r['inputs'])
        for path, expected in r['code_sha256'].items():
            require(digest(code_root/path) == expected, 'Executed code hash mismatch')
            counts['code_hashes'] += 1
        require(digest(code_root/r['scientific_contract']['path']) == r['scientific_contract']['sha256'], 'Invalid retirement acceptance evidence')
        if r.get('environment_lock_sha256'):
            require(digest(code_root/'environments/conda-linux-64.lock') == r['environment_lock_sha256'], 'Invalid retirement acceptance evidence')
    # The native completion validator already checks populations and statistics for all layers.
    # Check the stricter aggregate-only export policy for Layers 3 and 4 across all evidence.
    for name, forbidden_fn in [('advanced_analysis', identifying_values), ('disease_modeling', private_values)]:
        native=run/'.audit/workflows'/DIRECTORIES[name]
        state=next(w for w in record['workflows'] if w['name']==name)
        forbidden=forbidden_fn(state['provenance'])
        for path in native.rglob('*'):
            if not path.is_file():
                continue
            values=[]
            if path.suffix=='.xlsx':
                b=load_workbook(path,read_only=True,data_only=False)
                try: values=[v for sheet in b for row in sheet.values for v in row if isinstance(v,str)]
                finally: b.close()
            elif path.suffix=='.json': values=list(strings(json.loads(path.read_text())))
            elif path.suffix=='.csv':
                require(name!='disease_modeling', 'Unexpected disease CSV export')
                values=[v for row in csv.reader(io.StringIO(path.read_text())) for v in row]
            else: continue
            require(not any(v.strip() in forbidden for v in values), 'Identifier in aggregate export')
            counts['privacy_exports']+=1
        for path in (run/'.audit/logs').glob('*.log'):
            require(not any(v in path.read_text() for v in forbidden), 'Identifier in worker log')
    return record, counts


def compare(baseline, candidate, snapshot):
    baseline, candidate, snapshot=map(Path,(baseline,candidate,snapshot))
    a, ca=verify_run(baseline,snapshot)
    b, cb=verify_run(candidate,ROOT)
    require(normalized(a,baseline)==normalized(b,candidate), 'Completion/settings/populations differ')
    publications = lambda r: {(p['workflow'], p['path'], p['source']) for p in r['publications']}
    require(publications(a) == publications(b), 'Published artifact selection differs')
    checks=dict(json=0,csv=0,workbooks=0,png=0,pdf=0)
    def files(root):
        return {str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()
                and '.cache' not in p.parts and 'publication' not in p.parts
                and p.suffix in ('.json','.csv','.xlsx','.png','.pdf')
                and p.name!='artifact_index.json'}
    left,right=files(baseline),files(candidate)
    require(left.keys()==right.keys(), 'Artifact population differs')
    failures=[]
    for name,p in sorted(left.items()):
        q=right[name]
        if p.suffix=='.json':
            okay=normalized(json.loads(p.read_text()),baseline)==normalized(json.loads(q.read_text()),candidate)
            checks['json']+=1
        elif p.suffix=='.xlsx':
            okay=workbook_contents(p,baseline)==workbook_contents(q,candidate)
            checks['workbooks']+=1
        elif p.suffix=='.png':
            with Image.open(p) as x,Image.open(q) as y:
                okay=np.array_equal(np.asarray(x),np.asarray(y))
            checks['png']+=1
        elif p.suffix=='.pdf':
            # Matplotlib PDF bytes are deterministic apart from the creation date.
            def content(path): return re.sub(rb'/CreationDate \(D:[^)]*\)',b'/CreationDate (<TIME>)',path.read_bytes())
            okay=content(p)==content(q)
            checks['pdf']+=1
        else:
            okay=p.read_bytes()==q.read_bytes()
            checks['csv']+=1
        if not okay: failures.append(name)
    return dict(status='passed' if not failures else 'failed',baseline=str(baseline),candidate=str(candidate),
                baseline_integrity=ca,candidate_integrity=cb,compared=checks,failures=failures,
                exclusions=sorted(VOLATILE|{'scientific_contract.sha256','PDF CreationDate','Excel ZIP/core timestamps'}),
                limitations=['Workbook cells, formats and sheet structure compared; Excel visual rendering not available.',
                             'PNG pixels and PDF content compared; independent PDF rasterization not available.'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--snapshot',type=Path,required=True,help='Pre-retirement implementation directory')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.report.exists(): parser.error('Choose a fresh report destination')
    result=compare(args.baseline,args.candidate,args.snapshot)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    write_json(args.report,result)
    print(json.dumps(dict(status=result['status'],compared=result['compared'],failure_count=len(result['failures']))))
    return int(result['status']!='passed')


if __name__=='__main__':
    raise SystemExit(main())

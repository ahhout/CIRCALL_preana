"""Compare two explicitly selected full runs, including completed quality holds."""
import argparse
import json
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile

from PIL import Image

from analysis.layer_configuration import LAYERS
from analysis.outputs import DIRECTORIES, deliverables
from analysis.provenance import ROOT, digest, verify_inputs, settings_digest
from analysis.validation.artifact_checks import checked_index


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def workbook_equal(left, right):
    """Compare decompressed workbook parts, including styles, charts and hidden rows."""
    with ZipFile(left) as a, ZipFile(right) as b:
        if sorted(a.namelist()) != sorted(b.namelist()):
            return False
        for name in a.namelist():
            x, y = a.read(name), b.read(name)
            if x == y:
                continue
            if name != 'docProps/core.xml':
                return False
            roots = [ElementTree.fromstring(data) for data in (x, y)]
            for root in roots:
                for field in ('created', 'modified'):
                    node = root.find('{http://purl.org/dc/terms/}'+field)
                    if node is not None:
                        node.text = ''
            if ElementTree.tostring(roots[0]) != ElementTree.tostring(roots[1]):
                return False
        return True


def same_artifact(left, right):
    if digest(left) == digest(right):
        return True
    if left.suffix == '.xlsx':
        return workbook_equal(left, right)
    if left.suffix == '.png':
        with Image.open(left) as a, Image.open(right) as b:
            return a.size == b.size and a.convert('RGBA').tobytes() == b.convert('RGBA').tobytes()
    if left.suffix == '.pdf':
        pattern = rb'/(CreationDate|ModDate) \(D:\d{14}[^)]*\)'
        return re.sub(pattern, rb'/\1', left.read_bytes()) == re.sub(pattern, rb'/\1', right.read_bytes())
    if left.suffix == '.json':
        return json.loads(left.read_bytes()) == json.loads(right.read_bytes())
    return False


def check_provenance(record, code):
    verify_inputs(record['inputs'])
    for rel, expected in record['code_sha256'].items():
        require((code/rel).resolve().is_relative_to(code), 'Invalid code path')
        require(digest(code/rel) == expected, 'Code hash differs')
    contract = record['scientific_contract']
    require(digest(code/contract['path']) == contract['sha256'], 'Contract hash differs')
    if record['environment_lock_sha256']:
        require(digest(code/'environments/conda-linux-64.lock') == record['environment_lock_sha256'],
                'Environment lock differs')
    require(settings_digest(record['resolved_settings']) == record['resolved_settings_sha256'],
            'Resolved settings hash differs')


def inspect(root, code):
    index = checked_index(root)
    files = {a['path']: a['sha256'] for a in index['artifacts']}
    manifest = json.loads((root/'.audit/run_manifest.json').read_bytes())
    require(manifest['pipeline_kind'] == 'layered' and manifest['output_layout_version'] == 2
            and tuple(w['name'] for w in manifest['workflows']) == LAYERS, 'Incomplete layer selection')
    check_provenance(manifest, code)
    states, evidence, publications = [], set(), []
    for worker in manifest['workflows']:
        name = worker['name']
        folder = Path('.audit/workflows')/DIRECTORIES[name]
        record = json.loads((root/folder/'run_manifest.json').read_bytes())
        require(worker['status'] == record['status'] == 'complete' and worker['returncode'] == 0
                and worker['provenance'] == record and record['workflow'] == name
                and worker['report_generation_status'] == record['report_generation_status'] == 'complete'
                and worker['quality_status'] == record['quality_status'], 'Incomplete workflow')
        require(all(c.get(key) != 'execution_failed' for c in record['cohorts']
                    for key in ('statistics_status','association_status','disease_status')), 'Worker execution failed')
        check_provenance(record, code)
        preflight = worker['preflight']
        check_provenance(preflight, code)
        states.append(({key: record.get(key) for key in (
            'quality_status','cohorts','analysis_status','inputs','source_states','resolved_settings',
            'packages','environment_lock_sha256','scientific_contract','preparation_preview',
            'cohort_preflight','validation_quality')}, preflight.get('validation_quality')))
        artifacts = {a['path']: a['sha256'] for a in record['artifacts']}
        require(len(artifacts) == len(record['artifacts']), 'Duplicate native artifact')
        for rel, expected in artifacts.items():
            path = str(folder/rel)
            require(files.get(path) == expected, 'Native artifact hash differs')
            evidence.add(path)
        for old, new in deliverables(name, root/folder, record).items():
            source, path = str(folder/old), str(Path(DIRECTORIES[name])/new)
            require(old in artifacts and files.get(path) == artifacts[old], 'Publication hash differs')
            publications.append(dict(source=source, path=path, workflow=name, sha256=artifacts[old]))
    require(publications == manifest['publications'], 'Publication mapping differs')
    held = any(w['quality_status'] == 'errors_found' for w in manifest['workflows'])
    require(manifest['status'] == ('failed' if held else 'complete') and not manifest.get('error'),
            'Unexpected root completion state')
    return states, evidence, set(files), [(p['source'], p['path']) for p in publications]


def compare(baseline, candidate, baseline_code, candidate_code):
    left = inspect(baseline, baseline_code)
    right = inspect(candidate, candidate_code)
    require(left == right, 'Scope, settings, inputs or inventory differs')
    for rel in sorted(left[1]):
        require(same_artifact(baseline/rel, candidate/rel), 'Native artifact content differs')
    return dict(status='passed', native_artifacts=len(left[1]), indexed=len(left[2]), published=len(left[3]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('baseline','candidate','report'):
        parser.add_argument('--'+name, required=True, type=Path)
    for name in ('baseline','candidate'):
        parser.add_argument('--'+name+'-code-root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    roots = [args.baseline.resolve(), args.candidate.resolve()]
    report = args.report.absolute()
    if (report.exists() or any(p.is_symlink() for p in (report,*report.parents))
            or any(report.resolve().is_relative_to(root) for root in roots)):
        parser.error('Select a fresh report outside both runs')
    try:
        result = compare(*roots, args.baseline_code_root.resolve(), args.candidate_code_root.resolve())
    except Exception as error:
        result = dict(status='failed', error_code=type(error).__name__)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['status'])
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())

"""Container contexts select exact source bytes and preserve pipeline controls."""
import hashlib
import json
from pathlib import Path
import runpy

from openpyxl import Workbook
import pytest

from analysis.provenance import ROOT

BUILDER = runpy.run_path(str(ROOT/'environments/container/build.py'))


def selected_master(tmp_path):
    profile = json.loads((ROOT/'configs/pipeline_layers.json').read_text())
    sources = {}
    for role in BUILDER['ROLES']:
        source = tmp_path/f'synthetic_{role}.xlsx'
        book = Workbook()
        book.active.append(['synthetic_marker'])
        book.active.append([role])
        book.save(source)
        book.close()
        profile['sources'][role] = str(source)
        sources[role] = source
    for options in [profile['defaults'], *[v['options'] for v in profile['layers'].values()]]:
        for key in ('rules', 'definitions'):
            if key in options:
                options[key] = str(ROOT/'configs'/options[key])
    config = tmp_path/'synthetic_master.json'
    config.write_text(json.dumps(profile))
    fonts = tmp_path/'synthetic_fonts'
    fonts.mkdir()
    for name in BUILDER['FONTS']:
        (fonts/name).write_bytes(b'SYNTHETIC FONT CONTEXT FIXTURE')
    return config, fonts, profile, sources


def test_context_contains_only_selected_workbooks_and_preserves_controls(tmp_path):
    config, fonts, original, sources = selected_master(tmp_path)
    unrelated = tmp_path/'unselected.xlsx'
    unrelated.write_bytes(b'UNSELECTED SYNTHETIC SENTINEL')
    context = tmp_path/'context'
    record = BUILDER['prepare'](config, fonts, context)
    bundled = json.loads((context/'dataset/configs/container_master.json').read_text())
    assert bundled['layers'] == {
        name: {**layer, 'options': {key: str(Path(value).relative_to(ROOT/'configs'))
                                   if key in ('rules', 'definitions') else value
                                   for key, value in layer['options'].items()}}
        for name, layer in original['layers'].items()}
    assert set((context/'dataset/input').iterdir()) == {
        context/'dataset/input'/f'{role}.xlsx' for role in sources}
    for role, source in sources.items():
        assert (context/'dataset/input'/f'{role}.xlsx').read_bytes() == source.read_bytes()
        assert record['source_sha256'][role] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert bundled['sources'][role] == f'../input/{role}.xlsx'
    assert {p.name for p in (context/'arial').iterdir()} == set(BUILDER['FONTS'])
    assert not (context/'.git').exists()
    assert not (context/'input').exists()
    assert not (context/'.maintenance').exists()
    assert not (context/'.aws').exists()
    assert not (context/'.codex').exists()
    assert record['environment_lock_sha256'] == hashlib.sha256((ROOT/'environments/conda-linux-64.lock').read_bytes()).hexdigest()
    assert record['platform'] == 'linux/amd64'


def test_context_requires_full_master_and_four_font_styles(tmp_path):
    config, fonts, profile, _ = selected_master(tmp_path)
    (fonts/'Arial_Bold.ttf').unlink()
    with pytest.raises(ValueError, match='Arial requires'):
        BUILDER['prepare'](config, fonts, tmp_path/'missing_fonts')
    assert not (tmp_path/'missing_fonts').exists()
    profile['layers']['advanced_analysis']['enabled'] = False
    config.write_text(json.dumps(profile))
    with pytest.raises(ValueError, match='Every layer'):
        BUILDER['prepare'](config, fonts, tmp_path/'partial')
    assert not (tmp_path/'partial').exists()


def test_existing_context_is_preserved(tmp_path):
    config, fonts, _, _ = selected_master(tmp_path)
    context = tmp_path/'existing'
    context.mkdir()
    marker = context/'keep.txt'
    marker.write_text('preserve')
    with pytest.raises(ValueError, match='fresh context'):
        BUILDER['prepare'](config, fonts, context)
    assert marker.read_text() == 'preserve'
    assert list(context.iterdir()) == [marker]


def test_existing_image_is_preserved_before_context_creation(tmp_path, monkeypatch):
    config, fonts, _, _ = selected_master(tmp_path)
    image = tmp_path/'existing.sif'
    image.write_bytes(b'KEEP EXISTING IMAGE')
    context = tmp_path/'must_not_exist'
    monkeypatch.setattr(BUILDER['main'].__globals__['shutil'], 'which', lambda _: '/usr/bin/apptainer')
    assert BUILDER['main'](['--config', str(config), '--arial-dir', str(fonts),
                            '--context', str(context), '--image', str(image)]) == 1
    assert image.read_bytes() == b'KEEP EXISTING IMAGE'
    assert not context.exists()

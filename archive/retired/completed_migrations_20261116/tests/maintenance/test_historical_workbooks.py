"""Historical workbook packaging stays independent of retired scientific packages."""
from pathlib import Path
import pytest

from archive.retired.completed_migrations_20261116.analysis.historical_workbooks import build, engine_directory


def test_rebuild_reads_old_and_new_layouts_without_overwriting(tmp_path):
    root=tmp_path/'run'
    source=root/'.audit/workflows/sample_analysis'
    source.mkdir(parents=True)
    (source/'analysis_status.csv').write_text('analysis,cohort,status,reason\ninventory,circall,complete,\n')
    (source/'inventory').mkdir()
    (source/'inventory/availability.csv').write_text('cohort,count\ncircall,2\n')
    for i,requested in enumerate((root,root/'sample_analysis',source)):
        destination=tmp_path/f'report_{i}'
        paths=build(requested,destination)
        assert len(paths)==3 and all(p.is_file() for p in paths)
        with pytest.raises(FileExistsError): build(requested,destination)
    historical=tmp_path/'historical'
    historical.mkdir()
    (historical/'analysis_status.csv').write_text('analysis,cohort,status,reason\ninventory,circall,complete,\n')
    assert engine_directory(historical)==historical
    assert all(p.is_file() for p in build(historical))

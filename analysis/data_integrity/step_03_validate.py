"""Independently reconcile completed native results."""
import json
from pathlib import Path
from analysis.utils.source_state import verify_source_states
from analysis.provenance import digest
from analysis.data_integrity.step_01_inspect import group_findings, summarize
from analysis.data_integrity.step_02_report import validate_workbook


def validate_results(output,record):
    output=Path(output)
    for item in record['artifacts']:
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or digest(output/path)!=item['sha256']:
            raise ValueError('Integrity report artifact mismatch')
    for cohort in record['cohorts']:
        if cohort['report_status']!='complete':continue
        result=json.loads((output/cohort['cohort']/'findings.json').read_text())
        if result['groups']!=group_findings(result['findings']) or result['summary']!=summarize(result['findings']):
            raise ValueError('Integrity audit groups do not reconcile')
        validate_workbook(output/cohort['cohort']/'integrity_report.xlsx',result)
    verify_source_states(record['source_states'])

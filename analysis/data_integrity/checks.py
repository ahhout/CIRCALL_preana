"""Configured integrity rules; findings contain locations, never source values."""
from collections import Counter, defaultdict
from datetime import date, datetime
import json
import math
from pathlib import Path
import re

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from analysis.sample_io import read_sheet, SourceReadError
from analysis.sample_definitions import extraction_state

RULE_IDS = frozenset('file_unavailable file_unreadable sheet_missing header_missing header_duplicate unheaded_data whitespace category number_text numeric_text number_invalid date_text excel_error broken_reference self_reference identifier_reference cross_row_reference formula_unassessed cache_missing arithmetic denominator missing_operands false_zero missing_result extraction_state_conflict workflow_annotation aliquot_annotation unit_annotation'.split())


def load_rules(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate rules key')
            result[key] = value
        return result
    try:
        rules = json.loads(Path(path).read_text(), object_pairs_hook=unique)
        if rules['schema_version'] != 1 or set(rules['rules']) != RULE_IDS:
            raise ValueError()
        if rules['extraction_basis'] != 'dna_id':
            raise ValueError()
        if set(rules['rule_categories'])!=RULE_IDS or any(v not in ('Structure','Formatting','Interpretation','Formula','Logic') for v in rules['rule_categories'].values()):
            raise ValueError()
        if rules['reference_display_limit'] != 10:
            raise ValueError()
        for tolerance in ('rtol', 'atol'):
            if type(rules[tolerance]) not in (int, float) or not math.isfinite(rules[tolerance]) or rules[tolerance] < 0:
                raise ValueError()
        for rule in rules['rules'].values():
            if len(rule) != 3 or rule[0] not in ('error', 'review') or not all(isinstance(v,str) and v for v in rule):
                raise ValueError()
        for field in rules['fields'].values():
            if field['type'] not in ('number', 'text', 'category', 'date'):
                raise ValueError()
            if not all(isinstance(field.get(k),str) for k in ('unit','description')):
                raise ValueError()
            if field['type']=='category' and (not isinstance(field.get('allowed'),list) or not all(isinstance(v,str) for v in field['allowed'])):
                raise ValueError()
            for bound in ('minimum', 'maximum'):
                if bound in field and (type(field[bound]) not in (int,float) or not math.isfinite(field[bound])):
                    raise ValueError()
        for calc in rules['calculations']:
            if calc['operation'] not in ('multiply','divide') or len(calc['operands']) != 2:
                raise ValueError()
            if any(h not in rules['fields'] for h in [calc['output'],*calc['operands']]):
                raise ValueError()
        for key in ('required','patient_required','identifier_fields','missing_tokens','unknown_tokens','extraction_dependent_fields','workflow_annotations'):
            if not isinstance(rules[key],list) or any(not isinstance(x,str) for x in rules[key]):
                raise ValueError()
        if len(set(rules['required']))!=len(rules['required']) or set(rules['fields']) & set(rules['identifier_fields']):
            raise ValueError()
        if set(rules['missing_tokens']) & set(rules['unknown_tokens']) or set(rules['extraction_dependent_fields']) & set(rules['identifier_fields']):
            raise ValueError()
        return rules
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Invalid integrity rules configuration') from None


def number(value, missing, unknown=()):
    if value is not None and str(value).strip().casefold() in unknown:
        return None, 'unknown'
    if value is None or str(value).strip().casefold() in missing:
        return None, 'missing'
    if isinstance(value, bool) or isinstance(value, (date, datetime)):
        return None, 'invalid'
    try:
        result = float(str(value).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return None, 'annotation'
    if not math.isfinite(result):
        return None, 'invalid'
    return result, 'text' if isinstance(value,str) else 'number'


def group_findings(findings, limit=10):
    groups = defaultdict(dict)
    for item in findings:
        key = tuple(item[k] for k in ('source','sheet','field','rule','severity'))
        occurrence = item.get('cell') or item.get('scope', 'structure')
        groups[key][occurrence] = item
    result = []
    for key, occurrences in groups.items():
        sample = next(iter(occurrences.values()))
        cells = sorted({i['cell'] for i in occurrences.values() if i.get('cell')}, key=coordinate_to_tuple)
        contexts = Counter(context for item in occurrences.values() for context in set(item.get('contexts',[])))
        result.append(dict(zip(('source','sheet','field','rule','severity'),key),
                           issue=sample['issue'], action=sample['action'], count=len(occurrences),
                           cells=cells if len(occurrences) < limit else [],
                           category=sample.get('category','Unclassified'),context_counts=dict(sorted(contexts.items()))))
    return sorted(result, key=lambda g:(g['severity']!='error',-g['count'],g['source'],g['sheet'],g['field'],g['rule']))


def summarize(findings):
    groups = group_findings(findings)
    affected = {(i['source'],i['sheet'],coordinate_to_tuple(i['cell'])[0])
                for i in findings if i.get('cell') and coordinate_to_tuple(i['cell'])[0] > 1}
    errors = sum(g['count'] for g in groups if g['severity']=='error')
    reviews = sum(g['count'] for g in groups if g['severity']=='review')
    def cells(severity=None):
        return {(i['source'],i['sheet'],i['cell']) for i in findings if i.get('cell') and (severity is None or i['severity']==severity)}
    def rows(severity):
        return {(source,sheet,coordinate_to_tuple(cell)[0]) for source,sheet,cell in cells(severity) if coordinate_to_tuple(cell)[0]>1}
    return {'errors':errors,'reviews':reviews,'affected_rows':len(affected),
            'affected_cells':len(cells()),'error_cells':len(cells('error')),'review_cells':len(cells('review')),
            'error_rows':len(rows('error')),'review_rows':len(rows('review')),
            'quality_status':'errors_found' if errors else 'review_needed' if reviews else 'no_issues_detected'}


def formula_findings(cell, sheet_name, headers, identifiers):
    formula = cell.formula
    found = set()
    if '#REF!' in formula.upper():
        found.add('broken_reference')
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return found | {'formula_unassessed'}
    if any(t.type=='FUNC' and t.value.upper().startswith(('INDIRECT(', 'OFFSET(')) for t in tokens):
        found.add('formula_unassessed')
    for token in tokens:
        if token.type!='OPERAND' or token.subtype!='RANGE':
            continue
        ref = token.value
        if '!' in ref:
            owner, ref = ref.rsplit('!',1)
            if owner.strip("'").replace("''", "'") != sheet_name:
                found.add('cross_row_reference')
                continue
        ref = ref.replace('$','')
        if not re.fullmatch(r'[A-Za-z]+[1-9][0-9]*(?::[A-Za-z]+[1-9][0-9]*)?',ref):
            found.add('formula_unassessed')
            continue
        try:
            c1,r1,c2,r2 = range_boundaries(ref.upper())
        except ValueError:
            found.add('formula_unassessed')
            continue
        if c1 <= cell.column <= c2 and r1 <= cell.row <= r2:
            found.add('self_reference')
        if r1 != cell.row or r2 != cell.row:
            found.add('cross_row_reference')
        if any(headers.get(col) in identifiers for col in range(c1,min(c2,len(headers))+1)):
            found.add('identifier_reference')
    return found


def inspect_cohort(path, cohort, include_controls, rules, sheets_override=None):
    source = str(Path(path).resolve())
    sheets = ['Inventaire'] if cohort=='retrospective' else ['cohorte_lal']+(['cohorte_control'] if include_controls else [])
    if sheets_override is not None:sheets=sheets_override
    findings, coverage, sheet_counts = [], [], []
    missing = {v.casefold() for v in rules['missing_tokens']}
    unknown = {v.casefold() for v in rules['unknown_tokens']}
    identifiers = set(rules['identifier_fields'])
    known = set(rules['fields']) | identifiers
    row_contexts = {}
    def emit(sheet,field,rule,cell=None,scope=None):
        severity,issue,action = rules['rules'][rule]
        findings.append({'source':source,'sheet':sheet,'field':field,'rule':rule,
                         'severity':severity,'issue':issue,'action':action,'cell':cell,'scope':scope})
        findings[-1].update(category=rules['rule_categories'][rule],
                            contexts=row_contexts.get((sheet,coordinate_to_tuple(cell)[0]),[]) if cell else [])
    def cover(sheet,field,check,assessed=0,unavailable=0,reason=''):
        coverage.append({'sheet':sheet,'field':field,'check':check,'assessed':assessed,
                         'unavailable':unavailable,'reason':reason})
    for sheet_name in sheets:
        try:
            sheet = read_sheet(path,sheet_name)
        except SourceReadError as error:
            emit(sheet_name,'(source)',error.code,scope=sheet_name)
            sheet_counts.append({'sheet':sheet_name,'rows':0,'status':'unavailable'})
            cover(sheet_name,'(all)','all_checks',reason=error.code,unavailable=1)
            continue
        sheet_counts.append({'sheet':sheet_name,'rows':len(sheet.rows),'status':'inspected'})
        headers = {c.column:str(c.raw).strip() if c.raw is not None else '' for c in sheet.headers}
        counts = Counter(h for h in headers.values() if h)
        index = {h:col for col,h in headers.items() if h and counts[h]==1}
        def not_extracted(row):
            col=index.get(rules['extraction_basis'])
            return extraction_state(row[col-1] if col is not None else None, missing, unknown)=='no'
        dna_col=index.get(rules['extraction_basis'])
        states=Counter(extraction_state(row[dna_col-1] if dna_col is not None else None,missing,unknown) for row in sheet.rows)
        for state,n in sorted(states.items()):
            cover(sheet_name,'extraction_status','dna_id_presence',assessed=n if state!='unavailable' else 0,
                  unavailable=n if state=='unavailable' else 0,reason='derived_'+state)
        for row in sheet.rows:
            context=[]
            if cohort=='circall' and sheet_name=='cohorte_lal' and 'sample_id' in index:
                sample=row[index['sample_id']-1].value
                if sample is None or str(sample).strip()=='':
                    context.append('Blank sample ID; receipt unclassified')
                elif str(sample).strip().casefold()=='na':
                    context.append('Sample explicitly not received')
            if not_extracted(row):context.append('No DNA ID; not extracted')
            row_contexts[sheet_name,row[0].row]=context
        safe = lambda col: headers[col] if headers[col] in known else f'column_{col}'
        required = rules['required'] + (rules['patient_required'] if sheet_name!='cohorte_control' else [])
        for field in required:
            if field not in counts:
                emit(sheet_name,field,'header_missing',scope=field)
                cover(sheet_name,field,'field_checks',reason='required_header_missing',unavailable=1)
        cover(sheet_name,'(headers)','schema',assessed=len(sheet.headers))
        for header in sheet.headers:
            field = safe(header.column)
            if header.raw is not None and (str(header.raw)!=str(header.raw).strip() or '\u00a0' in str(header.raw)):
                emit(sheet_name,field,'whitespace',header.coordinate)
            if headers[header.column] and counts[headers[header.column]]>1:
                emit(sheet_name,field,'header_duplicate',header.coordinate)
        for col,raw_field in headers.items():
            field = safe(col)
            if counts.get(raw_field,0)>1:
                cover(sheet_name,field,'field_checks',reason='duplicate_header',unavailable=len(sheet.rows))
                continue
            if raw_field in identifiers:
                cover(sheet_name,field,'identifier_checks',reason='deferred_by_investigator',unavailable=len(sheet.rows))
                continue
            definition = rules['fields'].get(raw_field)
            assessed = 0
            skipped = Counter()
            for row in sheet.rows:
                cell = row[col-1]
                if not raw_field:
                    if cell.raw is not None:
                        emit(sheet_name,field,'unheaded_data',cell.coordinate)
                    continue
                if cell.formula:
                    for rule in formula_findings(cell,sheet_name,headers,identifiers):
                        if rule=='identifier_reference' and (definition is None or definition['type']!='number'):
                            continue
                        emit(sheet_name,field,rule,cell.coordinate)
                    if cell.value is None and cell.cached_type != 'str':
                        emit(sheet_name,field,'cache_missing',cell.coordinate)
                if cell.cached_type=='e' or cell.data_type=='e':
                    emit(sheet_name,field,'excel_error',cell.coordinate)
                    skipped['excel_error']+=1
                    continue
                if not_extracted(row) and raw_field in rules['extraction_dependent_fields'] and cell.value is not None and str(cell.value).strip().casefold() not in missing | unknown:
                    emit(sheet_name,field,'extraction_state_conflict',cell.coordinate)
                if definition is None:
                    continue
                value = cell.value
                if definition.get('specimens') is not None:
                    specimen_col=index.get('specimen_type')
                    specimen=row[specimen_col-1].value if specimen_col is not None else None
                    if specimen not in definition['specimens']:
                        skipped['specimen_not_applicable']+=1
                        continue
                if value is not None and str(value).strip().casefold() in unknown:
                    skipped['explicit_unknown']+=1
                    continue
                if value is None or str(value).strip().casefold() in missing:
                    skipped['not_applicable_not_extracted' if not_extracted(row) and raw_field in rules['extraction_dependent_fields'] else 'missing_or_intentionally_empty']+=1
                    continue
                assessed += 1
                if isinstance(value,str) and (value != value.strip() or '\u00a0' in value):
                    emit(sheet_name,field,'whitespace',cell.coordinate)
                if raw_field=='extraction_status':
                    dna_col=index.get(rules['extraction_basis'])
                    derived=extraction_state(row[dna_col-1] if dna_col is not None else None,missing,unknown)
                    if value in ('yes','no') and derived in ('yes','no') and value!=derived:
                        emit(sheet_name,field,'extraction_state_conflict',cell.coordinate)
                kind = definition['type']
                annotation = str(value).strip().casefold()
                if kind in ('number','date') and annotation in {v.casefold() for v in rules['workflow_annotations']}:
                    emit(sheet_name,field,'workflow_annotation',cell.coordinate)
                    continue
                if kind=='number':
                    n,status = number(value,missing,unknown)
                    rule = {'invalid':'number_invalid','annotation':'number_text','text':'numeric_text'}.get(status)
                    if status=='annotation' and definition['unit']=='mL' and re.fullmatch(r'\d+\s+aliquots?',annotation):
                        rule='aliquot_annotation'
                    elif status=='annotation' and re.fullmatch(r'[<>≤≥]?\s*\d+(?:[.,]\d+)?\s*(?:ml|[µμu]l|ng|pg|bp|ng/[µμu]l|ng/ml)',annotation):
                        rule='unit_annotation'
                    if rule:
                        emit(sheet_name,field,rule,cell.coordinate)
                    if n is not None and (n<definition.get('minimum',-math.inf) or n>definition.get('maximum',math.inf)):
                        emit(sheet_name,field,'number_invalid',cell.coordinate)
                elif kind=='date' and not isinstance(value,(date,datetime)):
                    emit(sheet_name,field,'date_text',cell.coordinate)
                elif kind=='category' and value not in definition['allowed']:
                    emit(sheet_name,field,'category',cell.coordinate)
            cover(sheet_name,field,'formula_checks',assessed=sum(row[col-1].formula is not None for row in sheet.rows))
            if definition is None:
                cover(sheet_name,field,'semantic_validation',reason='no_semantic_rule',unavailable=len(sheet.rows))
            else:
                cover(sheet_name,field,definition['type']+'_checks',assessed)
                for reason,n in sorted(skipped.items()):
                    cover(sheet_name,field,definition['type']+'_checks',unavailable=n,reason=reason)
                if definition['type']=='text':
                    cover(sheet_name,field,'semantic_validation',reason='whitespace_only; meaning_not_assessed',unavailable=len(sheet.rows))
        for calc in rules['calculations']:
            output = calc['output']
            fields = [output,*calc['operands']]
            if any(f not in index for f in fields+(['specimen_type'] if 'specimen' in calc else [])):
                cover(sheet_name,output,'arithmetic',unavailable=len(sheet.rows),reason='missing_or_duplicate_operand_header')
                continue
            compared = 0
            skipped = Counter()
            for row in sheet.rows:
                if not_extracted(row):
                    skipped['not_applicable_not_extracted']+=1
                    continue
                if 'specimen' in calc and str(row[index['specimen_type']-1].value).strip().casefold()!=calc['specimen']:
                    skipped['specimen_not_applicable']+=1
                    continue
                out,a,b = [row[index[h]-1] for h in fields]
                parsed = [number(c.value,missing,unknown) for c in [out,a,b]]
                z,x,y = [value for value,status in parsed]
                if calc['operation']=='divide' and y is not None and y<=0:
                    emit(sheet_name,output,'denominator',out.coordinate)
                    skipped['nonpositive_denominator']+=1
                    continue
                if x is None or y is None:
                    skipped['operand_explicit_unknown' if any(status=='unknown' for value,status in parsed[1:]) else 'operand_unavailable']+=1
                    if z is not None:
                        emit(sheet_name,output,'false_zero' if out.formula and z==0 else 'missing_operands',out.coordinate)
                    continue
                if z is None:
                    skipped['result_unavailable']+=1
                    if out.cached_type!='e':
                        emit(sheet_name,output,'missing_result',out.coordinate)
                    continue
                compared+=1
                expected = x*y if calc['operation']=='multiply' else x/y
                if not math.isclose(z,expected,rel_tol=rules['rtol'],abs_tol=rules['atol']):
                    emit(sheet_name,output,'arithmetic',out.coordinate)
            cover(sheet_name,output,'arithmetic',compared)
            for reason,n in sorted(skipped.items()):
                cover(sheet_name,output,'arithmetic',unavailable=n,reason=reason)
    # Stable deduplication ensures repeated rule detections cannot inflate counts.
    distinct = {(i['sheet'],i['field'],i['rule'],i['cell'] or i['scope']):i for i in findings}
    findings = sorted(distinct.values(),key=lambda i:(i['sheet'],i['field'],i['rule'],coordinate_to_tuple(i['cell']) if i['cell'] else (0,0)))
    return {'cohort':cohort,'source':source,'sheets':sheet_counts,'findings':findings,
            'groups':group_findings(findings),'coverage':coverage,'summary':summarize(findings)}

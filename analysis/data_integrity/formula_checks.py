"""Check formula references without evaluating workbook formulas."""
import re
from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries


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

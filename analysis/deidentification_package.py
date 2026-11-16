"""Surgical XLSX deidentification; measurements, styles and formula caches survive."""
from collections import Counter
from copy import deepcopy
from html import escape
from pathlib import PurePosixPath
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from analysis.provenance import digest

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS = {'m': MAIN}
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
CLEAR = frozenset({'lastname', 'firstname', 'dob', 'a2g_id', 'source_note', 'private_note'})
# Non-greedy attributes are essential: a formatting-only <c .../> must not absorb
# the next row and its first closing </c>.
CELL = re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?c\b[^>]*?\br="([A-Z]+[0-9]+)"[^>]*?(?:/>|>.*?</(?:[A-Za-z_][\w.-]*:)?c>)', re.S)
ET.register_namespace('', MAIN)


def text(cell, strings):
    if cell.get('t') == 's':
        return ''.join(t.text or '' for t in strings[int(cell.find('m:v', NS).text)].iter('{'+MAIN+'}t'))
    if cell.get('t') == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter('{'+MAIN+'}t'))
    value = cell.find('m:v', NS)
    return value.text if value is not None else None


def sheets(parts):
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(parts['xl/_rels/workbook.xml.rels'])}
    for sheet in ET.fromstring(parts['xl/workbook.xml']).find('m:sheets', NS):
        target = rels[sheet.get(RID)]
        member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        yield sheet.get('name'), member


def column(coordinate):
    return re.sub(r'\d+$', '', coordinate)


def parse_cell(raw, worksheet):
    # Excel can place revision attributes on a formula whose namespace is declared
    # only on the worksheet root. Keep the original fragment bytes for comparison.
    opening = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?worksheet\b[^>]*>', worksheet).group(0)
    namespaces = b' '.join(re.findall(rb'xmlns(?::[A-Za-z0-9_]+)?="[^"]*"', opening))
    return ET.fromstring(b'<root '+namespaces+b'>'+raw+b'</root>')[0]


def plan(parts, role, groups, missing):
    """Return cell edits and names held in memory only; never infer patient links."""
    strings = list(ET.fromstring(parts['xl/sharedStrings.xml'])) if 'xl/sharedStrings.xml' in parts else []
    edits, names, counts = {}, set(), Counter()
    for name, member in sheets(parts):
        rows = ET.fromstring(parts[member]).findall('m:sheetData/m:row', NS)
        if not rows:
            continue
        headers = {column(c.get('r')): text(c, strings) for c in rows[0]}
        if len([h for h in headers.values() if h in CLEAR]) != len({h for h in headers.values() if h in CLEAR}):
            raise ValueError('Duplicate privacy headers require review')
        for row in rows[1:]:
            for cell in row:
                formula = cell.find('m:f', NS)
                if formula is not None and any(re.search(r'(?<![A-Za-z_])\$?'+col+r'\$?\d+', formula.text or '')
                                               for col, field in headers.items() if field in CLEAR):
                    raise ValueError('Formula references a privacy field; dependency review required')
                field = headers.get(column(cell.get('r')))
                value = text(cell, strings)
                if field not in CLEAR or value is None or value == '':
                    continue
                if cell.find('m:f', NS) is not None:
                    raise ValueError('Formula in a privacy field requires dependency review')
                if field in ('lastname', 'firstname') and str(value).strip().casefold() not in missing:
                    names.add(str(value).strip())
                replacement = None
                if role == 'retrospective-blasts' and field == 'lastname':
                    if str(value).strip().casefold() in missing:
                        continue  # Preserve the established unavailable-identity states.
                    replacement = groups[str(value).strip()]
                edits.setdefault(member, {})[cell.get('r')] = replacement
                counts[field] += 1
    return strings, edits, names, counts


def group_values(path, missing):
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    strings = list(ET.fromstring(parts['xl/sharedStrings.xml'])) if 'xl/sharedStrings.xml' in parts else []
    result = set()
    for _, member in sheets(parts):
        rows = ET.fromstring(parts[member]).findall('m:sheetData/m:row', NS)
        if not rows:
            continue
        headers = {column(c.get('r')): text(c, strings) for c in rows[0]}
        for row in rows[1:]:
            for cell in row:
                value = text(cell, strings)
                if headers.get(column(cell.get('r'))) == 'lastname' and value is not None and str(value).strip().casefold() not in missing:
                    result.add(str(value).strip())
    return result


def relation_target(member, target):
    if target.startswith('/'):
        return target.lstrip('/')
    return posixpath.normpath(str(PurePosixPath(member).parent.parent / target))


def scrub_metadata(parts):
    """Remove document properties and comments, including their note drawings/links."""
    removed = {n for n in parts if n.startswith(('docProps/', 'xl/comments', 'xl/threadedComments/', 'xl/persons/'))}
    if any(n.startswith(('xl/externalLinks/', 'xl/embeddings/', 'xl/activeX/')) or n.endswith('vbaProject.bin') for n in parts):
        raise ValueError('External links or embedded content require separate privacy review')
    for name in parts:
        if name.endswith('.vml'):
            shapes = [s for s in ET.fromstring(parts[name]).iter() if s.tag.split('}')[-1] == 'shape']
            if any(s.get('type') != '#_x0000_t202' for s in shapes):
                raise ValueError('Non-comment VML content requires review')
            removed.add(name)
    result = {n: v for n, v in parts.items() if n not in removed}
    for member, raw in list(result.items()):
        if not member.endswith('.rels'):
            continue
        root = ET.fromstring(raw)
        discarded = []
        for rel in list(root):
            if rel.get('TargetMode') == 'External':
                raise ValueError('External relationship requires separate privacy review')
            if relation_target(member, rel.get('Target')) in removed:
                discarded.append(rel.get('Id'))
                root.remove(rel)
        if not discarded:
            continue
        result[member] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        if '/worksheets/_rels/' in member:
            sheet = member.replace('/_rels/', '/').removesuffix('.rels')
            for identifier in discarded:
                pattern = rb'<legacyDrawing\b[^>]*\br:id="'+identifier.encode()+rb'"[^>]*/>'
                result[sheet] = re.sub(pattern, b'', result[sheet])
    content = ET.fromstring(result['[Content_Types].xml'])
    for entry in list(content):
        if entry.get('PartName', '').lstrip('/') in removed:
            content.remove(entry)
    result['[Content_Types].xml'] = ET.tostring(content, encoding='utf-8', xml_declaration=True)
    return result, sorted(removed)


def patch_sheet(raw, strings, edits):
    seen = set()
    def replace(match):
        original = match.group(0)
        coordinate = match.group(1).decode()
        cell = parse_cell(original, raw)
        closing = b'</'+re.match(rb'<([^ >]+)', original).group(1)+b'>'
        if coordinate in edits:
            seen.add(coordinate)
            opening = re.sub(rb'\s+t="[^"]*"', b'', original[:original.index(b'>')+1])
            opening = opening.removesuffix(b'/>')+b'>' if opening.endswith(b'/>') else opening
            if edits[coordinate] is None:
                return opening+closing
            opening = opening[:-1]+b' t="inlineStr">'
            return opening+b'<is xmlns="'+MAIN.encode()+b'"><t>'+escape(edits[coordinate], quote=False).encode()+b'</t></is>'+closing
        if cell.get('t') != 's':
            return original
        if cell.find('m:f', NS) is not None:
            raise ValueError('Shared-string formula cache requires review')
        index = int(cell.find('m:v', NS).text)
        inline = ET.Element('{'+MAIN+'}is')
        for child in strings[index]:
            inline.append(deepcopy(child))
        opening = re.sub(rb'\bt="s"', b't="inlineStr"', original[:original.index(b'>')+1])
        return opening+ET.tostring(inline, encoding='utf-8')+closing
    result = CELL.sub(replace, raw)
    if seen != edits.keys():
        raise ValueError('Unsupported cell encoding; no workbook accepted')
    return result


def signatures(parts):
    """Record logical cells and exact formula/cache XML before/after the package edit."""
    strings = list(ET.fromstring(parts['xl/sharedStrings.xml'])) if 'xl/sharedStrings.xml' in parts else []
    logical, formulas = {}, {}
    for _, member in sheets(parts):
        for match in CELL.finditer(parts[member]):
            raw = match.group(0)
            cell = parse_cell(raw, parts[member])
            value = text(cell, strings)
            logical[member, match.group(1).decode()] = value
            if cell.find('m:f', NS) is not None:
                formulas[member, match.group(1).decode()] = raw
    return logical, formulas


def transform(source, destination, role, groups, missing):
    before_hash = digest(source)
    with ZipFile(source) as archive:
        original = {n: archive.read(n) for n in archive.namelist()}
        infos = archive.infolist()
    strings, edits, names, counts = plan(original, role, groups, missing)
    before_cells, before_formulas = signatures(original)
    output = dict(original)
    for _, member in sheets(original):
        output[member] = patch_sheet(original[member], strings, edits.get(member, {}))
    if 'xl/sharedStrings.xml' in output:
        output['xl/sharedStrings.xml'] = ('<sst xmlns="'+MAIN+'" count="0" uniqueCount="0"/>').encode()
    output, removed = scrub_metadata(output)
    after_cells, after_formulas = signatures(output)
    if before_formulas != after_formulas:
        raise ValueError('Formula or saved formula cache changed')
    if before_cells.keys() != after_cells.keys():
        raise ValueError('Cell coordinates changed')
    for (member, coord), value in before_cells.items():
        expected = edits.get(member, {}).get(coord, value)
        if after_cells[member, coord] != expected:
            raise ValueError('Unapproved cell change')
    with destination.open('xb') as stream, ZipFile(stream, 'w') as archive:
        for info in infos:
            if info.filename in output:
                archive.writestr(info, output[info.filename])
    destination.chmod(0o600)
    with ZipFile(destination) as archive:
        if archive.testzip() is not None or any(archive.read(n) != value for n, value in output.items()):
            raise ValueError('Invalid output archive')
    if digest(source) != before_hash:
        raise ValueError('Original workbook changed')
    return dict(source_sha256=before_hash, output_sha256=digest(destination),
                cleared_or_tokenised_cells=dict(counts), removed_parts=removed,
                preserved_formula_cells=len(before_formulas), preserved_cells=len(before_cells),
                formula_caches='byte-identical', unchanged_original=True), names


def scan_names(path, names):
    """Return locations/counts only, never the removed names or matched text."""
    names = {n for n in names if len(n) >= 2}
    long = [re.compile(r'(?<!\w)'+re.escape(n)+r'(?!\w)', re.I) for n in names if len(n) >= 4]
    exact = {n.casefold() for n in names}
    hits = Counter()
    with ZipFile(path) as archive:
        for member in archive.namelist():
            if member.endswith(('.xml', '.vml', '.rels')):
                root = ET.fromstring(archive.read(member))
                for node in root.iter():
                    for value in [node.text or '', *node.attrib.values()]:
                        if value.strip().casefold() in exact or any(p.search(value) for p in long):
                            hits[member] += 1
    return dict(hits)

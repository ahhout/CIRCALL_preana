"""Byte-preserving XML primitives shared by explicit workbook maintenance."""
from html import escape
import re

CELL = re.compile(rb'<c\b[^>]*?\br="([A-Z]+[0-9]+)"[^>]*?(?:/>|>.*?</c>)',re.S)
ROW = re.compile(rb'(<row\b[^>]*\br="([0-9]+)"[^>]*>)(.*?)(</row>)',re.S)

def cell_xml(coordinate,value,old=None,style=None):
    if old is None:
        opening=f'<c r="{coordinate}"'+(f' s="{style}"' if style is not None else '')+'>'
        opening=opening.encode()
    else:
        opening=old[:old.index(b'>')+1].replace(b'/>',b'>')
        opening=re.sub(rb'\s+t="[^"]*"',b'',opening)
    if value is None:
        return opening[:-1]+b'/>'
    return opening[:-1]+b' t="inlineStr"><is><t xml:space="preserve">'+escape(value,quote=False).encode()+b'</t></is></c>'

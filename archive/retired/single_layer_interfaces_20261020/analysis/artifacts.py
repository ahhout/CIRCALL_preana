"""Workflow-specific artifact contracts; checks never display clinical rows."""
import csv
import json
from pathlib import Path
import struct
import zipfile


def validate_files(output, required):
    output = Path(output)
    for relative, headers in required.items():
        path = output / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Missing or empty required artifact: {relative}')
        if path.suffix == '.csv':
            with path.open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                if len(fields) != len(set(fields)) or not set(headers).issubset(fields):
                    raise ValueError(f'Invalid table headers: {relative}')
        elif path.suffix == '.json':
            try:
                value = json.loads(path.read_text())
            except (ValueError, UnicodeError):
                raise ValueError(f'Invalid JSON artifact: {relative}') from None
            if not isinstance(value, dict):
                raise ValueError(f'Invalid JSON structure: {relative}')
        elif path.suffix == '.png':
            with path.open('rb') as stream:
                header = stream.read(24)
            if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or not all(struct.unpack('>II', header[16:24])):
                raise ValueError(f'Invalid PNG artifact: {relative}')
        elif path.suffix == '.pdf':
            with path.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    raise ValueError(f'Invalid PDF artifact: {relative}')
        elif path.suffix == '.xlsx':
            try:
                with zipfile.ZipFile(path) as book:
                    if 'xl/workbook.xml' not in book.namelist() or book.testzip():
                        raise ValueError
            except (ValueError, zipfile.BadZipFile):
                raise ValueError(f'Invalid workbook artifact: {relative}') from None


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))

from pathlib import Path
import csv

import pandas as pd


class InputDataError(ValueError):
    """Raised when an input table cannot satisfy the configured schema."""


def load_input(config):
    """Read a configured Excel or CSV input table."""
    input_config = config["input"]
    path = Path(input_config["path"])
    if not path.is_file():
        raise InputDataError(f"Input file does not exist: {path}")

    try:
        if input_config["format"] == "excel":
            from openpyxl import load_workbook
            book = load_workbook(path, read_only=True, data_only=True)
            try:
                if input_config['sheet'] not in book.sheetnames:
                    raise InputDataError('Configured input sheet is missing')
                header = list(next(book[input_config['sheet']].iter_rows(values_only=True), []))
            finally:
                book.close()
            validate_headers(header)
            return pd.read_excel(
                path,
                sheet_name=input_config["sheet"],
                decimal=input_config.get("decimal", "."),
            )
        with path.open(newline='', encoding='utf-8-sig') as stream:
            validate_headers(next(csv.reader(stream, delimiter=input_config['delimiter']), []))
        return pd.read_csv(
            path,
            sep=input_config["delimiter"],
            decimal=input_config.get("decimal", "."),
        )
    except (ValueError, OSError) as exc:
        if isinstance(exc, InputDataError):
            raise
        raise InputDataError('Could not read configured input; verify format and sheet') from None


def validate_headers(header):
    populated = [value for value in header if value is not None and value != '']
    if len(populated) != len(set(populated)):
        raise InputDataError('Input contains duplicate column headers')

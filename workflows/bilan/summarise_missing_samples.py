#!/usr/bin/env python3
"""Summarise CIRCALL rows where sample_id is 'na'.

Uses only the Python standard library; no package installation is required.
If no workbook is specified, the only non-temporary .xlsx file in data/raw/circall is used.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
NS = {"m": MAIN_NS}
HOSPITALS = {"001": "RDB", "002": "TRS"}
CELL_REF = re.compile(r"([A-Z]+)\d+")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIMEPOINT_ORDER = {"Diag": 0, "D4": 1, "D8": 2, "D15": 3, "TP1": 4, "TP2": 5}
CORE_TIMEPOINTS = [
    ("Diag", "Diagnosis"),
    ("D4", "J4"),
    ("D8", "J8"),
    ("D15", "J15"),
    ("TP1", "TP1"),
    ("TP2", "TP2"),
]
COMPARTMENTS = [
    ("plasma", "Plasma"),
    ("blood pellet", "Blood pellet"),
    ("bone marrow", "Bone marrow"),
    ("CSF", "CSF"),
]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise rows with sample_id=na by timepoint, compartment and hospital."
    )
    parser.add_argument(
        "workbook",
        type=Path,
        nargs="?",
        help="Input .xlsx file (defaults to the only .xlsx file in data/raw/circall)",
    )
    parser.add_argument("--sheet", default="cohorte_lal", help="Sheet to parse")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/missing_samples_by_hospital_timepoint.csv",
        help="Summary CSV path",
    )
    parser.add_argument(
        "--details-output",
        type=Path,
        help="Optional CSV with one row per missing sample",
    )
    parser.add_argument(
        "--table-output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/missing_samples_bias_summary.png",
        help="Presentation-ready summary table image",
    )
    parser.add_argument(
        "--compartment-output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/missing_samples_by_hospital_compartment.csv",
        help="Hospital-by-compartment summary CSV",
    )
    parser.add_argument(
        "--compartment-table-output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/missing_samples_compartment_summary.png",
        help="Presentation-ready hospital-by-compartment table image",
    )
    return parse_arguments(parser)


def parse_arguments(parser):
    args = parser.parse_args()
    if target := os.environ.get("PRE_ANALYSIS_ARGUMENTS_FILE"):
        Path(target).write_text(json.dumps(vars(args), indent=2, default=str) + "\n")
    return args


def resolve_workbook(workbook: Path | None) -> Path:
    if workbook is not None:
        if not workbook.is_file():
            raise SystemExit(f"Workbook not found: {workbook}")
        return workbook

    candidates = sorted(
        path for path in (PROJECT_ROOT / "data/raw/circall").glob("*.xlsx") if not path.name.startswith("~$")
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SystemExit(
            "No .xlsx workbook found. Pass one explicitly, for example: "
            "python3 summarise_missing_samples.py workbook.xlsx"
        )
    names = ", ".join(path.name for path in candidates)
    raise SystemExit(f"Multiple .xlsx workbooks found; specify one explicitly: {names}")


def read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def get_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = read_xml(archive, "xl/sharedStrings.xml")
    return ["".join(n.text or "" for n in item.findall(".//m:t", NS)) for item in root]


def get_sheet_path(archive: zipfile.ZipFile, requested: str) -> str:
    workbook = read_xml(archive, "xl/workbook.xml")
    rels = read_xml(archive, "xl/_rels/workbook.xml.rels")
    targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    available = []
    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        name = sheet.attrib["name"]
        available.append(name)
        if name == requested:
            target = targets[sheet.attrib[DOC_REL]].lstrip("/")
            if target.startswith("xl/"):
                return target
            return str(PurePosixPath("xl") / target)
    raise SystemExit(f"Sheet {requested!r} not found. Available sheets: {available}")


def value_of(cell: ET.Element, strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(n.text or "" for n in cell.findall(".//m:t", NS))
    node = cell.find("m:v", NS)
    value = "" if node is None else node.text or ""
    return strings[int(value)] if cell_type == "s" and value else value


def parse_rows(archive: zipfile.ZipFile, sheet: str) -> list[dict[str, str]]:
    strings = get_shared_strings(archive)
    root = read_xml(archive, get_sheet_path(archive, sheet))
    rows = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        parsed = {}
        for cell in row.findall("m:c", NS):
            match = CELL_REF.fullmatch(cell.attrib["r"])
            if match:
                parsed[match.group(1)] = value_of(cell, strings)
        rows.append(parsed)
    return rows


def hospital_for(circall_id: str) -> str:
    clean_id = circall_id.replace("\u00a0", "").strip()
    prefix = clean_id[:3]
    return HOSPITALS.get(prefix, f"UNKNOWN ({prefix})")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def rate_text(missing: int, assessed: int) -> str:
    percentage = 100 * missing / assessed if assessed else 0
    return f"{missing}/{assessed} ({percentage:.1f}%)"


def write_summary_table(
    path: Path, rows: list[dict[str, object]], title: str
) -> None:
    cache_root = Path("/tmp/bilan_plot_cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgba
    except ImportError as exc:
        raise SystemExit(
            "Table rendering requires matplotlib. Run this script with the "
            "pre_analysis conda environment."
        ) from exc

    columns = list(rows[0])
    labels = {
        "hospital": "Hospital",
        "affected_patients": "Affected\npatients",
        "all_assessed_samples": "All assessed\nrows",
        "Diagnosis": "Diagnosis",
        "J4": "J4",
        "J8": "J8",
        "J15": "J15",
        "TP1": "TP1",
        "TP2": "TP2",
        "Plasma": "Plasma",
        "Blood pellet": "Blood pellet",
        "Bone marrow": "Bone marrow",
        "CSF": "CSF",
    }
    cell_text = [[str(row[column]) for column in columns] for row in rows]
    figure, axis = plt.subplots(figsize=(max(9, 1.5 * len(columns)), 3.4))
    axis.axis("off")
    table = axis.table(
        cellText=cell_text,
        colLabels=[labels[column] for column in columns],
        cellLoc="center",
        loc="center",
        bbox=[0, 0.18, 1, 0.65],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for column in range(len(columns)):
        table[(0, column)].set_facecolor("#355C7D")
        table[(0, column)].get_text().set_color("white")
        table[(0, column)].get_text().set_weight("bold")
    for row_index, row in enumerate(rows, start=1):
        table[(row_index, 0)].get_text().set_weight("bold")
        if row["hospital"] == "Overall":
            for column in range(len(columns)):
                table[(row_index, column)].set_facecolor("#E8EDF2")
        for column, key in enumerate(columns[1:], start=1):
            value = str(row[key])
            match = re.search(r"\((\d+(?:\.\d+)?)%\)", value)
            if match:
                intensity = min(float(match.group(1)) / 25, 1)
                table[(row_index, column)].set_facecolor(
                    to_rgba("#F4A6A6", alpha=0.15 + 0.55 * intensity)
                )
    axis.set_title(title, fontsize=14, weight="bold", pad=10)
    figure.text(
        0.5,
        0.06,
        "Cells show missing / assessed (missing %). Assessed rows have a nonblank "
        "sample_id; missing means sample_id = 'na'.",
        ha="center",
        va="center",
        fontsize=8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = arguments()
    workbook = resolve_workbook(args.workbook)
    with zipfile.ZipFile(workbook) as archive:
        rows = parse_rows(archive, args.sheet)
    if not rows:
        raise SystemExit("The selected sheet is empty")

    columns = {name.strip(): column for column, name in rows[0].items()}
    required = {"circall_id", "sample_id", "timepoint", "compartment"}
    missing_columns = required - columns.keys()
    if missing_columns:
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing_columns))}")

    details: list[dict[str, object]] = []
    cohort_patients: dict[str, set[str]] = defaultdict(set)
    affected_patients: dict[str, set[str]] = defaultdict(set)
    sample_states: Counter[tuple[str, str, str]] = Counter()
    compartment_states: Counter[tuple[str, str, str]] = Counter()
    for row in rows[1:]:
        circall_id = row.get(columns["circall_id"], "").replace("\u00a0", "").strip()
        if not circall_id:
            continue
        hospital = hospital_for(circall_id)
        cohort_patients[hospital].add(circall_id)

        sample_id = row.get(columns["sample_id"], "").strip()
        timepoint = row.get(columns["timepoint"], "").strip()
        compartment = row.get(columns["compartment"], "").strip()
        if not timepoint or not compartment:
            continue
        if not sample_id:
            state = "blank"
        elif sample_id.casefold() == "na":
            state = "missing"
        else:
            state = "present"
        sample_states[(hospital, "All", state)] += 1
        sample_states[(hospital, timepoint, state)] += 1
        compartment_states[(hospital, compartment, state)] += 1
        if state != "missing":
            continue
        affected_patients[hospital].add(circall_id)
        details.append(
            {
                "circall_id": circall_id,
                "hospital": hospital,
                "timepoint": timepoint,
                "compartment": compartment,
            }
        )

    hospital_totals = Counter(str(row["hospital"]) for row in details)
    summary = []
    for hospital in ["RDB", "TRS", "Overall"]:
        source_hospitals = ["RDB", "TRS"] if hospital == "Overall" else [hospital]
        patients = set().union(*(cohort_patients[name] for name in source_hospitals))
        affected = set().union(*(affected_patients[name] for name in source_hospitals))

        def state_count(timepoint: str, state: str) -> int:
            return sum(sample_states[(name, timepoint, state)] for name in source_hospitals)

        missing_all = state_count("All", "missing")
        assessed_all = missing_all + state_count("All", "present")
        result: dict[str, object] = {
            "hospital": hospital,
            "affected_patients": rate_text(len(affected), len(patients)),
            "all_assessed_samples": rate_text(missing_all, assessed_all),
        }
        for timepoint, label in CORE_TIMEPOINTS:
            missing = state_count(timepoint, "missing")
            assessed = missing + state_count(timepoint, "present")
            result[label] = rate_text(missing, assessed)
        summary.append(result)

    fieldnames = [
        "hospital",
        "affected_patients",
        "all_assessed_samples",
        *(label for _timepoint, label in CORE_TIMEPOINTS),
    ]
    write_csv(
        args.output,
        fieldnames,
        summary,
    )
    write_summary_table(
        args.table_output,
        summary,
        "Explicitly missing CIRCALL samples by hospital and timepoint",
    )

    compartment_summary = []
    for hospital in ["RDB", "TRS", "Overall"]:
        source_hospitals = ["RDB", "TRS"] if hospital == "Overall" else [hospital]

        def compartment_state_count(compartment: str, state: str) -> int:
            return sum(
                compartment_states[(name, compartment, state)]
                for name in source_hospitals
            )

        missing_all = sum(
            compartment_state_count(compartment, "missing")
            for compartment, _label in COMPARTMENTS
        )
        assessed_all = missing_all + sum(
            compartment_state_count(compartment, "present")
            for compartment, _label in COMPARTMENTS
        )
        result = {
            "hospital": hospital,
            "all_assessed_samples": rate_text(missing_all, assessed_all),
        }
        for compartment, label in COMPARTMENTS:
            missing = compartment_state_count(compartment, "missing")
            assessed = missing + compartment_state_count(compartment, "present")
            result[label] = rate_text(missing, assessed)
        compartment_summary.append(result)

    compartment_fieldnames = [
        "hospital",
        "all_assessed_samples",
        *(label for _compartment, label in COMPARTMENTS),
    ]
    write_csv(
        args.compartment_output,
        compartment_fieldnames,
        compartment_summary,
    )
    write_summary_table(
        args.compartment_table_output,
        compartment_summary,
        "Explicitly missing CIRCALL samples by hospital and compartment",
    )
    if args.details_output:
        write_csv(
            args.details_output,
            ["circall_id", "hospital", "timepoint", "compartment"],
            details,
        )

    print(f"Missing samples: {len(details)}")
    print(
        "Affected patients: "
        f"{len(affected_patients['RDB'] | affected_patients['TRS'])}"
    )
    print(f"TRS: {hospital_totals['TRS']}")
    print(f"RDB: {hospital_totals['RDB']}")
    print(f"Summary rows: {len(summary)}")
    print(f"Wrote: {args.output}")
    print(f"Wrote: {args.table_output}")
    print(f"Wrote: {args.compartment_output}")
    print(f"Wrote: {args.compartment_table_output}")
    if args.details_output:
        print(f"Wrote: {args.details_output}")


if __name__ == "__main__":
    main()

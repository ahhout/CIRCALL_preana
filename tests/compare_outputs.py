"""Compare local migration outputs without printing table contents or identifiers."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


def compare_tree(baseline, candidate):
    extensions = {".csv", ".xlsx", ".png", ".jpeg", ".jpg"}
    before = {p.relative_to(baseline): p for p in baseline.rglob("*") if p.suffix in extensions}
    after = {p.relative_to(candidate): p for p in candidate.rglob("*") if p.suffix in extensions}
    result = {"missing": sorted(map(str, before.keys() - after.keys())), "extra": sorted(map(str, after.keys() - before.keys())), "tables": 0, "sheets": 0, "images": 0, "failures": []}
    for name in sorted(before.keys() & after.keys()):
        try:
            if name.suffix == ".csv":
                pd.testing.assert_frame_equal(pd.read_csv(before[name]), pd.read_csv(after[name]), check_exact=False, rtol=1e-9, atol=1e-12)
                result["tables"] += 1
            elif name.suffix == ".xlsx":
                left = pd.read_excel(before[name], sheet_name=None)
                right = pd.read_excel(after[name], sheet_name=None)
                if list(left) != list(right):
                    raise AssertionError("sheet mismatch")
                for sheet in left:
                    pd.testing.assert_frame_equal(left[sheet], right[sheet], check_exact=False, rtol=1e-9, atol=1e-12)
                    result["sheets"] += 1
                result["tables"] += 1
            else:
                with Image.open(before[name]) as left, Image.open(after[name]) as right:
                    if not np.array_equal(np.asarray(left), np.asarray(right)):
                        raise AssertionError("pixel mismatch")
                result["images"] += 1
        except Exception:
            # Assertion messages from pandas can include patient data: report filenames only.
            result["failures"].append(str(name))
    result["passed"] = not (result["missing"] or result["extra"] or result["failures"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-retrospective", type=Path, required=True)
    parser.add_argument("--baseline-bilan", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.baseline_retrospective, args.baseline_bilan, args.candidate / "retrospective", args.candidate / "bilan"):
        if not path.is_dir():
            parser.error(f"Directory not found: {path}")
    result = {
        "float_tolerance": {"relative": 1e-9, "absolute": 1e-12},
        "retrospective": compare_tree(args.baseline_retrospective, args.candidate / "retrospective"),
        "bilan": compare_tree(args.baseline_bilan, args.candidate / "bilan"),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if all(result[key]["passed"] for key in ("retrospective", "bilan")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

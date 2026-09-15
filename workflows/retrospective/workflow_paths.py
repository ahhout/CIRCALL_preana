"""Resolve CLI paths without changing the scientific defaults."""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "outputs/manual/retrospective"


def parse_workflow_args(parser, *, inputs, outputs, root_flag):
    parser.set_defaults(**{
        key: str(REPO_ROOT / "data/retrospective" / filename)
        for key, filename in inputs.items()
    })
    if root_flag:
        parser.set_defaults(**{root_flag: str(DEFAULT_OUTPUT)})
    args = parser.parse_args()
    output_root = Path(getattr(args, root_flag) if root_flag else DEFAULT_OUTPUT).resolve()
    if root_flag == "outputs_dir" and args.test_outputs_dir:
        output_root = Path(args.test_outputs_dir).resolve()
        args.test_outputs_dir = str(output_root)
    if root_flag:
        setattr(args, root_flag, str(output_root))
    results = output_root if root_flag == "outputs_dir" and output_root.name == "results" else output_root / "results"
    for key in outputs:
        value = getattr(args, key)
        if value is None or str(value).strip().lower() in ("none", ""):
            continue
        path = results / Path(value).name if value == parser.get_default(key) else Path(value)
        setattr(args, key, str(path.resolve()))
    for key in inputs:
        setattr(args, key, str(Path(getattr(args, key)).resolve()))
    if target := os.environ.get("PRE_ANALYSIS_ARGUMENTS_FILE"):
        Path(target).write_text(json.dumps(vars(args), indent=2, default=str) + "\n")
    return args

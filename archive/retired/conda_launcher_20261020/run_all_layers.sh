#!/usr/bin/env bash
# One integrated run; cohort quality holds do not suppress independent work.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: ./run_all_layers.sh [--validate-only] [--no-pdf-output | --pdf-output] [--output-dir PATH]

Preflight and run Layers 1–4 with one manifest and output root.
Independent work continues after quality holds or workflow failures; the final
exit is nonzero if selected work is blocked or fails. Invalid configuration or
worker-preflight failure stops before execution. Existing outputs are refused.

  --validate-only   Preflight only; publish nothing, return nonzero on known holds.
  --no-pdf-output   Save PNG figures only; --pdf-output restores PDF export.
  --output-dir PATH Select a fresh destination (default: outputs/layered/run_*).
  -h, --help        Show this help.
HELP
}

arguments=()
while (( $# > 0 )); do
    case "$1" in
        --layers|--workflow|--layers=*|--workflow=*)
            echo 'Partial layer execution is retired; use ./run_all_layers.sh for all four layers.' >&2
            exit 2 ;;
        --pdf-output|--no-pdf-output) arguments+=("$1"); shift ;;
        --validate-only) arguments+=("$1"); shift ;;
        --output-dir)
            if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
                usage >&2
                exit 2
            fi
            arguments+=("$1" "$2"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
if ! command -v conda >/dev/null 2>&1; then
    echo 'Conda is required; open a shell where conda is available.' >&2
    exit 1
fi

exec conda run --no-capture-output -n pre_analysis python run.py \
    --config configs/pipeline_layers.json "${arguments[@]}"

# Copilot repository instructions (bioinformatics)

## General behavior
- For simple questions, answer in 1–3 sentences.
- For medium questions, give me 4–6 sentences.
- For complex questions, give me one summary paragraph followed by up to 5 bullet points.
- Start directly with the answer.
- Stop after the last relevant fact.

## Environment
- Use conda exclusively.
- Do NOT create or reference virtualenv/venv or `.venv`.
- Always consult `env.yml` / `environment.yml`.
- If adding dependencies, update env.yml and avoid unnecessary packages.

## Parameter & decision handling
- Treat biological thresholds and pipeline settings as experimental design choices.
- Do NOT silently choose filtering thresholds, annotation rules, genome builds, or database versions.
- Confirm any analysis thresholds with the user.
- Expose parameters via CLI/config instead of hardcoding.
- Clearly state assumptions and request confirmation for decisions affecting interpretation or reproducibility.

## Reproducibility
- Prefer deterministic behavior and explicit parameters.
- Log important run parameters.
- When using annotation databases, state name, version, and genome build.
- Avoid hidden defaults.

## Script requirements
- Provide a CLI interface (argparse).
- Validate inputs early (existence, format, headers).
- Fail loudly with meaningful errors.
- Log key filtering steps and counts.
- Avoid overwriting or deleting raw data by default.

## Bioinformatics data conventions
- Assume large datasets; avoid loading full BAM/VCF into memory.
- Prefer streaming or indexed access.
- Preserve headers in VCF/BAM-derived outputs.
- Explicitly specify genome build (hg19 vs hg38).
- Be aware of contig naming differences (chr1 vs 1).
- Avoid coordinate conversions or aggressive filtering without confirmation.

## Data safety
- Assume clinical data may exist.
- Do NOT output or log patient names.

## Pipeline safety
Require confirmation before:
- data deletion or overwriting
- liftover or coordinate transformation
- merging samples
- aggressive filtering steps

## Coding safety
Bash:
- use `set -euo pipefail`
- quote variables

Python:
- use pathlib for paths
- prefer subprocess.run(..., check=True)
- avoid os.system

## Documentation
- Provide explicit commands with expected inputs/outputs.
- Prefer practical, lab-runnable examples.

## Philosophy
Act as a cautious scientific collaborator:
- prefer transparency and parameter exposure
- avoid overengineering
- avoid confident biological claims without confirmation

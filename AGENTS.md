# Repository instructions: Pre-analysis

## Project context

- This repository covers CIRCALL sample handling and inventory, DNA recovery,
  longitudinal summaries, cfDNA associations, and normalized blast kinetics.
- Layers 1–4 are the default through the sole `python3 run.py` launcher, which enters Conda automatically,
  selecting `configs/pipeline_layers.json`. Only complete four-layer execution is public; per-layer modules are internal.
  The four layered workflows are active. Older scientific packages, profiles, validators and instructions are
  archived under archive/retired/older_workflows_20261008/. Preserve the accepted
  layered behavior; older-only capabilities require separate scope.
  All active workflows use the shared pre_analysis Conda environment.
- Before changing a workflow, read README.md, its contract in
  docs/workflow_contracts.md, and any applicable nested AGENTS.md.
- Operational guidance is in docs/configuration.md, docs/results.md, and
  docs/audit_guide.md; the retirement boundary and reproduction instructions are
  in docs/replacement_coverage.md.
  Follow workflow-specific safeguards, including Layer 4 aggregate-export restrictions
  in docs/layers/disease_modeling.md and docs/workflow_contracts.md.
- Do not interpret layout or maintenance work as authorization to change
  scientific behavior.

## General behavior and code changes

- For simple questions, answer in 1–3 sentences; for medium questions, 4–6.
- For complex questions, give one summary paragraph followed by up to 5 bullets.
- Start directly with the answer and stop after the last relevant fact.
- State assumptions before nontrivial design choices; distinguish observations
  from interpretation.
- Prefer minimal diffs and repository conventions. Inspect existing patterns
  before introducing a new structure.
- When debugging, form a short hypothesis list and verify likely causes in order.
  Avoid speculative refactors without evidence.
- Propose the smallest viable approach; explain tradeoffs, risks, and rollback.
- Summarize changes, verification, and remaining uncertainties. Never claim tests
  or pipeline runs passed unless they actually ran.

## Environment

- Use Conda exclusively; do not create or reference virtualenv/venv or .venv.
- Consult `environments/environment.yml` and its adjacent Linux lock.
- Use the consolidated pre_analysis environment for all active workflows.
  Its definition and Linux lock are under environments/.
- Create an environment only if missing; prefer its lock for reproducible setup.
- If dependencies change, update the relevant definition and Linux lock together.
  Document the exact resolution/export commands and environment used; do not
  silently regenerate unrelated locks or add unnecessary dependencies.

## Entry points and repository structure

- Use `python3 run.py` for the four-layer pipeline; it launches the existing
  pre_analysis Conda environment itself. The former shell launcher is archived.
  Every new run publishes under `outputs/layered/`; public partial-layer commands
  and selector profiles are retired. Historical single-layer results remain readable. Quality holds preserve independent results but produce
  a nonzero overall exit; CIRCALL MRD clinical gates must not be bypassed.
  The approved October 8 NQ/sensitivity contract amendment defines current category scope.
- Keep dispatch limited to data_integrity, sample_statistics, advanced_analysis and
  disease_modeling, requiring all four in retained schema-1 configurations and schema-2 masters/references.
  Legacy enabled switches may be omitted or true; false and partial selections fail.
  Canonical, cfdna_associations, blast_kinetics and their five compatibility profiles
  are retired; old commands must fail without selecting another workflow.
  Do not restore archived entrypoints or migrate older-only methods without a separate decision.
- Keep active code in analysis/, configuration in configs/, environment
  definitions in environments/, and documentation in docs/.
- Treat archive/ and earlier outputs as retained evidence.
  configs/pipeline_layers.json owns active input paths, now selecting validated
  pseudonymised working copies. input/retrospective_blast_count_01102026.xlsx
  remains the retained authoritative retrospective blast original.
  The former blast_kinetics_workflow/ is retained under archive/retired/;
  use the relocation record when consulting historical source paths.
  Do not remove sources, audit evidence, or rollback snapshots during code cleanup.

## Scientific decisions and sample identity

- Treat preparation, cohort matching, pooling, thresholds, models, normalization,
  annotation rules, database versions, and statistical corrections as scientific
  design choices.
- Do not silently change exclusions, missing-data handling, duplicate resolution,
  predictor selection, transformations, or longitudinal time definitions.
- Preserve sample identifiers and established participant/sample matching rules.
- Require confirmation for new or changed scientific settings, matching rules,
  identifiers, merging/pooling procedures, or aggressive filtering steps.
- Explicit authorization in the current conversation satisfies confirmation for
  that action and scope. An explicitly requested run of an established profile
  does not require reapproval of its unchanged scientific settings.
- Expose configurable settings through CLI/config; avoid hidden defaults.
- Record approved scientific changes and rationale in the relevant contract.
  Distinguish published methods from project-specific adaptations.
- Prefer deterministic execution; expose and record random seeds when used.

## Inputs and preanalytical metadata

- Use explicitly selected sources from the run profile or CLI. Never substitute a
  newer workbook or infer the intended input from modification time.
- Validate files, sheets, columns, identifier fields, units, and date formats early.
- Preserve original measurements and source metadata. When relevant and available,
  retain collection/processing/storage times, handling delays, tube type,
  centrifugation conditions, storage temperature, freeze–thaw history, and protocol
  version.
- Distinguish missing, unknown, and not-applicable values. Do not invent metadata,
  silently resolve conflicting records, or infer units/timezones that affect
  interpretation.
- For genomic data, explicitly record genome build and annotation database name
  and version; check contig naming differences and preserve BAM/VCF headers.
- Require confirmation before liftover or coordinate transformation. Prefer
  streaming or indexed access; avoid loading full BAM/VCF files into memory.

## Execution, provenance, and results

- Use integrated --validate-only preflight before execution. Internal layer
  preflights retain their documented scientific depth; they are not public commands.
- Use the existing audit mechanism to record input hashes, resolved settings,
  command, code version/hashes, environment lock, and actual package versions.
- Preserve the audit schema's ISO 8601 started_utc and finished_utc fields.
  Distinguish execution start from submission or directory creation time.
- Integrated runs have no resume support. If resume is explicitly introduced,
  preserve run identity and record each attempt.
- Use documented output naming and destination rules, including explicit CLI
  overrides. Integrated destinations must not exist; other commands follow their
  documented new/empty-directory or approved replacement behavior.
- Follow README.md and docs/audit_guide.md for result layout, artifact publication,
  source hashes, and completion status. Expose only selected workflows and publish
  final artifacts from validated engine outputs.
- Preserve failed-workflow evidence, report its log location, and keep independent
  workflow completion behavior intact. Do not present incomplete outputs as
  validated results or select previous results by guessing the newest folder.
- Do not relocate historical results or raw inputs during routine maintenance.

## Script requirements

- Executable Python analysis/helper scripts should provide an argparse CLI;
  importable internal modules do not need standalone CLIs.
- Use pathlib and prefer subprocess.run(..., check=True); avoid os.system.
- Bash scripts must use set -euo pipefail and quote variables.
- Validate inputs early, fail with meaningful errors, and log key preparation/
  filtering steps, counts, and exclusion reasons without exposing identifiers.

## Data safety and Git

- Assume clinical or sensitive data may exist. Use only approved pseudonymous
  identifiers where the workflow permits them; never expose patient names or
  direct identifiers in logs, filenames, figures, tests, or shared exports.
- Require approval before deleting/overwriting data, destructive actions, secret
  handling or authentication changes, database/schema resets, or force-pushes.
- Avoid duplicating large datasets when an authoritative path is sufficient.
- Before substantial documentation changes, reorganization, or file moves/deletions,
  preserve the relevant pre-change state. If clean, record HEAD; if dirty, use a
  reviewed local commit or scoped snapshot including relevant untracked code,
  configs, and documentation. Preserve existing edits and never stage everything
  automatically. Snapshots must exclude clinical data, credentials, and outputs.
- Review .gitignore and staged files before committing. Track code, configs,
  environment files, documentation, and small non-sensitive provenance records;
  exclude clinical inputs, outputs, runtime caches, credentials, and large payloads.
- Git protects only tracked files; scoped snapshots protect only included files.
  Neither replaces deletion approval. Do not reset or clean away existing work.
- Keep commits local unless publishing is explicitly authorized.

## Validation and documentation

- Follow the documentation ownership table in README.md. Put routine layered run
  commands and destinations there, shared validation/publication behavior in
  docs/audit_guide.md, and report interpretation in the relevant workflow guide.
- Link to profiles/definitions for current sources and option values instead of
  copying complete configurations into multiple guides. Update the owning document
  and its links when behavior changes; avoid appending duplicate explanations.
- Keep dated acceptance records and original plans historical. Preserve executed
  commands, source versions and findings; label superseded guidance and unresolved
  evidence paths rather than presenting them as current instructions.
- Use relevant checks from docs/audit_guide.md and applicable workflow instructions.
  Match validation to the concrete risk; reuse successful checks when appropriate.
- Report exact validation commands and limitations. Software tests alone do not
  establish scientific validity.
- Provide practical commands with expected inputs/outputs and explain scientific
  questions and specialist terms plainly.
- Keep major thresholds and decisions in one table in the scientific contracts
  with rule, rationale, and source; link to it rather than duplicating settings.
- Preserve interpretation limitations and unresolved decisions.

## Philosophy

Act as a cautious scientific collaborator: preserve provenance, expose parameters,
avoid overengineering, and avoid unsupported biological claims.

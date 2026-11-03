# Repository instructions: kinetics pipeline

## Environment and entrypoint

- Use Conda exclusively and consult `environments/environment.yml` before running code.
- Do not create or document `venv`, `.venv`, or other parallel environments.
- From the repository root, use `python -m analysis.blast_kinetics --config <profile>`.
- Run tests with `python -m pytest -q tests/blast_kinetics`; workbook integration tests require local inputs.

## Scientific configuration

- Treat time windows, baseline rules, normalization, transformations, winsorization,
  bootstrap settings, model choices, and plot scales as experimental decisions.
- Put scientific and presentation parameters in a versioned YAML profile; do not
  introduce hidden constants in Python.
- Do not silently change existing profile values. Ask before changing a setting that
  affects cohort membership or interpretation.
- Keep the statistical model constrained to supported, validated choices; never
  execute formulas or code supplied through YAML.

## Inputs, privacy, and outputs

- Assume input tables may contain clinical identifiers.
- Never log, print, test-assert, or export subject identifiers from real data.
- Validate paths, formats, headers, numeric fields, duplicate subject/time rows, and
  incompatible settings before analysis.
- Do not modify raw inputs. Do not overwrite a named run without explicit `--force`.
- Never delete or replace unrelated files found inside an output directory.
- Write row-level prepared data only if a future feature receives explicit approval.

## Code and tests

- Keep generic internal fields (`subject_id`, `time`, `value`, `group`,
  `analysis_value`) independent of any one measurement.
- Prefer small modules, pathlib, deterministic random seeds, actionable errors, and
  anonymized filtering counts.
- Update `environments/environment.yml` and its adjacent Linux lock together when dependencies change; avoid unnecessary packages.
- Add tests for configuration, edge cases, privacy, and output safety with every new
  behavior. Do not claim a pipeline run succeeded unless it actually ran.

## Legacy material

- Files under `archive/` are historical references, not active entrypoints.
- Do not edit or execute legacy scripts unless the user explicitly requests it.
- New generated artifacts belong under `output/<run-name>/`; complete engine evidence stays in `.audit/workflows/blast_kinetics/` inside that run.

## Documentation

- Keep README commands copy-pasteable from the repository root.
- When adding configuration fields, document their effect and update both sample
  profiles when applicable.
- Explain scientific assumptions plainly and avoid unsupported biological claims.

# Pseudonymised working inputs

This procedure creates analysis copies, not certified anonymous or public data.
Exact dates, approved study/sample/DNA/donor codes and clinical characteristics
remain. Protocol codes can contain initials. Keep these copies under controlled
access and review remaining identification risks before sharing any data image.

## Accepted local bundle

The November 16 copies are in `input/deidentified_20261116_ready/`. Its
`master.json` selects all five copies and retains the scientific settings of
`configs/pipeline_layers.json`. The default master now explicitly selects these
validated copies. No original input was overwritten or relocated.

```bash
python3 run.py --validate-only
python3 run.py
```

These commands run all four layers through the existing launcher and publish to a
fresh destination under `outputs/layered/`. As with ordinary runs, the assessment
time is current unless explicitly fixed in the selected master. The acceptance
comparison fixed it identically in both named profiles.

The original-source maintenance master is retained locally as
`input/private/deidentification_20261116_ready/original_master.json`; use it when
preparing new copies from authoritative originals. Reprocessing the default copies
would alias already pseudonymised count groups again and is not the maintenance
source selection. The bundle's `deidentification_report.json` records source/output hashes, counts,
formula-cache preservation and the distinction between package verification and
pipeline acceptance. The [acceptance record](history/deidentification_20261116.md)
owns the full-run comparison and limitations. The private surname mapping is
separate, in `input/private/deidentification_20261116_ready/`, and must never be
included in a container, shared export, log or Git commit. Both bundle and private
directory have owner-only access; original workbook permissions remain unchanged.

## Transformation contract

The approved field rules and scientific invariants are recorded once in
[the workflow contract](workflow_contracts.md#pseudonymised-working-inputs--november-16-2026).
No clinical exclusion, predictor, model, threshold, unit, missingness rule or
cross-source matching method was changed.

The maintenance helper patches XLSX ZIP/XML rather than importing/exporting or
recalculating the workbooks. This preserves saved formula results, formatting,
Excel extensions and source row coordinates. It converts used shared strings to
equivalent inline strings and empties the shared-string table, removing unused
identifiers too. It removes document properties, comments and their note drawings
and relationships. External links, embedded content and unsupported dependencies
are rejected for review. Known-name scanning covers all remaining XML parts but
does not establish that every indirect identifier or unknown name is absent.

## Repeating the procedure

Choose fresh Git-ignored destinations, separate from one another. The group map
is private data; reusing it preserves aliases across later copies without editing
the existing mapping. Omitting `--group-map` creates a new alias set.

```bash
conda run --no-capture-output -n pre_analysis python -B -m analysis.maintenance.deidentify_workbooks \
  --config input/private/deidentification_20261116_ready/original_master.json \
  --output-dir input/deidentified_next \
  --private-dir input/private/deidentification_next \
  --group-map input/private/deidentification_20261116_ready/retrospective_count_groups.json
```

Run integrated preflight and full original/copy comparisons before adopting a new
bundle. Match group membership, selected diagnosis samples, receipt/extraction
states, clinical values, missingness, results and figures. Permit only documented
identifier/provenance differences. Fresh directories are required; failures retain
their evidence and are never presented as accepted bundles. Do not run the
name/DOB-based patient-ID filling helper on these stripped working copies; any
future identity maintenance belongs on separately reviewed authoritative sources.

The helper prints counts and safe failure classes, never names or mapping values.
Its focused synthetic checks are:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/maintenance/test_deidentification.py
```

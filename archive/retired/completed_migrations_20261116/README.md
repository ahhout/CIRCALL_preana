# Completed migrations

These tools completed earlier source or execution migrations. They are preserved
for explicit reproduction, not routine pipeline preparation. No data or results
were moved into this bundle. The pre-change checkpoint was `e90445e`; `inventory.json`
maps original paths and hashes to the relocated files.

| Module below `analysis/` | Historical task |
| --- | --- |
| `workbook_harmonization` | Approved old-to-current headers/specimen labels; mapping retained under `configs/maintenance/` |
| `extraction_status` | Original explicit not-extracted column migration; the current pipeline ignores that legacy column |
| `patient_ids` | Name/DOB-based ID backfill on authoritative originals; unsuitable for stripped working copies |
| `migrate_retrospective_blasts` | Original retrospective count-source layout conversion |
| `historical_workbooks` | Package explicitly selected historical CSV outputs without new inference |
| `validation.validate_retirement` | Original before/after workflow-retirement acceptance check |

From the repository root, inspect a relocated command with the shared Conda
environment:

```bash
conda run -n pre_analysis python -m archive.retired.completed_migrations_20261116.analysis.patient_ids --help
```

Use the corresponding module name from the table for other commands. The normal
pipeline does not import these modules. No old-path forwarding scripts were kept.
Reproduction still requires explicitly selected sources and the recorded scientific
version; archiving is not approval to overwrite data or change identity rules.

The archived code uses current shared readers and maintenance XML primitives;
only imports, configuration/provenance locations and CLI labels were rebased.
Transformation logic was retained. For byte-exact earlier code, use the recorded
checkpoint and original hashes rather than treating relocated hashes as originals.
Historical commands in dated acceptance records retain their execution-time paths.

The preserved tests are opt-in; default pytest discovery excludes archives:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider archive/retired/completed_migrations_20261116/tests
```

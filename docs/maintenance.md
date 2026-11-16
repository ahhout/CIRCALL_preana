# Workbook maintenance

Normal analysis uses [the README run commands](../README.md#run). These tools are
explicit preparation steps; the pipeline never runs them automatically.

| Task | Current tool |
| --- | --- |
| Create pseudonymised copies | `analysis.maintenance.deidentify_workbooks`; see [working-input procedure](deidentification.md) |
| Trim approved text labels | `analysis.maintenance.workbook_cleanup` |
| Standardise approved missing/annotation markers | `analysis.maintenance.sample_annotations` |
| Repair reviewed existing inventory formulas | `analysis.maintenance.repair_inventory_formulas` |

Run them in the existing Conda environment, with explicit sources and fresh output
destinations. For the selected tool's arguments:

```bash
conda run -n pre_analysis python -m analysis.maintenance.workbook_cleanup --help
```

Preserve originals and review changes before adoption. Identity, merging, filtering
and scientific settings still follow the [contracts](workflow_contracts.md).
Current copies have no names/DOB for identity backfill; use the separately retained
authoritative-source profile when preparing future copies.

Completed header/ID/extraction migrations, retrospective source conversion,
historical CSV packaging and the original retirement check are in the
[archive index](../archive/README.md). Their old commands are historical;
there are no compatibility wrappers in the current interface.

# Retained compatibility interfaces

The target is one layered pipeline. These interfaces remain available during the
transition because removing them is a capability decision, not just file cleanup.
They are not selected by the layered master and must not become fallback paths
for a blocked layer. See [retirement coverage](../replacement_coverage.md).

| Interface | Authoritative configuration / instructions |
| --- | --- |
| Former combined default | [pipeline_all.json](../../configs/compatibility/pipeline_all.json) |
| Longitudinal DNA models/trends | [pipeline_longitudinal.json](../../configs/compatibility/pipeline_longitudinal.json), [sample-analysis guide](sample_analysis.md) |
| Older recorded counts and MRD | [pipeline_kinetics.json](../../configs/compatibility/pipeline_kinetics.json), [pipeline_mrd.json](../../configs/compatibility/pipeline_mrd.json) |
| Older diagnosis associations | [pipeline_cfdna_spearman.json](../../configs/compatibility/pipeline_cfdna_spearman.json), [association guide](cfdna_associations.md) |
| Optional normalized kinetics | [YAML profiles](../../configs/blast_kinetics/blast_kinetics.yml), [raw-measurement example](../../configs/blast_kinetics/raw_measurement_example.yml), [kinetics guide](blast_kinetics.md) |
| Older preparation metadata | [Extraction protocols](../../configs/sample_analysis/extraction_protocols.json), [association source pin](../../configs/source_catalog.json) |
| Statistical interpretation | [Compatibility questions](statistical_questions.md); these are not the current Layer 2/3 methods |

The five old root `configs/pipeline_*.json` names forward to the configurations
above. Their selections and source paths are unchanged. `source_catalog.json`
is used by the compatibility association interface, not the layered master.
Normalized kinetics and extraction protocols retain their existing separate
namespaces and paths for standalone commands and historical reproduction.

The retained packages are `analysis/sample_analysis`, `analysis/cfdna_associations`
and `analysis/blast_kinetics`. Shared `association_methods.py` belongs to both the
current and retained implementations. Do not move shared methods with an old
package. New layered functionality belongs in the four layer packages.

Before retirement, decide which older capabilities are still wanted: migrate only
those, and explicitly retire the rest. Verify current layered scientific tables,
figures, source selection, gates, failure handling and publication independently.
Existing inputs, outputs and provenance remain evidence even after an interface
is retired. Earlier `legacy`, `scripts` and `kinetics_pipeline` execution remains
retired; this reorganization does not restore it.

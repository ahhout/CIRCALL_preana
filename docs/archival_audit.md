# Archival candidates audit

October 7, 2026. The largest opportunity to reduce visible clutter is to archive
whole historical result bundles, followed by a small set of superseded helpers
and design material. The older scientific packages still provide explicitly
retained capabilities and compatibility entrypoints, so they are not ready for
wholesale archival. No files were moved, deleted, or overwritten by this audit.

## Completed archival on October 7

After reviewing this audit, the investigator instructed: keep all layered outputs
and archive historical `output/` contents. All 63 historical items now reside in
[the compatibility results archive](../archive/results/compatibility_20261007T073346593956Z/).
Every one of their 11,842 files was verified byte-for-byte, including native audit
evidence, failed attempts and caches. All 2,584 files under `outputs/` remain
unchanged. `output/` remains available for future explicit compatibility runs.

The superseded RETRO-code helper, temporary workbook helper, architecture proposal,
column crosswalk and draft field definitions are under
[the historical tooling bundle](../archive/retired/superseded_tools_20261007T073346593956Z/).
The complete original identity-test source is retained there. Only its two
superseded `IdentityTests` cases and their import were removed from active discovery;
current patient-ID and statistical tests remain. Original documentation bytes
are preserved in the pre-change snapshot; archived Markdown links were adjusted.

The [relocation record](../archive/migrations/archival_cleanup_20261007T073346593956Z/relocation.json)
maps every moved top-level item, and the adjacent file inventories record hashes
for all result files. Historic manifests, workbook provenance and recorded commands
retain original paths. To inspect or revalidate an old run, substitute its mapped
archive path explicitly; no implicit redirect or symlink was added. Use a fresh
destination outside the archive for any new validation report.

The candidate tables below describe the pre-move assessment; their clickable
links now point to archived items. The optional local cache utility and the
conditional second documentation batch were left in place. No layered output,
compatibility scientific package, active maintenance tool or clinical input was
removed, and no cache deletion or data deduplication was performed.

Post-move verification checked 9,942 artifacts in the 53 archived current indexes.
Two publication-mapping discrepancies in
`run_2026-10-01_14-20-31.113783_UTC` were already present before relocation; the
affected bytes and original metadata were preserved, not repaired. Four existing
Layer 1 historical links in `data_integrity.md` already pointed to absent paths;
they are unrelated to these moves and are recorded as unresolved references.
The active portable suite passed 390 tests and 81 subtests. Its count is two lower
because the superseded identity helper's tests were archived with their source.

The [complete inventory](../archive/audits/archival_candidates_20261007T071834121614Z/inventory.json)
records each output candidate's size, manifest statuses, artifact-index checks,
literal code/documentation references and selected evidence references. These
references are a lower bound: dynamic paths, notebooks outside the scanned tree
and external consumers may exist. Absence of a literal reference is not proof
that a run is disposable.

## Footprint and integrity

Sizes below are sums of file bytes, excluding filesystem allocation overhead.
Moving files into `archive/` on the same filesystem reduces visible clutter but
does not itself recover disk space.

| Area | Inventory | File bytes | Interpretation |
| --- | --- | --- | --- |
| `output/` | 51 directories and 12 loose files | 996.4 MiB | Historical compatibility runs, validations and audit tables. Strongest bulk archival candidate, subject to reference preservation and explicit working-result designation. |
| `outputs/layer*/` | 25 directories and 5 loose files | 142.5 MiB | Layer-specific runs and acceptance evidence. Some development/intermediate candidates exist; preserve explicitly named baselines. |
| Runtime caches inside these results | Included in the totals above | 41.6 MiB | Separate cleanup decision. Do not strip caches or alter run ownership records while performing an archival move. |
| `archive/` | Existing historical material | Not proposed for further cleanup | Retain migration snapshots, original sources, relocation records and failed-run evidence. |

All 78 current artifact indexes checked successfully: 12,480 indexed artifacts,
with no missing files or checksum mismatches. One additional index inside
`output/run_2026-10-01_14-20-31.113783_UTC/.audit/figure_edits/20261001T145745Z/`
is a historical edit snapshot. It is not a second current index to validate
against that snapshot directory. Preserve it with the run.

Not every directory has an artifact index. An unindexed directory needs a fresh
file inventory and hashes before relocation; an indexed directory still needs
unindexed files and historical edit snapshots included in the move manifest.

No `outputs/layered/` clinical run directory currently exists. The unified default
has synthetic acceptance evidence, but the audit cannot designate a completed
clinical combined run as a replacement for existing layer results.

## Script and documentation candidates

“Candidate” means suitable for a concrete archival proposal, not authorized for
removal. Historical execution should remain inactive after archival unless
explicitly requested.

| Candidate | Evidence | Readiness and required companion work |
| --- | --- | --- |
| [tmp/spreadsheets/revise_statistics.py](../archive/retired/superseded_tools_20261007T073346593956Z/tmp/spreadsheets/revise_statistics.py) | Standalone 205-line workbook revision helper with explicit source/destination arguments; no literal caller found in current code, tests, configs or documentation | Low-dependency candidate. Preserve the source and original path as historical tooling; confirm it is not still used manually. Do not infer that any workbook it revised is a duplicate. |
| [analysis/sample_statistics/identity.py](../archive/retired/superseded_tools_20261007T073346593956Z/analysis/sample_statistics/identity.py) | Its own header marks the RETRO-code proposal superseded by `analysis.patient_ids`. Current Layer 2 execution does not import it | Clear superseded implementation, but not ready to move alone: `tests/sample_statistics/test_statistics.py` imports it and contains `test_review_and_apply_preserve_sources` and `test_ambiguous_rows_require_explicit_mapping`. Separate/relocate the historical tests or preserve a reviewed compatibility shim, then rerun discovery. Keep the active `patient_ids.py` implementation. |
| [Historical architecture proposal](../archive/retired/superseded_tools_20261007T073346593956Z/docs/layered_architecture_proposal.md), [column crosswalk](../archive/retired/superseded_tools_20261007T073346593956Z/docs/cohort_column_mapping.md), and [draft field definitions](../archive/retired/superseded_tools_20261007T073346593956Z/configs/definitions/cohort_fields.proposed.json) | Explicitly historical/proposed material; the draft definitions have no runtime/test references found, and the documents cross-link to them | Archive as one design bundle, preserving relative links or replacing current references with archival links. Do not include the active `workbook_harmonization.json`, integrity rules or released layer definitions. |
| Root `codex-clean-cache` | Local editor/cache utility, unrelated to scientific execution | Optional relocation outside the scientific workspace or archival after owner review. No execution or cache clearing is part of this audit. |
| `docs/repository_cleanup.md` and `docs/layer4_implementation_plan.md` | Historical migration/design material, but actively linked by current guides/contracts | Conditional second batch. Preserve links and approval rationale; moving them provides organizational benefit, not retirement of their evidence. Keep current guides and scientific contracts accessible. |

The first three source/design groups total only about 150 KiB. Their value as
archival candidates is clearer ownership and reduced navigation clutter, not
meaningful disk recovery.

## Output archival batches

Archive complete run roots, including `.audit`, logs, settings, intermediate
artifacts, publication indexes and historical edits. Group related comparison
records with the runs they describe. Preserve source bytes and recorded statuses.

| Proposed batch | Exact scope or examples | Conditions |
| --- | --- | --- |
| Historical compatibility results | Contents of `output/`, retaining the directory as a destination for future explicit compatibility runs | Best bulk candidate: 996.4 MiB. Designate any working/reference runs to leave accessible first. Current docs link several validation bundles; update those links and record old-to-new paths. Keep loose validation JSONs and clinical audit CSVs with their related evidence. |
| Large validation bundles | `output/integrated_validation_20261001/` (117.5 MiB), `output/layout_validation_20261001T094022Z/` (106.0 MiB), `output/environment_cleanup_20261001T100451Z/` (28.7 MiB) | Good historical-bundle candidates, not expendable test debris. Preserve nested standalone/integrated runs and comparison records together. The layout/environment bundles have current documentation references. Sizes are subsets of the compatibility total. |
| Failed compatibility attempts | `output/full_canonical_panels_20261001/`, `output/statistical_simplification_20261001/`, `output/run_2026-10-01_11-03-55.205592_UTC/`, `output/run_2026-10-01_11-41-13.164299_UTC/` | Root manifests record failures while independent workflows completed. Archive as failed-attempt evidence; retain successful peer results and diagnostic logs. Do not relabel these as successful or discard them because later runs exist. |
| Earlier Layer 3 development/acceptance attempts | `outputs/layer3_advanced_analysis/acceptance_master_20261006/`, `run_20261006T102503Z_master/`, `run_20261006T102503Z_standalone/`, plus `validation_20261006T102503Z.json` | Candidates for a grouped historical move. Keep the explicitly documented final acceptance pair and the source-comparison reference listed below. No claim of numerical or whole-run duplication is made. |
| Later Layer 3 ad hoc runs | Under `outputs/layer3_advanced_analysis/`: `run_20261006T131001510695Z/`, `run_20261006T131734603911Z/`, `run_20261006T132432152893Z/`, `run_20261006T132632860232Z/` | Review required. They are complete, but no literal current code/documentation reference was found. A later timestamp does not establish which run is preferred or superseded. Designate the working result before moving them. |
| Layer 4 development/intermediate acceptance | Under `outputs/layer4_disease_modeling/`: `development_blocked_20261006/`, both `run_20261006T141611Z_*` runs, both `run_20261006T142050Z_*` runs, and their two matching validation JSONs | Good intermediate-evidence candidates once paired with the retained final acceptance record. The failed master statuses reflect the expected clinical quality hold, not proof of a software defect or disposable output. |
| Layer 1 and Layer 2 repeats | All three current Layer 1 run roots; the timestamped Layer 2 runs | Hold pending explicit baseline designation. Layer 1 is small; Layer 2 timing, source revisions and figure changes matter. Neither the newest timestamp nor absence of references establishes redundancy. |
| `output/spreadsheet/` | Loose historical workbook collection, about 1.7 MiB | Has a current documentation reference and no run manifest found. Inventory and identify its originating runs before moving; do not assume it duplicates newer statistics workbooks. |

The Layer 3/4 development, intermediate and ad hoc candidates listed above total
about 47.1 MiB, included in the 142.5 MiB layered total. That total is a review
queue, not a finding that every directory has been superseded.

## Evidence to keep accessible during the first pass

| Evidence | Why it remains accessible |
| --- | --- |
| Layer 3 `run_20261006T102847Z_standalone/`, `run_20261006T102847Z_master/`, `validation_20261006T102847Z.json` | Explicit final pair in [Layer 3 acceptance](layer3_validation_20261006.md). |
| Layer 3 `acceptance_standalone_20261006/` | Explicit source-hash comparison reference in that acceptance record. |
| Layer 4 `run_20261006T142704Z_standalone/`, `run_20261006T142704Z_master/`, `validation_20261006T142704Z.json` | Explicit final pair in [Layer 4 acceptance](layer4_validation_20261006.md), including the preserved CIRCALL hold. |
| Layer 2 `run_20261006T093742879752Z/`, `run_20261006_log_concentrations/`, `run_20261006_simple_subtitles/` | Referenced by the concentration-axis and subtitle migration verification records under `archive/migrations/`. These form change-comparison evidence. |
| Existing rollback snapshots and relocation records | Required to reconstruct the uncommitted repository migration and validate prior relocations. Git HEAD alone does not capture the current implementation. |

These are named evidence references, not a declaration that their scientific
results should be preferred over later runs. They can eventually live in a
historical results area if their references and validation tooling resolve the
relocation, but should not disappear during the first cleanup pass.

## Code that must remain available

Retain `analysis/sample_analysis/`, `analysis/cfdna_associations/` and
`analysis/blast_kinetics/`, their compatibility profiles, required tests and
validators. All four layers can execute without those scientific packages, but
the user explicitly chose to keep compatibility until longitudinal models,
bootstrap trends, handling correlations and combined yield/WBC presentations are
migrated and validated. Runtime independence of the layers does not retire those
capabilities. Normalized modeling also remains an explicit compatibility workflow.

Retain current maintenance tools: `patient_ids.py`, `repair_inventory_formulas.py`,
`workbook_cleanup.py`, `workbook_harmonization.py`, `extraction_status.py` and
`sample_analysis/migrate_retrospective_blasts.py`. They have documented operations,
tests or shared imports. In particular, formula repair and patient-ID maintenance
use workbook/XML helpers from the cleanup/extraction modules. Grouping maintained
tools into a clearer namespace is possible future layout work; archival would
remove supported functionality.

Retain shared reading, source-state, configuration, association methods,
orchestration, publication, provenance and figure-layout modules, all four layers,
active definitions, environment files and authoritative inputs. Do not restore
tracked-but-deleted earlier implementations just to create a cleaner Git status.

## Duplicate and relocation cautions

`output/cfdna_spearman_20261001_1533/` and
`output/full_canonical_panels_20261001/` have identical indexed published-file
sets. The latter also retains a failed canonical attempt. This is not whole-run
duplication, and deleting either based on visible figures would lose evidence.
Likewise, visible artifacts and their `.audit` native copies are intentional
publication/provenance pairs, not duplicate-cleanup targets.

Before any move, prepare an exact source/destination manifest covering all files,
including unindexed evidence. Review live documentation/configuration references
and metadata paths. Preserve immutable run manifests, workbook provenance and
hashes; use a relocation record and update consumers rather than rewriting old
scientific evidence. Verify destination bytes and publication pairs after moving.
Do not insert symlinks into indexed run trees, which have explicit symlink guards.

The proposed order is: review the small superseded tooling/design bundle; designate
working results; archive complete compatibility-result bundles; then review
intermediate layered runs. Actual relocation requires a separate, concrete approval
under the repository's data-safety rules. No deletion is proposed here.

## Audit scope and reproducibility

The [audit record](../archive/audits/archival_candidates_20261007T071834121614Z/audit.json)
records the scan command, Git state and matching pre-change implementation
checkpoint. The adjacent `audit_inventory.py` reads metadata and hashes, without
executing any scientific workflow or parsing clinical measurement rows. Source-path
values used to detect dependencies are omitted from the saved inventory.
Selected validation/relocation records were also checked for output references.
No software tests were rerun for this read-only audit, and hash consistency does
not establish scientific validity or clinical equivalence between runs.

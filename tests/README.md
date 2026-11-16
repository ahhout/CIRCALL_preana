# Tests and validation tools

Use the existing `pre_analysis` Conda environment. The portable suite collects
both pytest functions and unittest classes:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests
```

| Location | Responsibility |
| --- | --- |
| `data_integrity/`, `sample_statistics/`, `advanced_analysis/`, `disease_modeling/` | Current layers |
| `orchestration/` | Master configuration, execution, output ownership, gates and isolated layer dependencies |
| `maintenance/` | Reusable annotation, formula repair, cleanup and deidentification |
| `fixtures/` | Shared synthetic builders and frozen synthetic numerical references; never clinical workbooks |
| `validation/` | Retained result-validator tests and current layer command forwards |
| `analysis/validation/` | Actual result-validation command implementations; see the audit guide |

Import shared builders from `tests.fixtures`, not another `test_*.py` module.
Workflow-local fixtures may remain beside their suite when they have no cross-suite
consumer. Public execution acceptance uses complete four-layer profiles through the sole launcher in bootstrapped and activated environments.
`fixtures/execution.py` builds historical single-layer layouts solely for internal-engine
and reader tests; it is not an application interface. Older workflow suites are in the code-only retirement bundle; `pytest.ini` excludes
archives from active discovery. Their assertions do not substitute for the retained
scientific methods and frozen numerical references. Software checks and
synthetic output parity do not establish scientific validity of clinical results.

Completed migration tests moved with their tools to
`archive/retired/completed_migrations_20261116/tests/`. They are excluded from
normal discovery and can be checked explicitly:

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider archive/retired/completed_migrations_20261116/tests
```

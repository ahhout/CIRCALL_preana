# Single Conda-aware launcher — October 20, 2026

The investigator requested one launcher that enters Conda itself. `run.py` now
uses only the standard library before selecting the existing `pre_analysis`
environment. An already-correct interpreter is reused; labels from another
interpreter are insufficient. Conda discovery checks CONDA_EXE, PATH and standard
home installations in that order. No packages or environments are installed.

## Preservation and rollback

The pre-change dirty implementation is preserved in
`archive/migrations/conda_launcher_before_20261020/implementation/` with path/hash
inventory and original Git status. The snapshot excludes clinical data, outputs,
caches and credentials. Restore only reviewed affected files after checking the
inventory and preserving subsequent unrelated edits; never reset/clean the tree
or replace inputs/results.

The original shell wrapper is in the
[code-only archive](../../archive/retired/conda_launcher_20261020/README.md).
New execution no longer depends on it; historical records retain their original
commands and hashes. Environment definitions/lock and scientific options are unchanged.

## Verification

The [aggregate acceptance record](conda_launcher_20261020.json) records the checks.

```bash
conda run --no-capture-output -n pre_analysis python -B -m pytest -q -p no:cacheprovider tests/orchestration --tb=short
```

Result: **113 tests and 23 subtests passed**, with **zero warnings**, in 188.20 seconds.
Coverage includes configured/PATH/home Conda discovery, correct-interpreter reuse,
argument boundaries and paths with spaces, exit-status propagation, missing Conda,
launch failure and recursion prevention. Isolated successful and deliberately
blocked synthetic four-layer runs matched their already-activated counterparts in
native numerical reports and visible PNG hashes, with old scientific packages
physically absent. Publication, source-change, failure and interruption safeguards
also passed. New manifests hash `run.py` without requiring the archived shell file.

The first isolated test fixture incorrectly removed the active prefix while
retaining Conda's activation stack; that fixture was corrected to model a genuine
unactivated shell before the successful final test run.

A real check used `/usr/bin/python3` with only HOME, PATH=`/usr/bin:/bin` and
LANG=`C.UTF-8`, without activation, CONDA_EXE or Conda on PATH:

```bash
/usr/bin/python3 /home/arnohoutman/projects/pre_analysis/run.py --validate-only --output-dir /home/arnohoutman/projects/pre_analysis/outputs/conda_launcher_20261020/preflight_destination
```

It discovered the installed home-directory Conda, selected `pre_analysis` and
completed all four configured preflights with exit **0**. No result directory was
created. The exact command/environment/status and log are retained in
`outputs/conda_launcher_20261020/system_python_preflight.json` and its adjacent log.

All **150 snapshot files** and the archived shell hash matched their inventories.
The scientific master and environment YAML/Linux lock bytes are unchanged.
`git diff --check` passed. Active documentation file links resolve apart from
the two previously acknowledged missing historical acceptance JSON files.
Nothing was staged or committed.

This change reran the affected orchestration suite, not the entire scientific
suite. Synthetic equivalence and preflight do not establish clinical scientific
validity. No clinical full execution, environment creation or dependency change
was performed.

"""Synthetic integration checks; no clinical inputs are required."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run

spec = importlib.util.spec_from_file_location("workflow_paths", ROOT / "workflows/retrospective/workflow_paths.py")
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def workbook(self, name="synthetic.xlsx", columns=(), sheet="cohorte_lal"):
        book = Workbook()
        book.active.title = sheet
        if columns:
            book.active.append(list(columns))
            book.active.append(["synthetic"] * len(columns))
        path = self.base / name
        book.save(path)
        book.close()
        return path

    def test_bilan_requires_explicit_handoff(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run.arguments(["--stage", "bilan"])

    def test_invalid_sensitivity_options(self):
        for options in (["--mixed-outlier-drop-n", "-1"], ["--stage", "bilan", "--retrospective-workbook", "a.xlsx", "--mixed-outlier-drop-n", "1"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.arguments(options)

    def test_output_reuse_does_not_touch_existing_files(self):
        existing = self.base / "keep.txt"
        existing.write_text("unchanged")
        with self.assertRaises(ValueError):
            run.prepare_output(self.base)
        self.assertEqual(existing.read_text(), "unchanged")
        with self.assertRaises(ValueError):
            run.prepare_output(existing)

    def test_empty_output_allowed(self):
        run.prepare_output(self.base / "new")
        run.prepare_output(self.base / "new")

    def test_workbook_contract(self):
        path = self.workbook(columns=run.CIRCALL_COLUMNS)
        run.validate_workbook(path, sheet="cohorte_lal", columns=run.CIRCALL_COLUMNS)
        with self.assertRaisesRegex(ValueError, "Missing required sheet"):
            run.validate_workbook(path, sheet="Detailed")
        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            run.validate_workbook(path, sheet="cohorte_lal", columns={"absent"})

    def test_missing_invalid_empty_inputs(self):
        with self.assertRaisesRegex(ValueError, "Workbook not found"):
            run.validate_workbook(self.base / "missing.xlsx")
        invalid = self.base / "invalid.xlsx"
        invalid.write_text("not excel")
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            run.validate_workbook(invalid)
        with self.assertRaisesRegex(ValueError, "Empty worksheet"):
            run.validate_workbook(self.workbook())

    def test_failed_stage_records_exit_code(self):
        manifest = {"stages": []}
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "exit 7"):
            run.execute_stage("synthetic", [sys.executable, "-c", "raise SystemExit(7)"], [], output=self.base, manifest=manifest)
        saved = json.loads((self.base / "run_manifest.json").read_text())
        self.assertEqual(saved["stages"][0]["status"], "failed")
        self.assertEqual(saved["stages"][0]["returncode"], 7)

    def test_zero_exit_with_missing_artifact_is_failure(self):
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "required artifacts"):
            run.execute_stage("synthetic", [sys.executable, "-c", "pass"], [self.base / "missing.csv"], output=self.base, manifest={"stages": []})

    def test_commands_handoff_and_output_routing(self):
        args = run.arguments(["--output-dir", str(self.base / "run")])
        steps = list(run.workflow_steps(args))
        self.assertEqual([s[0] for s in steps], ["parse", "analysis", "report", "missing_samples", "csf", "dosage", "correlations"])
        for name, command, expected in steps:
            for path in expected:
                self.assertTrue(path.is_relative_to(args.output_dir))
            if name in ("dosage", "correlations"):
                index = command.index("--retrospective-workbook")
                self.assertEqual(Path(command[index + 1]), args.output_dir / "retrospective/results/cfdna_analysis.xlsx")
        args = run.arguments(["--stage", "bilan", "--retrospective-workbook", str(self.base / "supplied.xlsx")])
        steps = list(run.workflow_steps(args))
        self.assertEqual(len(steps), 4)
        for name, command, _ in steps:
            if name in ("dosage", "correlations"):
                self.assertEqual(command[command.index("--retrospective-workbook") + 1], str(self.base / "supplied.xlsx"))

    def test_sensitivity_count_reaches_analysis_report_and_artifact_checks(self):
        args = run.arguments(["--stage", "retrospective", "--mixed-outlier-drop-n", "1"])
        stages = {name: (command, expected) for name, command, expected in run.workflow_steps(args)}
        for stage in ("analysis", "report"):
            command, _ = stages[stage]
            self.assertEqual(command[command.index("--mixed_outlier_drop_n") + 1], "1")
        self.assertIn("cfDNA_mixedlm_outlier_drop1_contrasts_vs_base.csv", [path.name for path in stages["analysis"][1]])

    def test_pipeline_stops_after_failure(self):
        circall = self.workbook(columns=run.CIRCALL_COLUMNS)
        retrospective = self.workbook("synthetic_ret.xlsx", run.RETROSPECTIVE_COLUMNS, "Detailed")
        with patch.object(run, "execute_stage", side_effect=RuntimeError("synthetic failure")) as execute, redirect_stderr(io.StringIO()):
            result = run.main(["--stage", "bilan", "--circall", str(circall), "--retrospective-workbook", str(retrospective), "--output-dir", str(self.base / "out")])
        self.assertEqual(result, 1)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(json.loads((self.base / "out/run_manifest.json").read_text())["status"], "failed")

    def test_relative_paths_use_callers_directory(self):
        result = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import run; print(run.arguments(['--inventory', 'synthetic.xlsx']).inventory)", str(ROOT)], cwd=self.base, capture_output=True, text=True, check=True)
        self.assertEqual(Path(result.stdout.strip()), self.base / "synthetic.xlsx")
        self.assertEqual(run.arguments([]).donors, ROOT / "data/raw/retrospective/cfDNA_donors.xlsx")

    def test_legacy_output_root_redirects_defaults_and_keeps_overrides(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--test_outputs_dir", default="outputs")
        parser.add_argument("--plot", default="outputs/results/plot.jpeg")
        parser.add_argument("--out_excel", default="outputs/results/analysis.xlsx")
        parser.add_argument("--donors", default="donors.xlsx")
        custom = self.base / "explicit.xlsx"
        with patch.object(sys, "argv", ["analysis.py", "--test_outputs_dir", str(self.base / "run"), "--out_excel", str(custom)]):
            args = paths.parse_workflow_args(parser, inputs={"donors": "cfDNA_donors.xlsx"}, outputs=["plot", "out_excel"], root_flag="test_outputs_dir")
        self.assertEqual(Path(args.plot), self.base / "run/results/plot.jpeg")
        self.assertEqual(Path(args.out_excel), custom)
        self.assertEqual(Path(args.donors), ROOT / "data/raw/retrospective/cfDNA_donors.xlsx")

    def test_all_cli_help_from_another_directory(self):
        scripts = [ROOT / "run.py", *sorted((ROOT / "workflows").rglob("*.py"))]
        for script in scripts:
            if script.name in ("stats_reporting.py", "workflow_paths.py"):
                continue
            with self.subTest(script=script.name):
                result = subprocess.run([sys.executable, str(script), "--help"], cwd=self.base, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()

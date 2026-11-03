from __future__ import annotations

from tests.fixtures.associations import row, toy_cohort

import numpy as np
import pandas as pd
import pytest

from analysis.cfdna_associations.analyze_blast_cfdna import CohortConfig, PREDICTORS, PredictorConfig, fit_regression, prepare_analysis_data, prepare_cohort, validate_columns, write_outputs






def test_filtering_median_aggregation_and_percentage_conversion() -> None:
    data = pd.DataFrame(
        [
            row("Alpha", "Sang", "cfDNA", 0.10, 10),
            row("Alpha", "Sang", "cfDNA", 0.30, 30),
            row("Alpha", "Moelle", "MNC celDNA", 0.70),
            row("Alpha", "Moelle", "MNC celDNA", 0.90),
            row("Alpha", "Sang", "cfDNA", 0.99, 999, tube="EDTA"),
            row("Alpha", "Sang", "cfDNA", 0.99, 999, phase="TP1"),
            row("Beta", "Sang", "cfDNA", 0.05, 5),
            row("Beta", "Moelle", "MNC celDNA", 0.50),
        ]
    )

    cohort, counts = prepare_cohort(data, CohortConfig())

    assert len(cohort) == 2
    alpha = cohort.loc[cohort["cfdna_ng_per_ml"].eq(20)].iloc[0]
    assert alpha["peripheral_blast_percent"] == pytest.approx(20)
    assert alpha["tumor_fraction_percent"] == pytest.approx(80)
    assert alpha["blood_sample_ids"] == "Alpha_Sang_cfDNA"
    assert alpha["marrow_sample_ids"] == "Alpha_Moelle_MNC celDNA"
    assert counts["blood_candidate_rows"] == 3
    assert counts["analysis_patients"] == 2
    assert counts["blood_patients_with_repeated_rows"] == 1
    assert counts["marrow_patients_with_repeated_rows"] == 1


def test_missing_required_columns_fail_early() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        validate_columns(pd.DataFrame({"cytology": [0.5]}))


def test_cytospin_is_used_when_cytology_is_missing() -> None:
    data = pd.DataFrame(
        [
            row("Alpha", "Sang", "cfDNA", np.nan, 10, cytospin=0.25),
            row("Alpha", "Moelle", "MNC celDNA", np.nan, cytospin=0.80),
            row("Beta", "Sang", "cfDNA", 0.30, 20, cytospin=0.99),
            row("Beta", "Moelle", "MNC celDNA", 0.70, cytospin=0.95),
        ]
    )

    cohort, _ = prepare_cohort(data, CohortConfig())

    assert cohort["peripheral_blast_percent"].tolist() == pytest.approx([25, 30])
    assert cohort["tumor_fraction_percent"].tolist() == pytest.approx([80, 70])


def test_out_of_range_cytology_is_rejected() -> None:
    data = pd.DataFrame(
        [
            row("Alpha", "Sang", "cfDNA", 10, 10),
            row("Alpha", "Moelle", "MNC celDNA", 0.70),
        ]
    )
    with pytest.raises(ValueError, match="fractions between 0 and 1"):
        prepare_cohort(data, CohortConfig())


def test_log10_cfdna_is_used_not_natural_log() -> None:
    cohort = toy_cohort()
    predictor = PredictorConfig(
        "age_diag", "Age at diagnosis", "continuous", "cfDNA_age_diag"
    )

    analysis = prepare_analysis_data(cohort, predictor)

    assert analysis["log10_cfDNA"].to_numpy() == pytest.approx(
        np.log10(analysis["cfdna_ng_per_ml"].to_numpy())
    )
    assert not np.allclose(
        analysis["log10_cfDNA"].to_numpy(),
        np.log(analysis["cfdna_ng_per_ml"].to_numpy()),
    )


def test_nonpositive_cfdna_causes_clear_error() -> None:
    cohort = toy_cohort()
    cohort.loc[0, "cfdna_ng_per_ml"] = 0
    predictor = PredictorConfig(
        "age_diag", "Age at diagnosis", "continuous", "cfDNA_age_diag"
    )

    with pytest.raises(ValueError, match="non-positive cfDNA"):
        prepare_analysis_data(cohort, predictor)


def test_continuous_regression_results_include_requested_model_statistics() -> None:
    predictor = PredictorConfig(
        "age_diag", "Age at diagnosis", "continuous", "cfDNA_age_diag"
    )
    analysis = prepare_analysis_data(toy_cohort(), predictor)

    model, results = fit_regression(analysis, predictor)

    assert model is not None
    assert results["formula"].iat[0] == "log10_cfDNA ~ age_diag"
    for column in [
        "n",
        "coefficient",
        "std_error",
        "t_statistic",
        "p_value",
        "f_statistic",
        "f_p_value",
        "multiple_r_squared",
        "adjusted_r_squared",
        "aic",
        "bic",
        "df_resid",
    ]:
        assert column in results.columns


def test_categorical_regression_uses_formula_c_and_reports_group_contrasts() -> None:
    predictor = PredictorConfig("sex", "Sex", "categorical", "cfDNA_sex")
    analysis = prepare_analysis_data(toy_cohort(), predictor)

    model, results = fit_regression(analysis, predictor)

    assert model is not None
    assert results["formula"].iat[0] == "log10_cfDNA ~ C(sex)"
    assert any(results["term"].str.startswith("C(sex)"))


def test_default_outputs_only_selected_regression_and_descriptions(tmp_path):
    output = tmp_path / 'results'
    cohort = toy_cohort()
    cohort['cfdna_ng_per_ml'] *= np.exp(np.random.default_rng(7).normal(0, .15, len(cohort)))
    write_outputs(output, cohort, {'analysis_patients': 12})
    assert {p.name for p in output.iterdir() if p.is_dir()} == {p.output_name for p in PREDICTORS}
    for predictor in PREDICTORS:
        target = output/predictor.output_name
        assert (target/predictor.figure_name).exists()
        if predictor.variable != 'peripheral_blast_percent':
            descriptive = pd.read_csv(target/'descriptive_summary.csv')
            assert not any('p_value' in c or 'p_adj' in c for c in descriptive.columns)
            assert not (target/'results.csv').exists()
    folder = output / 'cfDNA_vs_peripheral_blood_blast_percent'
    result = pd.read_csv(folder/'results.csv')
    assert result.term.tolist() == ['peripheral_blast_percent']
    assert result.predictor_increment.iat[0] == 10
    assert result.p_adj_bh.iat[0] == pytest.approx(result.p_value.iat[0])
    assert result.fold_change.iat[0] == pytest.approx(10 ** (10 * result.coefficient.iat[0]))
    assert result.ci95_low_fc.iat[0] < result.fold_change.iat[0] < result.ci95_high_fc.iat[0]
    descriptions = pd.read_csv(output/'predictor_descriptions.csv')
    assert set(descriptions.predictor) == {p.variable for p in PREDICTORS}
    written = pd.read_csv(folder/'analysis_data.csv')
    assert not {'lastname', 'firstname', 'dob', 'patient_key'} & set(written.columns)
    assert (folder/'log10_cfDNA_ng_per_mL_vs_peripheral_blood_blast_percent.png').exists()


def test_diagnostics_are_descriptive_not_another_test_family(tmp_path):
    output = tmp_path/'results'
    write_outputs(output, toy_cohort(), {})
    folder = output/'cfDNA_vs_peripheral_blood_blast_percent'/'assumptions'
    diagnostics = pd.read_csv(folder/'diagnostics.csv')
    assert {'max_leverage', 'max_cooks_distance', 'df_resid'} <= set(diagnostics.columns)
    assert 'p_value' not in diagnostics
    assert not (folder/'assumptions.csv').exists()
    for name in ('residuals_vs_fitted.png', 'qq_plot.png', 'scale_location.png'):
        assert (folder/name).exists()


def test_explicit_predictors_share_one_corrected_family_and_hc3(tmp_path):
    from statsmodels.stats.multitest import multipletests
    output = tmp_path/'results'
    names = ['age_diag', 'peripheral_blast_percent', 'gb_per_l', 'sex']
    write_outputs(output, toy_cohort(), {}, predictors=names)
    tables = [pd.read_csv(output/p.output_name/'results.csv') for p in PREDICTORS if p.variable in names]
    assert all(len(t) == 1 for t in tables)
    actual = [t.p_adj_bh.iat[0] for t in tables]
    expected = multipletests([t.p_value.iat[0] for t in tables], method='fdr_bh')[1]
    assert actual == pytest.approx(expected)
    for table in tables:
        if table.predictor.iat[0] != 'sex':
            assert table.standard_error_type.iat[0] == 'HC3 robust'
        else:
            assert table.term.iat[0] == 'overall predictor'
            assert pd.isna(table.coefficient.iat[0])


def test_unavailable_selected_predictor_stays_in_correction_family(tmp_path):
    cohort = toy_cohort()
    cohort['age_diag'] = np.nan
    output = tmp_path/'results'
    write_outputs(output, cohort, {}, predictors=['peripheral_blast_percent', 'age_diag'])
    fitted = pd.read_csv(output/'cfDNA_vs_peripheral_blood_blast_percent/results.csv').iloc[0]
    skipped = pd.read_csv(output/'cfDNA_age_diag/results.csv').iloc[0]
    assert skipped.status == 'skipped'
    assert pd.isna(skipped.p_adj_bh)
    assert fitted.p_adj_bh == pytest.approx(min(1, 2*fitted.p_value))


def test_low_information_predictor_writes_skipped_status() -> None:
    predictor = PredictorConfig("sex", "Sex", "categorical", "cfDNA_sex")
    cohort = toy_cohort()
    cohort["sex"] = "F"
    analysis = prepare_analysis_data(cohort, predictor)

    model, results = fit_regression(analysis, predictor)

    assert model is None
    assert results["status"].iat[0] == "skipped"
    assert "fewer than 2" in results["reason"].iat[0]


def test_spearman_ties_and_log_invariance():
    from scipy.stats import spearmanr
    from analysis.cfdna_associations.analyze_blast_cfdna import spearman_sensitivity
    predictor = next(p for p in PREDICTORS if p.variable == 'peripheral_blast_percent')
    cohort = toy_cohort()
    cohort['peripheral_blast_percent'] = [0, 0, 5, 5, 10, 10, 20, 30, 40, 50, 60, 60]
    cohort['cfdna_ng_per_ml'] = [1, 4, 2, 2, 8, 5, 7, 9, 3, 12, 11, 6]
    analysis = prepare_analysis_data(cohort, predictor)
    result = spearman_sensitivity(analysis, predictor)
    expected = spearmanr(cohort.peripheral_blast_percent, cohort.cfdna_ng_per_ml)
    assert result['spearman_n'] == 12
    assert result['spearman_rho'] == pytest.approx(expected.statistic)
    assert result['spearman_p_value'] == pytest.approx(expected.pvalue)
    analysis['log10_cfDNA'] = 1.
    assert spearman_sensitivity(analysis, predictor)['spearman_status'] == 'unavailable'
    assert spearman_sensitivity(analysis.iloc[:2], predictor)['spearman_status'] == 'unavailable'


def test_spearman_does_not_change_primary_or_descriptive_scope(tmp_path):
    enabled, disabled = tmp_path/'enabled', tmp_path/'disabled'
    write_outputs(enabled, toy_cohort(), {})
    write_outputs(disabled, toy_cohort(), {}, spearman_enabled=False)
    relative = 'cfDNA_vs_peripheral_blood_blast_percent/results.csv'
    a, b = pd.read_csv(enabled/relative), pd.read_csv(disabled/relative)
    pd.testing.assert_frame_equal(a[b.columns], b)
    assert a.spearman_status.iat[0] == 'computed'
    pooled = tmp_path/'pooled'
    write_outputs(pooled, toy_cohort(), {}, descriptive_only=True)
    assert not list(pooled.rglob('results.csv'))
    summary = pd.read_csv(pooled/'cfDNA_vs_peripheral_blood_blast_percent/descriptive_summary.csv')
    assert not any('p_value' in c for c in summary.columns)

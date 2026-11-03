"""Frozen pre-extraction numerical results, independent of compatibility execution."""
from dataclasses import asdict
import json

import numpy as np
import pandas as pd
import pytest

from analysis import association_methods as methods
from analysis.provenance import ROOT

REFERENCE = json.loads((ROOT/'tests/fixtures/synthetic_association_methods_reference.json').read_text())


@pytest.mark.parametrize('case', REFERENCE['cases'], ids=lambda c: c['name'])
def test_methods_match_frozen_reference(case):
    predictor = methods.select_predictors([case['predictor']])[0]
    data = methods.prepare_analysis_data(pd.DataFrame(case['input']), predictor)
    model, table = methods.fit_regression(data, predictor)
    # JSON encodes unavailable numeric values as null, including all-null columns.
    expected = pd.DataFrame(**case['table']).astype(table.dtypes)
    pd.testing.assert_frame_equal(table, expected, check_dtype=False, rtol=1e-10, atol=1e-12)
    if 'predictions' in case:
        assert model is not None
        np.testing.assert_allclose(model.fittedvalues, case['predictions'], rtol=1e-10, atol=1e-12)
        pd.testing.assert_frame_equal(methods.model_diagnostics(model), pd.DataFrame(**case['diagnostics']),
                                      check_dtype=False, rtol=1e-10, atol=1e-12)
    else:
        assert model is None
    if 'spearman' in case:
        actual = methods.spearman_sensitivity(data, predictor)
        for key, expected in case['spearman'].items():
            if expected is None:
                assert np.isnan(actual[key])
            elif isinstance(expected, (float, int)):
                assert actual[key] == pytest.approx(expected, rel=1e-10, abs=1e-12)
            else:
                assert actual[key] == expected


def test_predictor_configuration_matches_frozen_reference():
    assert [asdict(p) for p in methods.PREDICTORS] == REFERENCE['predictors']

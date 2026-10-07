from analysis.blast_kinetics.config import load_config
from analysis.blast_kinetics.data_io import load_input
from analysis.blast_kinetics.preprocessing import prepare_data
from analysis.blast_kinetics.statistics import fit_time_model


def test_current_workbook_reproduces_validated_blast_cohort(blast_config):
    prepared = prepare_data(load_input(blast_config), blast_config)

    assert prepared.summary["analysis_rows"] == 108
    assert prepared.summary["analysis_subjects"] == 25
    assert prepared.summary["subjects_by_group"] == {
        "DUX4-r": 2,
        "ETV6::RUNX1": 8,
        "Hyperdiploidy": 3,
        "KMT2A-r": 3,
        "PAX5alt": 1,
        "T-Other": 6,
        "TCF3::PBX1": 2,
    }


def test_current_workbook_model_converges(blast_config):
    prepared = prepare_data(load_input(blast_config), blast_config)

    trend = fit_time_model(prepared.frame, blast_config)

    assert trend.result.converged
    assert trend.result.params["time_centered"] < 0


def test_second_profile_analyzes_another_measurement_without_code_changes():
    config = load_config("configs/blast_kinetics/raw_measurement_example.yml").data

    prepared = prepare_data(load_input(config), config)

    assert prepared.summary["analysis_rows"] == 148
    assert prepared.summary["analysis_subjects"] == 32

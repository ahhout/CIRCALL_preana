"""Synthetic association tables; no clinical sources."""
import numpy as np
import pandas as pd

def row(
    patient: str,
    tissue: str,
    nucleic_acid: str,
    cytology: object,
    yield_value: object = np.nan,
    cytospin: object = np.nan,
    sex: object = "M",
    age_diag: object = 5,
    genetic_subtype: object = "Subtype A",
    gb_per_l: object = 10,
    phase: str = "diag",
    tube: str = "Roche",
) -> dict[str, object]:
    return {
        "lastname": patient,
        "firstname": "Test",
        "dob": "2010-01-01",
        "sample_id": f"{patient}_{tissue}_{nucleic_acid}",
        "treatment_phase": phase,
        "tissue": tissue,
        "tube": tube,
        "nucleic_acid": nucleic_acid,
        "cytology": cytology,
        "cytospin_%": cytospin,
        "sex": sex,
        "age_diag": age_diag,
        "genetic_subtype": genetic_subtype,
        "GB_per_L": gb_per_l,
        "cfDNA_ng_per_mL_plasma": yield_value,
    }


def toy_cohort(n: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observation": np.arange(1, n + 1),
            "blood_sample_ids": [f"B{i}" for i in range(1, n + 1)],
            "marrow_sample_ids": [f"M{i}" for i in range(1, n + 1)],
            "cfdna_ng_per_ml": np.power(10.0, 1 + np.arange(n) * 0.03),
            "sex": ["F", "M"] * (n // 2),
            "age_diag": np.linspace(2, 16, n),
            "genetic_subtype": ["A", "B", "C"] * (n // 3),
            "peripheral_blast_percent": np.linspace(1, 90, n),
            "gb_per_l": np.linspace(2, 120, n),
            "tumor_fraction_percent": np.linspace(15, 95, n),
            "blood_row_count": 1,
            "marrow_row_count": 1,
        }
    )



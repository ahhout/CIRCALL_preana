from copy import deepcopy
from pathlib import Path

import pytest

from analysis.blast_kinetics.config import load_config


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def blast_config():
    return load_config(ROOT / "configs" / "blast_kinetics" / "blast_kinetics.yml").data


@pytest.fixture
def configurable(blast_config):
    def factory(**updates):
        config = deepcopy(blast_config)
        for dotted_key, value in updates.items():
            target = config
            parts = dotted_key.split("__")
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return config

    return factory

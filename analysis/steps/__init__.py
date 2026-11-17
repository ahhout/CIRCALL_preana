"""Ordered internal layer coordinators."""
from importlib import import_module

MODULES = {
    'data_integrity': 'step_01_data_integrity',
    'sample_statistics': 'step_02_sample_statistics',
    'advanced_analysis': 'step_03_advanced_analysis',
    'disease_modeling': 'step_04_disease_modeling',
}


def stage(name):
    return import_module(f"{__name__}.{MODULES[name]}")

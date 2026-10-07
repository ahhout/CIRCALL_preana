"""Dependency-free configuration parsing helpers."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Configuration contains duplicate keys')
        result[key] = value
    return result

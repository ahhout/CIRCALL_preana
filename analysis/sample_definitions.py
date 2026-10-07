"""Shared investigator-approved sample annotations; no identifier values exported."""


def extraction_state(dna_id, missing_tokens, unknown_tokens=()):
    """An actual recorded DNA ID establishes extraction; an empty ID means no.

    A missing column, formula ID or Excel error cannot establish either state.
    Legacy missing/unknown annotations are accepted without inventing an ID.
    """
    if dna_id is None or dna_id.formula or dna_id.data_type == 'e' or dna_id.cached_type == 'e':
        return 'unavailable'
    token = '' if dna_id.value is None else str(dna_id.value).strip().casefold()
    return 'no' if token in set(missing_tokens) | set(unknown_tokens) | {''} else 'yes'

"""Select and save disease figure families without exporting clinical rows."""
from pathlib import Path

from .counts import count_figure
from .mrd import mrd_figure
from .mrd_status import mrd_status_figure
from .saving import save


def figures(destination, scope, prepared, result, args, d):
    destination = Path(destination)
    fig = mrd_figure(prepared['mrd'], scope, args, d)
    if fig is not None:
        save(fig, destination/'mrd'/'mrd_trajectories', pdf_output=getattr(args, 'pdf_output', True))
    if scope == 'pooled':
        if prepared['mrd']:
            save(mrd_status_figure(result['tables']['MRD'], d), destination/'mrd'/'mrd_status', pdf_output=getattr(args, 'pdf_output', True))
        return
    for measurement in d['counts'][scope]['sheets']:
        for early in (False, True):
            fig = count_figure(prepared['counts'], measurement, args, d, early=early)
            if fig is not None:
                save(fig, destination/'blood_counts'/f'{measurement}_{"early_window" if early else "full_range"}', pdf_output=getattr(args, 'pdf_output', True))


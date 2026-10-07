"""Selected inventory sources and immutable source-state checks for Layers 1–3."""
from pathlib import Path

from analysis.provenance import digest


def sources(args):
    selected={}
    if args.cohort in ('all','retrospective'):selected['retrospective']=args.inventory
    if args.cohort in ('all','circall'):selected['circall']=args.circall
    return selected

def capture_sources(args):
    inputs={'rules':args.rules}
    states={}
    selected=sources(args)
    if args.include_controls and 'retrospective' in selected and getattr(args,'donors',None) is not None:
        selected['retrospective_controls']=args.donors
    for cohort,path in selected.items():
        try:
            hashed=digest(path)
            states[cohort]={'path':str(path),'sha256':hashed,'availability':'readable'}
            inputs[cohort]=path
        except OSError:
            states[cohort]={'path':str(path),'sha256':None,'availability':'unavailable'}
    return inputs,states

def verify_source_states(states):
    for record in states.values():
        try:current=digest(Path(record['path']))
        except OSError:current=None
        if current!=record['sha256']:
            raise ValueError('An integrity source changed during the run')

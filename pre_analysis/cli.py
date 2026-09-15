"""Public runner interface with explicit canonical and preserved legacy modes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def arguments(argv=None):
    parser=argparse.ArgumentParser(description='Pre-analysis: shared cohort analyses or preserved legacy workflows')
    parser.add_argument('--workflow',choices=['canonical','legacy'],default='canonical')
    parser.add_argument('--cohort',choices=['all','retrospective','circall'])
    parser.add_argument('--analysis',choices=['all','inventory','volumes','yield','longitudinal'])
    parser.add_argument('--stage',choices=['all','retrospective','bilan'],help='Legacy mode only')
    for flag in ('inventory','donors','circall','retrospective-workbook','output-dir'):
        parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--mixed-random-slope-sensitivity',action='store_true')
    parser.add_argument('--mixed-outlier-drop-n',type=int,default=0)
    args=parser.parse_args(argv)
    if args.mixed_outlier_drop_n<0:parser.error('--mixed-outlier-drop-n must be nonnegative')
    if args.workflow=='canonical':
        if args.stage is not None or args.retrospective_workbook is not None:
            parser.error('--stage and --retrospective-workbook require --workflow legacy')
        args.cohort=args.cohort or 'all';args.analysis=args.analysis or 'all'
        if args.analysis not in ('all','longitudinal') and (args.mixed_random_slope_sensitivity or args.mixed_outlier_drop_n):
            parser.error('Sensitivity options require --analysis all or longitudinal')
        args.inventory=args.inventory or ROOT/'cfDNA_inventaire_retrospective.xlsx'
        args.circall=args.circall or ROOT/'inventaire_CIRCALL_15092026.xlsx'
        args.donors=args.donors or ROOT/'data/retrospective/cfDNA_donors.xlsx'
        args.output_dir=args.output_dir or ROOT/'outputs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    elif args.cohort is not None or args.analysis is not None:
        parser.error('--cohort and --analysis require --workflow canonical')
    for name,value in vars(args).items():
        if isinstance(value,Path):setattr(args,name,value.expanduser().resolve())
    return args


def main(argv=None):
    args=arguments(argv)
    if args.workflow=='canonical':
        from .canonical import run
        return run(args)
    from . import legacy
    options=[]
    for name in ('stage','inventory','donors','circall','retrospective_workbook','output_dir'):
        value=getattr(args,name)
        if value is not None:options.extend(['--'+name.replace('_','-'),str(value)])
    if args.mixed_random_slope_sensitivity:options.append('--mixed-random-slope-sensitivity')
    options.extend(['--mixed-outlier-drop-n',str(args.mixed_outlier_drop_n)])
    return legacy.main(options)

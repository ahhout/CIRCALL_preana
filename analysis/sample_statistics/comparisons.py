"""Participant-level cohort/pooled comparisons; exports contain aggregates only."""
from collections import defaultdict
from itertools import combinations
import hashlib
import math
from types import SimpleNamespace

import numpy as np
from scipy.stats import mannwhitneyu, permutation_test, rankdata, PermutationMethod
from statsmodels.stats.multitest import multipletests


def significance(p):
    if p is None:
        return 'NA'
    return next((label for cutoff,label in [(1e-4,'****'),(1e-3,'***'),(1e-2,'**'),(.05,'*')]
                 if p < cutoff), 'ns')


def signed_rank_permutation(differences, settings, seed):
    """Vectorized Wilcoxon sign flips; wilcox zeros excluded, tied ranks averaged."""
    nonzero=np.asarray([v for v in differences if v!=0],dtype=float)
    if len(nonzero)<2:
        return SimpleNamespace(statistic=0.,pvalue=1.),2**len(nonzero)
    ranks=rankdata(np.abs(nonzero),method='average')
    signed=ranks*np.sign(nonzero)
    def positive_rank_sum(values,axis):
        return np.maximum(values,0).sum(axis=axis)
    result=permutation_test((signed,),positive_rank_sum,permutation_type='samples',vectorized=True,
                            alternative=settings['alternative'],n_resamples=settings['resamples'],
                            batch=settings['batch'],rng=np.random.default_rng(seed))
    positive=float(positive_rank_sum(signed,axis=0))
    return SimpleNamespace(statistic=min(positive,float(ranks.sum())-positive),pvalue=float(result.pvalue)),2**len(nonzero)


def compare(rows, d, cohort):
    """Controls vs selected visits, then all prespecified paired visit contrasts."""
    settings=d['inference']
    output=[]
    for field in settings['metrics']:
        definition=d['metrics'][field]
        if cohort in definition.get('exclude_cohorts',[]):
            continue
        for specimen in definition['specimens']:
            observations=defaultdict(list)
            for row in rows:
                if (cohort!='pooled' and row['cohort']!=cohort) or row['specimen']!=specimen or row['receipt'] not in ('received','received_early'):
                    continue
                if row['cohort'] in definition.get('exclude_cohorts',[]):
                    continue
                visit='control' if row['control'] else row['visit']
                if visit not in ['control',*settings['visits']]:
                    continue
                value=row['measurements'][field]['value']
                if value is None:
                    continue
                if not math.isfinite(value) or value<0:
                    raise ValueError('Invalid comparison measurement')
                observations[(visit,(row['cohort'],row['subject_key']))].append(value)
            medians=defaultdict(dict)
            for (visit,subject), values in observations.items():
                medians[visit][subject]=float(np.median(values))
            planned=[('control',visit,'independent') for visit in settings['control_visits']]
            planned += [(a,b,'paired') for a,b in combinations(settings['visits'],2)]
            family=[]
            for first,second,kind in planned:
                left,right=medians[first],medians[second]
                matched=sorted(left.keys() & right.keys()) if kind=='paired' else []
                x=sorted(left.values()) if kind=='independent' else [left[k] for k in matched]
                y=sorted(right.values()) if kind=='independent' else [right[k] for k in matched]
                record=dict(cohort=cohort,field=field,specimen=specimen,visit_1=first,visit_2=second,
                            test='Mann–Whitney U' if kind=='independent' else 'Wilcoxon signed-rank',
                            kind=kind,alternative=settings['alternative'],observation_unit='participant median per visit',
                            n_1=len(x),n_2=len(y),paired_n=len(matched) if kind=='paired' else None,
                            available_n_1=len(left),available_n_2=len(right),
                            median_1=float(np.median(x)) if x else None,median_2=float(np.median(y)) if y else None,
                            zero_differences=None,statistic=None,p_value=None,p_adjusted=None,
                            correction=settings['correction'],family_size=len(planned),
                            status='unavailable',reason='No matched patients' if kind=='paired' else 'Missing comparison group',
                            p_method=None,permutation_seed=None,display=kind=='independent')
                minimum=settings['minimum_group_n'] if kind=='independent' else settings['minimum_paired_n']
                if x and y and (len(x)<minimum or len(y)<minimum):
                    record['reason']=f'Requires at least {minimum} participants per group' if kind=='independent' else f'Requires at least {minimum} matched pairs'
                if len(x)>=minimum and len(y)>=minimum:
                    key=f'{cohort}/{field}/{specimen}/{first}/{second}/{settings["seed"]}'
                    seed=int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],'big')
                    method=PermutationMethod(n_resamples=settings['resamples'],batch=settings['batch'],rng=np.random.default_rng(seed))
                    if kind=='independent':
                        result=mannwhitneyu(x,y,alternative=settings['alternative'],method=method)
                        total=math.comb(len(x)+len(y),len(x))
                    else:
                        differences=sorted(left[k]-right[k] for k in matched)
                        record['zero_differences']=sum(v==0 for v in differences)
                        result,total=signed_rank_permutation(differences,settings,seed) if any(differences) else (None,1)
                    record.update(statistic=float(result.statistic) if result is not None else 0.,
                                  p_value=float(result.pvalue) if result is not None else 1.,
                                  status='computed',reason='All paired differences are zero' if kind=='paired' and not any(differences) else '',
                                  p_method='all differences zero' if result is None else 'exact permutation' if total<=settings['resamples'] else 'Monte Carlo permutation',
                                  permutation_seed=seed)
                family.append(record)
            adjusted=multipletests([r['p_value'] if r['p_value'] is not None else 1. for r in family],method=settings['correction'])[1]
            for record,p in zip(family,adjusted,strict=True):
                if record['p_value'] is not None:
                    record['p_adjusted']=float(p)
                record['significance']=significance(record['p_adjusted'])
            output.extend(family)
    return output

"""Bound long-song evidence without silently claiming complete prompt coverage."""
import json

def bound_evidence(evidence,budget):
    if len(json.dumps(evidence))<=budget: return evidence
    def trim(value,items,chars):
        if isinstance(value,str):
            if len(value)<=chars: return value
            lines=value.splitlines()
            if len(lines)>1:
                selected=lines if len(lines)<=items else [lines[round(i*(len(lines)-1)/(items-1))] for i in range(items)]
                per=max(1,chars//len(selected)-15)
                return '\n'.join(line[:per] for line in selected)+' [selected excerpts]'
            return value[:chars]+' [excerpt]'
        if isinstance(value,list):
            selected=value if len(value)<=items else [value[round(i*(len(value)-1)/(items-1))] for i in range(items)]
            return [trim(v,items,chars) for v in selected]
        if isinstance(value,dict): return {k:trim(v,items,chars) for k,v in value.items()}
        return value
    for items,chars in ((12,2000),(8,900),(4,400),(2,100)):
        result=trim(evidence,items,chars)
        result['evidence_scope']='A bounded selection of the supplied long-song evidence. Omitted detail is not evidence of absence; do not invent missing sections or lyrics.'
        if len(json.dumps(result))<=budget: return result
    raise ValueError('Artist direction and exclusions leave insufficient space for musical evidence; shorten those text fields')

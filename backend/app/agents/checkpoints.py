"""Small application-managed node checkpoints, matching the existing commerce workflow."""
class PlanningInterrupted(Exception):
    pass


def checkpoint_node(name,fn,save=None):
    def run(state):
        if name in state.get('completed',[]):return {}
        changes=fn(state)
        changes['completed']=state.get('completed',[])+[name]
        if save:save({**state,**changes})
        return changes
    return run


def rediscover_after_interruption(state,parse_name,validate_name):
    # Retain interpretation only. Current catalog/stock must be read again before
    # issuing another recommendation; no checkout/payment operation is replayed.
    completed=[name for name in [parse_name,validate_name] if name in state.get('completed',[])]
    result={'text':state.get('text',''),'completed':completed,'steps':state.get('steps',[])[:len(completed)],'status':'VALID'}
    if state.get('intent'):result['intent']=state['intent']
    return result

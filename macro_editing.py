"""Pure action-list history and multi-selection operations."""
from copy import deepcopy
from macro_flow import CONTROL

class ActionHistory:
    def __init__(self, limit=60):
        if limit < 1: raise ValueError("History limit must be positive.")
        self.limit, self.past, self.future = limit, [], []

    @property
    def can_undo(self): return bool(self.past)

    @property
    def can_redo(self): return bool(self.future)

    def record(self, actions):
        self.past.append(deepcopy(list(actions)))
        if len(self.past)>self.limit: del self.past[0]
        self.future.clear()

    def undo(self, actions):
        if not self.past: return None
        self.future.append(deepcopy(list(actions)))
        return self.past.pop()

    def redo(self, actions):
        if not self.future: return None
        self.past.append(deepcopy(list(actions)))
        return self.future.pop()

def _indices(actions, indices):
    ids=sorted(set(indices))
    if not ids or ids[0]<0 or ids[-1]>=len(actions):
        raise ValueError("Select at least one valid action.")
    return ids

def move_selected(actions, indices, direction):
    ids=_indices(actions, indices)
    if direction not in (-1,1): raise ValueError("Direction must be -1 or 1.")
    selected=set(ids)
    result=list(actions)
    for i in (ids if direction==-1 else reversed(ids)):
        neighbor=i+direction
        if 0<=neighbor<len(result) and neighbor not in selected:
            result[i],result[neighbor]=result[neighbor],result[i]
            selected.remove(i)
            selected.add(neighbor)
    return result,sorted(selected)

def duplicate_selected(actions, indices):
    ids=_indices(actions, indices)
    if any(actions[i].kind in CONTROL for i in ids):
        raise ValueError("Duplicate only executable actions, not control markers.")
    result=list(actions)
    copies=[deepcopy(actions[i]) for i in ids]
    at=ids[-1]+1
    result[at:at]=copies
    return result,list(range(at,at+len(copies)))

def delete_selected(actions,indices):
    ids=_indices(actions,indices)
    excluded=set(ids)
    result=[a for i,a in enumerate(actions) if i not in excluded]
    return result,([min(ids[0],len(result)-1)] if result else [])

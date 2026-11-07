"""Tree representation of the existing flat JSON actions.

UI grouping is a view only: file format and playback still use Action lists.
Never persist a new workflow format. The flatten operation validates all markers.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from copy import deepcopy

from macro_model import Action, validate_action
from macro_flow import OPENERS, CONTROL, validate_flow

@dataclass
class WorkflowNode:
    action: Action
    children: List["WorkflowNode"] = field(default_factory=list)
    otherwise: Optional[List["WorkflowNode"]] = None
    else_marker: Optional[Action] = None
    end_marker: Optional[Action] = None

    @property
    def is_group(self):
        return self.action.kind in OPENERS


def from_actions(actions):
    """Convert valid, flat marker-based actions into structured nodes."""
    validate_flow(actions)
    position = 0

    def parse(until=()):
        nonlocal position
        result = []
        while position < len(actions) and actions[position].kind not in until:
            action = deepcopy(actions[position])
            position += 1
            if action.kind not in OPENERS:
                if action.kind in CONTROL:
                    raise ValueError("Unexpected standalone control marker.")
                result.append(WorkflowNode(action))
                continue
            marker = OPENERS[action.kind]
            if action.kind == "if_start":
                yes = parse(("else", "if_end"))
                otherwise = None
                else_action = None
                if position < len(actions) and actions[position].kind == "else":
                    else_action = deepcopy(actions[position])
                    position += 1
                    otherwise = parse(("if_end",))
                ending = deepcopy(actions[position])
                position += 1
                result.append(WorkflowNode(action, yes, otherwise, else_action, ending))
            else:
                children = parse((marker,))
                ending = deepcopy(actions[position])
                position += 1
                result.append(WorkflowNode(action, children, end_marker=ending))
        return result

    tree = parse()
    if position != len(actions):
        raise ValueError("Unconsumed workflow markers.")
    return tree


def to_actions(nodes):
    """Flatten and validate an editor tree without changing JSON semantics."""
    result = []

    def emit(items):
        for node in items:
            result.append(deepcopy(node.action))
            if node.is_group:
                if not node.children:
                    raise ValueError("A workflow block must contain at least one action.")
                emit(node.children)
                if node.action.kind == "if_start" and node.otherwise:
                    result.append(deepcopy(node.else_marker or Action(kind="else")))
                    emit(node.otherwise)
                result.append(deepcopy(node.end_marker or
                                       Action(kind=OPENERS[node.action.kind])))
            elif node.children or node.otherwise is not None:
                raise ValueError("Actions cannot contain nested items.")

    emit(nodes)
    for a in result:
        validate_action(vars(a))
    validate_flow(result)
    return result


def default_node(kind):
    """Create a usable workflow block, or a valid non-visual leaf."""
    if kind in OPENERS:
        if kind == "watch_start":
            action = Action(kind=kind, region_x=0, region_y=0,
                            region_w=200, region_h=100, poll_interval=0.5,
                            watch_max_changes=0)
            return WorkflowNode(action, [WorkflowNode(Action(kind="wait", seconds=0.5))],
                                end_marker=Action(kind="watch_end"))
        kwargs = {"condition_source": "pixel", "pixel_color": "#00FF00"}
        action = (Action(kind=kind, repeats=5) if kind == "loop_start" else
                  Action(kind=kind, repeats=5, **kwargs) if kind == "until_start" else
                  Action(kind=kind, **kwargs))
        return WorkflowNode(action, [WorkflowNode(Action(kind="wait", seconds=0.5))],
                            otherwise=[] if kind == "if_start" else None,
                            end_marker=Action(kind=OPENERS[kind]))
    if kind in ("click", "move", "drag"):
        return WorkflowNode(Action(kind=kind, x=0, y=0,
                                   **({"to_x": 0, "to_y": 0} if kind == "drag" else {})))
    if kind in ("if_end", "loop_end", "else", "until_end", "watch_end"):
        raise ValueError("Add the whole workflow block, not an individual marker.")
    if kind == "click_image":
        # A path is selected interactively before this action is inserted.
        return WorkflowNode(Action(kind=kind, image_path=""))
    if kind == "wait_until":
        return WorkflowNode(Action(kind=kind, condition_source="pixel"))
    if kind in ("key_down", "key_up"):
        return WorkflowNode(Action(kind=kind, keys="shift"))
    if kind == "clipboard_set":
        return WorkflowNode(Action(kind=kind, clipboard_text=""))
    return WorkflowNode(Action(kind=kind))

"""Structured, lazy execution for visual conditions and repeat blocks.

A Repeat Until block runs its body, then checks the condition. Its maximum
cycle count is mandatory, preventing an unbounded unattended loop.
"""
from macro_model import loop_spans

OPENERS = {"loop_start": "loop_end", "if_start": "if_end",
           "until_start": "until_end"}
CLOSERS = {v: k for k, v in OPENERS.items()}
CONTROL = frozenset((*OPENERS, *CLOSERS, "else"))
SMART = frozenset(("click_image", "wait_until", "if_start", "else",
                   "if_end", "until_start", "until_end"))


def has_smart_actions(actions):
    return any(action.kind in SMART for action in actions)


def validate_flow(actions):
    """Check marker placement and return end/else lookups."""
    loop_spans(actions)  # Preserve existing restriction on nested fixed loops.
    stack = []
    ends, alternatives, else_ends = {}, {}, {}
    for i, a in enumerate(actions):
        if a.kind in OPENERS:
            stack.append((a.kind, i, None))
        elif a.kind == "else":
            if not stack or stack[-1][0] != "if_start":
                raise ValueError(f"Else at action {i + 1} needs an open If.")
            kind, start, prior = stack.pop()
            if prior is not None:
                raise ValueError(f"Duplicate Else for If at action {start + 1}.")
            if i == start + 1:
                raise ValueError(f"If at action {start + 1} has an empty Then branch.")
            alternatives[start] = i
            stack.append((kind, start, i))
        elif a.kind in CLOSERS:
            if not stack or stack[-1][0] != CLOSERS[a.kind]:
                raise ValueError(f"Unexpected {a.kind} at action {i + 1}.")
            _, start, alt = stack.pop()
            if i == (alt if alt is not None else start) + 1:
                raise ValueError(f"Empty block at action {start + 1}.")
            ends[start] = i
            if alt is not None:
                else_ends[alt] = i
    if stack:
        raise ValueError(f"Unclosed block at action {stack[-1][1] + 1}.")
    return ends, alternatives, else_ends


def validate_start_selection(actions, start_index):
    if not 0 <= start_index < len(actions):
        raise ValueError("Selected action is out of range.")
    ends, _, _ = validate_flow(actions)
    for start, end in ends.items():
        if start < start_index <= end:
            raise ValueError(
                "Run from Selected cannot start inside a control block; "
                "select its opening marker or an action outside it."
            )


def iter_flow_steps(actions, check, stopped, start_index=0):
    """Yield (list_index, action), evaluating conditions using check(action)."""
    validate_start_selection(actions, start_index)
    ends, alternatives, else_ends = validate_flow(actions)
    pc = start_index
    frames = []  # [kind, opening index, completed/active cycles]
    while pc < len(actions):
        if stopped():
            raise RuntimeError("Stopped")
        action = actions[pc]
        kind = action.kind
        if kind in ("loop_start", "until_start"):
            frames.append([kind, pc, 1])
            pc += 1
        elif kind == "loop_end":
            frame = frames[-1]
            start = actions[frame[1]]
            if frame[2] < start.repeats:
                frame[2] += 1
                pc = frame[1] + 1
            else:
                frames.pop()
                pc += 1
        elif kind == "until_end":
            frame = frames[-1]
            start = actions[frame[1]]
            if check(start):
                frames.pop()
                pc += 1
            elif frame[2] >= start.repeats:
                raise TimeoutError(
                    f"Repeat Until at action {frame[1] + 1} did not match "
                    f"within {start.repeats} cycles."
                )
            else:
                frame[2] += 1
                pc = frame[1] + 1
        elif kind == "if_start":
            if check(action):
                pc += 1
            else:
                pc = alternatives[pc] + 1 if pc in alternatives else ends[pc] + 1
        elif kind == "else":
            pc = else_ends[pc] + 1
        elif kind == "if_end":
            pc += 1
        else:
            if action.enabled:
                for _ in range(action.repeats):
                    if stopped():
                        raise RuntimeError("Stopped")
                    yield pc, action
            pc += 1

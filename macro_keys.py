"""Explicit keyboard recording and safe held-key tracking."""
from macro_model import Action

MODIFIERS=frozenset(("ctrl","shift","alt","win"))
ALIASES={
 "control":"ctrl","control_l":"ctrl","control_r":"ctrl",
 "ctrl_l":"ctrl","ctrl_r":"ctrl","shift_l":"shift","shift_r":"shift",
 "alt_l":"alt","alt_r":"alt","alt_gr":"alt","cmd":"win",
 "cmd_l":"win","cmd_r":"win","super":"win","escape":"esc",
 "return":"enter","page_up":"pgup","page_down":"pgdn"
}
SPECIAL=frozenset(("enter","esc","tab","space","backspace","delete","insert",
 "home","end","up","down","left","right","pgup","pgdn","capslock",
 "numlock","printscreen","ctrl","shift","alt","win"))

def valid_hold_key(name):
    if not isinstance(name,str) or not name or name!=name.strip():
        return False
    name=name.lower()
    return name in SPECIAL or (len(name)==1 and name.isascii() and name.isalnum()) or (
        name.startswith("f") and name[1:].isdigit() and 1<=int(name[1:])<=24)

def normalize_event_key(key):
    name=getattr(key,"name",None)
    if name is not None:
        name=ALIASES.get(name.lower(),name.lower())
        return name if valid_hold_key(name) else None
    char=getattr(key,"char",None)
    if isinstance(char,str) and len(char)==1:
        if char==" ": return "space"
        if char in ("\r","\n"): return "enter"
        if char=="\t": return "tab"
        if char.isascii() and char.isprintable():
            return char.lower()
        if 1<=ord(char)<=26: return chr(ord("a")+ord(char)-1)
    vk=getattr(key,"vk",None)
    if isinstance(vk,int) and 65<=vk<=90: return chr(vk).lower()
    return None

class KeyboardRecorder:
    def __init__(self): self.pressed=set()
    def press(self,name):
        if name is None or name in self.pressed: return None
        self.pressed.add(name)
        if name in MODIFIERS: return Action(kind="key_down",keys=name)
        return Action(kind="key",keys=name,key_mode="press")
    def release(self,name):
        if name is None or name not in self.pressed: return None
        self.pressed.remove(name)
        return Action(kind="key_up",keys=name) if name in MODIFIERS else None
    def finish(self):
        result=[Action(kind="key_up",keys=k) for k in sorted(self.pressed & MODIFIERS)]
        self.pressed.clear()
        return result

class HeldKeys:
    def __init__(self,key_down,key_up):
        self.down,self.up=key_down,key_up
        self.held=[]
    def press(self,name):
        if name not in self.held:
            self.held.append(name)
            self.down(name)
    def release(self,name):
        if name not in self.held:
            raise ValueError(f"Key {name!r} was not held by this macro.")
        self.up(name)
        self.held.remove(name)
    def release_all(self):
        errors=[]
        for name in reversed(self.held[:]):
            try:
                self.up(name)
                self.held.remove(name)
            except Exception as exc:
                errors.append((name,exc))
        return errors

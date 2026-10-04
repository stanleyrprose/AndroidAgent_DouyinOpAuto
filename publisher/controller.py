#!/usr/bin/env python3
import base64
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .state import detect_state
except ImportError:
    # Preserve direct script imports from publisher/.
    from state import detect_state

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / "bridge" / "androidctl.sh"
ROOT_EXEC = ROOT / "bridge" / "root-exec.sh"
RUNTIME = Path("/opt/y700/runtime")
UI_XML = RUNTIME / "publisher-ui.xml"
TIKTOK = "com.zhiliaoapp.musically"
ADB_IME = "com.android.adbkeyboard/.AdbIME"
PREVIOUS_IME = RUNTIME / "state" / "previous-ime.txt"

class UIError(RuntimeError):
    pass

def run(*args, check=True, capture=True):
    p=subprocess.run(
        [str(x) for x in args],
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and p.returncode != 0:
        raise UIError(f"command failed rc={p.returncode}: {' '.join(map(str,args))}\n{p.stderr or ''}")
    return p

def androidctl(*args, check=True):
    return run(CTL, *args, check=check)

def root_exec(command, check=True):
    return run(ROOT_EXEC, command, check=check)

def dump_ui():
    androidctl("dump-ui", UI_XML.name)
    return UI_XML

def current_state():
    return detect_state(dump_ui())

def fast_state(timeout_seconds=2):
    host="/data/local/y700-agent/runtime/publisher-ui.xml"
    p=root_exec(
        f"rm -f {host}; toybox timeout {int(timeout_seconds)} uiautomator dump {host} >/dev/null 2>&1; test -s {host}",
        check=False,
    )
    if p.returncode != 0 or not UI_XML.exists():
        return None
    return detect_state(UI_XML)

def current_activity():
    p=androidctl("activity", check=False)
    return (p.stdout or "") + (p.stderr or "")

def tiktok_foreground():
    return TIKTOK in current_activity()

def _center(bounds):
    m=re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1,y1,x2,y2=map(int,m.groups())
    return (x1+x2)//2,(y1+y2)//2

def _bounds(bounds):
    m=re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    return tuple(map(int,m.groups())) if m else None

def _idmatch(actual, wanted):
    return actual == wanted or actual.endswith("/"+wanted)

def find_node(xml_path, *, rid=None, text=None, desc=None, clickable=None):
    root=ET.parse(xml_path).getroot()
    for node in root.iter("node"):
        if rid is not None and not _idmatch(node.attrib.get("resource-id") or "", rid):
            continue
        if text is not None and (node.attrib.get("text") or "") != text:
            continue
        if desc is not None and (node.attrib.get("content-desc") or "") != desc:
            continue
        if clickable is not None and node.attrib.get("clickable") != ("true" if clickable else "false"):
            continue
        c=_center(node.attrib.get("bounds",""))
        if c:
            return c,node.attrib
    return None,None

def wait_node(timeout=10, **selector):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        xml=dump_ui()
        c,attrs=find_node(xml,**selector)
        if c:
            return c,attrs
        last=current_state()
        time.sleep(0.7)
    raise UIError(f"timeout waiting node={selector}, last_state={last}")

def tap_node(timeout=8, **selector):
    c,attrs=wait_node(timeout=timeout,**selector)
    androidctl("tap",str(c[0]),str(c[1]))
    return attrs

def wait_state(states, timeout=18, require_tiktok=False):
    states={states} if isinstance(states,str) else set(states)
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        last=current_state()
        if last["state"]=="KEYGUARD":
            androidctl("wake",check=False)
            androidctl("unlock",check=False)
            time.sleep(0.5)
            continue
        if last["state"]=="SMS_PROMPT":
            # This is a dismissible TikTok marketing modal. BACK is more
            # reliable than tapping its animated close target and cannot opt in.
            androidctl("back",check=False)
            time.sleep(0.7)
            continue
        if last["state"] in states:
            if require_tiktok and not last.get("tiktok_visible",False):
                raise UIError(f"state matched but TikTok UI is not visible: {last}; activity={current_activity()}")
            return last
        time.sleep(0.8)
    raise UIError(f"timeout waiting for {sorted(states)}, last={last}, activity={current_activity()}")

def reset_app():
    # Dismiss any launcher/system overlay left from a failed prior run.
    androidctl("back", check=False)
    root_exec(f"am force-stop {TIKTOK}")
    time.sleep(1)
    androidctl("wake")
    androidctl("unlock")
    androidctl("launch",TIKTOK)
    time.sleep(3)

    # A cold TikTok HOME autoplays video. On this ZUI/Android 16 build that
    # can prevent UiAutomator from reaching idle. Probe first: static dialogs
    # are dumpable and therefore never receive the fallback tap. Only when the
    # fast probe times out do we pause the center of the feed.
    probe=fast_state(2)
    if probe is None:
        root_exec("input tap 952 1500",check=False)
        time.sleep(0.7)

    return wait_state({"HOME","CREATE","GALLERY","EDIT","POST_CONFIG"}, timeout=20, require_tiktok=True)

def settle_transients(timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        st=current_state()
        if st["state"]=="KEYGUARD":
            androidctl("wake",check=False)
            androidctl("unlock",check=False)
            time.sleep(0.5)
            continue
        if st["state"]=="SMS_PROMPT":
            xml=dump_ui()
            c,_=find_node(xml,rid="e62",clickable=True)
            if c:
                androidctl("tap",str(c[0]),str(c[1]))
            time.sleep(0.5)
            continue
        return st
    raise UIError("transient UI did not settle")

def go_to_gallery(reset=False):
    st=reset_app() if reset else settle_transients()
    if st["state"]=="UNKNOWN" or not tiktok_foreground():
        st=reset_app()

    if st["state"]=="HOME":
        xml=dump_ui()
        c,_=find_node(xml,rid="o70",clickable=True)
        if c:
            androidctl("tap",str(c[0]),str(c[1]))
        # The page may already advance between state read and node lookup.
        st=wait_state({"CREATE","GALLERY","PERMISSION"}, timeout=20, require_tiktok=True)

    if st["state"]=="CREATE":
        xml=dump_ui()
        c,_=find_node(xml,rid="upload_hot_area",clickable=True)
        if c:
            androidctl("tap",str(c[0]),str(c[1]))
        st=wait_state({"GALLERY","PERMISSION"}, timeout=20, require_tiktok=True)

    if st["state"]=="PERMISSION":
        raise UIError("TikTok media permission prompt is blocking gallery")
    if st["state"] not in {"GALLERY","EDIT","POST_CONFIG"}:
        raise UIError(f"cannot reach gallery from state={st}")
    return st

def select_album(name="Y700Agent", reset=False):
    st=go_to_gallery(reset=reset)
    if st["state"] in {"EDIT","POST_CONFIG"}:
        return st
    xml=dump_ui()
    _,title_attrs=find_node(xml,rid="tv_title")
    if title_attrs and (title_attrs.get("text") or "") == name:
        return st
    tap_node(rid="dqr", clickable=True)
    c,_=wait_node(text=name, timeout=12)
    androidctl("tap",str(c[0]),str(c[1]))
    time.sleep(1)
    st=wait_state("GALLERY", timeout=12, require_tiktok=True)
    xml=dump_ui()
    _,title_attrs=find_node(xml,rid="tv_title")
    if not title_attrs or (title_attrs.get("text") or "") != name:
        raise UIError(f"album selection did not stick: wanted={name}")
    return st

def select_first_media(album="Y700Agent", reset=False):
    st=select_album(album, reset=reset)
    if st["state"]=="EDIT":
        return st
    if st["state"]=="POST_CONFIG":
        return st
    xml=dump_ui()
    root=ET.parse(xml).getroot()
    grid_bounds=None
    for node in root.iter("node"):
        if _idmatch(node.attrib.get("resource-id") or "","jc5"):
            grid_bounds=_bounds(node.attrib.get("bounds",""))
            break
    if not grid_bounds:
        raise UIError("gallery grid not found")
    gx1,gy1,gx2,gy2=grid_bounds
    candidates=[]
    for node in root.iter("node"):
        if node.attrib.get("clickable")!="true":
            continue
        b=_bounds(node.attrib.get("bounds",""))
        if not b: continue
        x1,y1,x2,y2=b
        if x1>=gx1 and y1>=gy1 and x2<=gx2 and y2<=gy2 and (x2-x1)>100 and (y2-y1)>100:
            candidates.append((y1,x1,b))
    if not candidates:
        raise UIError("no selectable media found")
    _,_,b=sorted(candidates)[0]
    c=_center(f"[{b[0]},{b[1]}][{b[2]},{b[3]}]")
    androidctl("tap",str(c[0]),str(c[1]))
    return wait_state("EDIT", timeout=25, require_tiktok=True)

def go_to_post_config(album="Y700Agent", reset=False):
    st=settle_transients()
    if reset or st["state"]=="UNKNOWN" or not tiktok_foreground():
        st=select_first_media(album, reset=True)
    elif st["state"] not in {"EDIT","POST_CONFIG"}:
        st=select_first_media(album)
    if st["state"]=="POST_CONFIG":
        return st
    tap_node(rid="pje", clickable=True)
    return wait_state("POST_CONFIG", timeout=35, require_tiktok=True)

def _first_edit_text(xml_path):
    root=ET.parse(xml_path).getroot()
    for node in root.iter("node"):
        if node.attrib.get("class")=="android.widget.EditText":
            c=_center(node.attrib.get("bounds",""))
            if c:
                return c,node.attrib
    return None,None

def _edit_text_by_id(xml_path,rid):
    root=ET.parse(xml_path).getroot()
    for node in root.iter("node"):
        if not _idmatch(node.attrib.get("resource-id") or "",rid):
            continue
        if node.attrib.get("class")!="android.widget.EditText":
            continue
        c=_center(node.attrib.get("bounds",""))
        if c:
            return c,node.attrib
    return None,None

def begin_automation_ime():
    current=root_exec("settings get secure default_input_method").stdout.strip()
    PREVIOUS_IME.parent.mkdir(parents=True,exist_ok=True)
    if current and current!="null" and current!=ADB_IME and not PREVIOUS_IME.exists():
        PREVIOUS_IME.write_text(current+"\n",encoding="utf-8")
    if current != ADB_IME:
        root_exec(f"ime enable {ADB_IME} >/dev/null")
        root_exec(f"ime set {ADB_IME} >/dev/null")
        time.sleep(0.5)
    return current

def restore_input_method():
    if not PREVIOUS_IME.exists():
        return ""
    previous=PREVIOUS_IME.read_text(encoding="utf-8").strip()
    if previous and previous!="null":
        root_exec(f"ime set {shlex.quote(previous)} >/dev/null",check=False)
    PREVIOUS_IME.unlink(missing_ok=True)
    return previous

def _set_unicode_field(rid,text):
    st=current_state()
    if st["state"]!="POST_CONFIG":
        st=go_to_post_config(reset=False)

    # Switch IME before focusing the field. This TikTok build can drop focus
    # when the active IME changes.
    begin_automation_ime()
    time.sleep(0.5)
    st=current_state()
    if st["state"]!="POST_CONFIG" or not tiktok_foreground():
        st=go_to_post_config(reset=False)

    xml=dump_ui()
    c,attrs=_edit_text_by_id(xml,rid)
    if not c:
        raise UIError(f"EditText not found: {rid}")
    androidctl("tap",str(c[0]),str(c[1]))
    b64=base64.b64encode(text.encode("utf-8")).decode("ascii")
    root_exec("am broadcast -a ADB_CLEAR_TEXT >/dev/null",check=False)
    root_exec(f"am broadcast -a ADB_INPUT_B64 --es msg {shlex.quote(b64)} >/dev/null")
    time.sleep(1)
    xml=dump_ui()
    _,attrs=_edit_text_by_id(xml,rid)
    actual=(attrs or {}).get("text","")
    if actual != text:
        raise UIError(f"text verification failed rid={rid}: expected={text!r} actual={actual!r}")
    return text

def set_caption(text):
    # caption.txt maps to TikTok's detailed-description field.
    # Keep the automation IME until the publish session is committed or aborted;
    # restoring the normal IME mid-flow makes this TikTok build leave POST_CONFIG.
    return _set_unicode_field("h00",text)

def set_title(text):
    # Some TikTok layouts expose a separate title field (h04), while others
    # expose only the detailed-description field (h00). Treat title as optional.
    st=current_state()
    if st["state"]!="POST_CONFIG":
        st=go_to_post_config(reset=False)
    xml=dump_ui()
    c,_=_edit_text_by_id(xml,"h04")
    if not c:
        return {"status":"SKIPPED","reason":"title_field_not_present"}
    _set_unicode_field("h04",text)
    return {"status":"SET","text":text}

def _visibility_desc(xml_path):
    root=ET.parse(xml_path).getroot()
    for node in root.iter("node"):
        if not _idmatch(node.attrib.get("resource-id") or "","doy"):
            continue
        desc=(node.attrib.get("content-desc") or "").strip()
        if desc and desc!="更多选项":
            return desc
    return ""

def set_visibility(mode="PUBLIC"):
    labels={
        "PUBLIC":"所有人",
        "FRIENDS":"好友",
        "PRIVATE":"仅自己",
    }
    if mode not in labels:
        raise UIError(f"unsupported visibility: {mode}")
    st=current_state()
    if st["state"]!="POST_CONFIG":
        st=go_to_post_config(reset=False)
    xml=dump_ui()
    current=_visibility_desc(xml)
    if mode=="PRIVATE" and "只有你自己" in current:
        return current
    if mode=="PUBLIC" and ("所有人可见" in current or current=="所有人"):
        return current
    if mode=="FRIENDS" and "好友" in current:
        return current

    # Open the visibility row. This TikTok build reuses 'doy' for both
    # visibility and '更多选项', so use content-desc to distinguish them.
    root=ET.parse(xml).getroot()
    clicked=False
    for node in root.iter("node"):
        if not _idmatch(node.attrib.get("resource-id") or "","doy"):
            continue
        desc=(node.attrib.get("content-desc") or "").strip()
        if not desc or desc=="更多选项" or node.attrib.get("clickable")!="true":
            continue
        c=_center(node.attrib.get("bounds",""))
        androidctl("tap",str(c[0]),str(c[1]))
        clicked=True
        break
    if not clicked:
        raise UIError("visibility row not found")

    wait_state("VISIBILITY", timeout=12, require_tiktok=True)
    tap_node(desc=labels[mode], clickable=True)
    wait_state("POST_CONFIG", timeout=12, require_tiktok=True)
    actual=_visibility_desc(dump_ui())
    checks={
        "PRIVATE": lambda x: "只有你自己" in x,
        "PUBLIC": lambda x: "所有人" in x,
        "FRIENDS": lambda x: "好友" in x,
    }
    if not checks[mode](actual):
        raise UIError(f"visibility verification failed: mode={mode} actual={actual!r}")
    return actual

def tap_publish():
    st=current_state()
    if st["state"]!="POST_CONFIG":
        raise UIError(f"publish commit requires POST_CONFIG, got {st}")
    tap_node(rid="st6", clickable=True)

if __name__=="__main__":
    print(go_to_post_config(reset=True))

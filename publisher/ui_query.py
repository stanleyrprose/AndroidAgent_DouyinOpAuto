#!/usr/bin/env python3
import argparse,re,xml.etree.ElementTree as ET

def parse_bounds(s):
    m=re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",s or "")
    if not m: return None
    return tuple(map(int,m.groups()))

def center(b):
    x1,y1,x2,y2=b
    return (x1+x2)//2,(y1+y2)//2

ap=argparse.ArgumentParser()
ap.add_argument("xml")
g=ap.add_mutually_exclusive_group(required=True)
g.add_argument("--id")
g.add_argument("--text")
g.add_argument("--desc")
g.add_argument("--first-clickable-in-id")
args=ap.parse_args()
root=ET.parse(args.xml).getroot()
nodes=list(root.iter("node"))

def idmatch(rid,needle):
    return rid==needle or rid.endswith("/"+needle)

if args.first_clickable_in_id:
    containers=[]
    for n in nodes:
        if idmatch((n.attrib.get("resource-id") or ""),args.first_clickable_in_id):
            b=parse_bounds(n.attrib.get("bounds"))
            if b: containers.append(b)
    for cb in containers:
        cx1,cy1,cx2,cy2=cb
        for n in nodes:
            if n.attrib.get("clickable")!="true": continue
            b=parse_bounds(n.attrib.get("bounds"))
            if not b: continue
            x1,y1,x2,y2=b
            if x1>=cx1 and y1>=cy1 and x2<=cx2 and y2<=cy2 and (x2-x1)>100 and (y2-y1)>100:
                x,y=center(b); print(x,y); raise SystemExit(0)
    raise SystemExit(2)

for n in nodes:
    rid=(n.attrib.get("resource-id") or "")
    txt=(n.attrib.get("text") or "")
    desc=(n.attrib.get("content-desc") or "")
    ok=(args.id and idmatch(rid,args.id)) or (args.text is not None and txt==args.text) or (args.desc is not None and desc==args.desc)
    if ok:
        b=parse_bounds(n.attrib.get("bounds"))
        if b:
            x,y=center(b); print(x,y); raise SystemExit(0)
raise SystemExit(2)

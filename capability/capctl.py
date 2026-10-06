#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from .catalog import CatalogError,load_catalog,resolve
from .runtime import CapabilityError,admit,verify_contract,_job_dir
def main():
    ap=argparse.ArgumentParser(prog="capctl"); sp=ap.add_subparsers(dest="cmd",required=True)
    sp.add_parser("list"); p=sp.add_parser("describe"); p.add_argument("capability"); p.add_argument("--version")
    p=sp.add_parser("invoke"); p.add_argument("capability"); p.add_argument("--request",required=True)
    p=sp.add_parser("status"); p.add_argument("job_id")
    args=ap.parse_args()
    try:
        if args.cmd=="list": out={"capabilities":list(load_catalog().values())}
        elif args.cmd=="describe":
            rows=load_catalog(); row=rows.get(args.capability)
            if not row: raise CatalogError("CAPABILITY_NOT_FOUND")
            if args.version and row["version"]!=args.version: raise CatalogError("CAPABILITY_VERSION_MISMATCH")
            out=row
        elif args.cmd=="invoke":
            req=json.loads(Path(args.request).read_text(encoding="utf-8"))
            if req.get("capability")!=args.capability: raise CapabilityError("REQUEST_CAPABILITY_MISMATCH")
            out=admit(req)
        else:
            verify_contract(args.job_id); d=_job_dir(args.job_id)
            out={"capability_job_id":args.job_id,"state":json.loads((d/"state.json").read_text()),"backend":json.loads((d/"backend.json").read_text()) if (d/"backend.json").exists() else None}
        print(json.dumps(out,ensure_ascii=False,indent=2)); return 0
    except (CapabilityError,CatalogError,OSError,ValueError) as exc:
        print(json.dumps({"status":"BLOCKED","error":{"code":str(exc),"message":str(exc)}},ensure_ascii=False)); return 2
if __name__=="__main__": raise SystemExit(main())

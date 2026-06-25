#!/usr/bin/env python3
"""Sweep all BG PDFs in the workspace root through /extract-bg-fields."""
from __future__ import annotations
import glob, json, os, sys, time
import requests

ROOT = "/aidata/gmdc_bg_api"
URL = "http://127.0.0.1:5000/extract-bg-fields"

FIELDS = [
    "bank_guarantee_number", "date_of_issue", "expiry_date", "claim_expiry_date",
    "amount_of_bg", "currency", "bg_issuing_bank", "ifs_code",
    "applicant", "in_favour_of", "rfp_number", "subject",
]

def short(v, n=40):
    if v is None: return ""
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"

def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "*.pdf")))
    results = []
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        t0 = time.time()
        try:
            with open(path, "rb") as fh:
                r = requests.post(URL, files={"file": (name, fh, "application/pdf")}, timeout=240)
            dt = time.time() - t0
            if r.status_code != 200:
                print(f"[{i:02d}/{len(files)}] {name}: HTTP {r.status_code} in {dt:.1f}s")
                results.append({"file": name, "status": r.status_code, "error": r.text[:300]})
                continue
            data = r.json()
            f = data.get("fields", {})
            filled = sum(1 for k in FIELDS if f.get(k))
            print(f"[{i:02d}/{len(files)}] {name}  ({filled}/{len(FIELDS)} fields, {dt:.1f}s)")
            print(f"    bg#={short(f.get('bank_guarantee_number'))}  bank={short(f.get('bg_issuing_bank'))}")
            print(f"    amt={short(f.get('amount_of_bg'))} {f.get('currency','')}   issue={f.get('date_of_issue','')}   exp={f.get('expiry_date','')}")
            print(f"    ifsc={short(f.get('ifs_code'))}   rfp={short(f.get('rfp_number'))}")
            results.append({"file": name, "status": 200, "filled": filled, "fields": f, "elapsed_s": round(dt, 2)})
        except Exception as exc:  # noqa: BLE001
            dt = time.time() - t0
            print(f"[{i:02d}/{len(files)}] {name}: EXCEPTION {exc!r} in {dt:.1f}s")
            results.append({"file": name, "status": "error", "error": str(exc)})
    out = os.path.join(ROOT, "uploads", "sweep_results.json")
    with open(out, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nSaved: {out}")
    # summary
    ok = [r for r in results if r.get("status") == 200]
    if ok:
        avg = sum(r["filled"] for r in ok) / len(ok)
        print(f"Success: {len(ok)}/{len(results)}   avg fields filled: {avg:.1f}/{len(FIELDS)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

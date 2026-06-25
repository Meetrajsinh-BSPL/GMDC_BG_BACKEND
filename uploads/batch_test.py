import typing
#!/usr/bin/env python3
"""Batch-test all BG PDFs against /extract-bg-fields and collect results."""

import json, subprocess, sys, os, time

PDF_DIR = "/aidata/gmdc_bg_api"
ENDPOINT = "http://localhost:5000/extract-bg-fields"

# Find all PDFs (exclude uploads/ duplicates)
pdfs = sorted([
    os.path.join(PDF_DIR, f) for f in os.listdir(PDF_DIR)
    if f.lower().endswith('.pdf')
])

print(f"Found {len(pdfs)} PDFs to test\n")
print("=" * 100)

results = []
CRITICAL_FIELDS = [
    "bank_guarantee_number", "bg_issuing_bank", "amount_of_bg",
    "date_of_issue", "expiry_date", "claim_expiry_date",
    "in_favour_of", "currency"
]

for i, pdf_path in enumerate(pdfs, 1):
    fname = os.path.basename(pdf_path)
    print(f"\n[{i}/{len(pdfs)}] Testing: {fname}")

    start = time.time()
    try:
        proc = subprocess.run(
            ["curl", "-s", "-X", "POST", ENDPOINT, "-F", f"file=@{pdf_path}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180
        )
        elapsed = time.time() - start
        resp = json.loads(proc.stdout.decode('utf-8', errors='replace'))
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        results.append({
            "file": fname, "success": False, "error": "TIMEOUT (180s)",
            "time_s": round(elapsed, 1), "fields": {}
        })
        print(f"  => TIMEOUT after {elapsed:.1f}s")
        continue
    except json.JSONDecodeError as e:
        elapsed = time.time() - start
        results.append({
            "file": fname, "success": False, "error": f"JSON decode: {e}",
            "time_s": round(elapsed, 1), "fields": {}
        })
        print(f"  => JSON decode error after {elapsed:.1f}s")
        continue

    success = resp.get("success", False)
    fields = resp.get("fields", {})
    error = resp.get("error", "")

    # Count filled critical fields
    filled = sum(1 for k in CRITICAL_FIELDS if (fields.get(k) or "").strip())
    total_cr = len(CRITICAL_FIELDS)

    # Identify missing critical fields
    missing = [k for k in CRITICAL_FIELDS if not (fields.get(k) or "").strip()]

    rec = {
        "file": fname,
        "success": success,
        "error": error if not success else "",
        "time_s": round(elapsed, 1),
        "fields": fields,
        "filled_critical": filled,
        "total_critical": total_cr,
        "missing_critical": missing,
    }
    results.append(rec)

    status = "OK" if success else "FAIL"
    print(f"  => {status} | {elapsed:.1f}typing.Union[s, C]ritical: {filled}/{total_cr}")
    if success:
        print(f"     BG#: {fields.get('bank_guarantee_number', '-')}")
        print(f"     Bank: {fields.get('bg_issuing_bank', '-')}")
        print(f"     Amount: {fields.get('amount_of_bg', '-')}")
        print(f"     Issue: {fields.get('date_of_issue', '-')} | Expiry: {fields.get('expiry_date', '-')} | Claim: {fields.get('claim_expiry_date', '-')}")
        print(f"     Beneficiary: {(fields.get('in_favour_of') or '-')[:80]}")
        if missing:
            print(f"     MISSING: {', '.join(missing)}")
    else:
        print(f"     Error: {error}")

# Save raw results
with open("/aidata/gmdc_bg_api/uploads/test_results.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Summary
print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

total = len(results)
ok = sum(1 for r in results if r["success"])
failed = total - ok
avg_time = sum(r["time_s"] for r in results) / max(1, total)

print(f"Total PDFs: {total}")
print(f"Successful: {ok} ({100*ok//total}%)")
print(f"Failed:     {failed}")
print(f"Avg time:   {avg_time:.1f}s")

# Critical field coverage
print(f"\nCRITICAL FIELD COVERAGE (across {ok} successful extractions):")
for field in CRITICAL_FIELDS:
    count = sum(1 for r in results if r["success"] and (r["fields"].get(field) or "").strip())
    pct = 100 * count // max(1, ok)
    print(f"  {field:30s}: {count}/{ok} ({pct}%)")

# Documents with missing critical fields
print(f"\nDOCUMENTS WITH MISSING CRITICAL FIELDS:")
for r in results:
    if r["success"] and r["missing_critical"]:
        print(f"  {r['file'][:60]:60s} => missing: {', '.join(r['missing_critical'])}")

import typing
import re

_months_map = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
}

def _to_dd_mm_yyyy(date_str):
    if not date_str: return date_str
    date_str = date_str.strip()
    m = re.match(r"(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s,]+(\d{4})", date_str)
    if m:
        dd, mon, yyyy = m.group(1), m.group(2), m.group(3)
        mm = _months_map.get(mon[:3].lower())
        if mm:
            return f"{int(dd):02d}/{mm}/{yyyy}"
    m = re.match(r"(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})", date_str)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"
    return date_str

print("=== _to_dd_mm_yyyy tests ===")
tests = [
    ("01-JUN-2030", "01/06/2030"),
    ("31-JUL-2030", "31/07/2030"),
    ("05-DEC-2025", "05/12/2025"),
    ("04-12-2025", "04/12/2025"),
    ("01/06/2030", "01/06/2030"),
]
for inp, expected in tests:
    got = _to_dd_mm_yyyy(inp)
    status = "PASS" if got == expected else "FAIL"
    print(f"  [{status}] {inp!r} -> {got!r} (expected {expected!r})")

print()
print("=== Heuristic regex tests ===")
_FD = r'([0-9]{1,2}[-/\s](?:[0-9]{1,2}|[A-Za-z]{3,9})[-/\s][0-9]{2,4})'
text_snips = [
    ("date_of_issue",      "BANK GUARANTEE NO: 016BG01253390012  ISSUANCE DATE: 05-DEC-2025",
     r'(?:ISSUANCE|BG\s*Issue)\s*DATE?[:\s]*' + _FD),
    ("expiry_date(1)",     "Date of Expiry : 01-JUN-2030",
     r'Date\s*of\s*Expiry\s*[:\-]\s*' + _FD),
    ("expiry_date(2)",     "(IN) This Bank Guarantee is valid up to 01-JUN-2030.",
     r'valid\s*up\s*to\s*' + _FD),
    ("expiry_clause_4",    "on or before the (date) 01-JUN-2030",
     r'on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?' + _FD),
    ("claim_expiry_date",  "a demand on or before 31-JUL-2030.",
     r'on\s*or\s*before\s*(?:the\s*)?(?:\(date\)\s*)?' + _FD),
    ("bg_number",          "BANK GUARANTEE NO: 016BG01253390012",
     r'(?:BANK\s*GUARANTEE\s*NO|Guarantee\s*No|BG\s*No)[:\.\s]*([A-Z0-9]+)'),
    ("rfp_number",         "Ref: Tender bearing No. GMDCAT/MAC/01/2024-25",
     r'[Tt]ender\s*bearing\s*[Nn]o[.:\s]*([^\n,;]{5,40})'),
    ("amount",             "Limit to liability : Rs.556,598/-",
     r'(?:Rs\.?|INR|Rupees)\s*([0-9][0-9,\.]+)'),
]
for label, text, pat in text_snips:
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        if re.match(r'\d{1,2}[-/\s]', raw):
            normalized = _to_dd_mm_yyyy(raw)
        else:
            normalized = raw
        print(f"  [PASS] {label}: {normalized!r}")
    else:
        print(f"  [FAIL] {label}: NO MATCH in {text!r}")

print()
print("=== Amount decimal-comma fix ===")
def _amount_matches(extracted, api_blob):
    blob = re.sub(r'(\d),(\d{2})(?!\d)', r'\1.\2', api_blob)
    blob = re.sub(r',', '', blob)
    pat = r'(?:inr|rs\.?|rupees|only|\$|₹|/-)'
    e = re.sub(pat, '', extracted, flags=re.IGNORECASE).strip().replace(',', '')
    b = re.sub(pat, '', blob, flags=re.IGNORECASE).strip().replace(',', '')
    try:
        return abs(float(e) - float(b)) < 0.05
    except:
        return False

cases = [
    ("556598.00", "556598,00", True),
    ("556598", "556,598.00", True),
    ("100000", "1,00,000", True),
]
for ext, api, expected in cases:
    got = _amount_matches(ext, api)
    status = "PASS" if got == expected else "FAIL"
    print(f"  [{status}] extracted={ext!r} api={api!r} -> {got}")

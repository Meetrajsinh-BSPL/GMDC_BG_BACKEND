from __future__ import annotations
"""Per-field matching helpers used by /validate-upload."""
import re

from normalizers import normalize_for_match


def flatten_json_text(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(flatten_json_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(flatten_json_text(i) for i in obj)
    if isinstance(obj, str):
        return obj
    return str(obj)


def _norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[\s,_\-/:|]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def loose_contains(needle: str, haystack: str) -> bool:
    n = _norm_text(needle)
    h = _norm_text(haystack)
    if not n:
        return False
    if n in h:
        return True
    n_tokens = set(n.split())
    if not n_tokens:
        return False
    h_tokens = set(h.split())
    return len(n_tokens & h_tokens) / max(1, len(n_tokens)) >= 0.6


def _digits_only(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def _parse_amount_int(s: str):
    if not s:
        return None
    s = s.replace(",", "")
    s = re.sub(r"(inr|rs\.?|rupees|only|\$|₹|/-)", " ", s, flags=re.IGNORECASE)
    best = None
    for n in re.findall(r"\d+(?:\.\d+)?", s):
        try:
            v = int(float(n))
            if best is None or v > best:
                best = v
        except ValueError:
            continue
    return best


def amount_matches(extracted: str, api_blob: str) -> int:
    ex = _parse_amount_int(extracted)
    if ex is None:
        return 0
    # ICICI uses comma-as-decimal separator ("556598,00"). Convert before stripping commas.
    blob = re.sub(r"(\d),(\d{2})(?!\d)", r"\1.\2", api_blob)
    blob = blob.replace(",", "")
    for c in re.findall(r"\d+(?:\.\d+)?", blob):
        try:
            v = int(float(c))
        except ValueError:
            continue
        if abs(v - ex) <= max(1, int(0.01 * ex)):
            return 1
    return 0


_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11",
    "dec": "12",
}


def _normalize_date_to_variants(s: str) -> list[str]:
    if not s:
        return []
    t = s.strip().lower()

    m = re.search(
        r"(\d{1,2})\s*[-/ .]?\s*([a-zA-Z]+)\s*[-/ ,.]?\s*(\d{2,4})", t
    )
    if m:
        dd = f"{int(m.group(1)):02d}"
        mon_txt = m.group(2)[:3]
        yyyy = m.group(3)
        if len(yyyy) == 2:
            yyyy = "20" + yyyy
        mm = _MONTHS.get(mon_txt)
        if mm:
            return list({
                f"{dd}/{mm}/{yyyy}", f"{dd}-{mm}-{yyyy}",
                f"{yyyy}-{mm}-{dd}", f"{yyyy}/{mm}/{dd}",
                f"{dd}{mm}{yyyy}", f"{yyyy}{mm}{dd}",
            })

    ds = _digits_only(t)
    if len(ds) == 7:
        ds = ds.zfill(8)
    if len(ds) >= 8:
        dd, mm, yyyy = ds[0:2], ds[2:4], ds[4:8]
        return list({
            f"{dd}/{mm}/{yyyy}", f"{dd}-{mm}-{yyyy}", f"{yyyy}-{mm}-{dd}",
            f"{yyyy}/{mm}/{dd}", f"{dd}.{mm}.{yyyy}", f"{dd}{mm}{yyyy}",
            f"{yyyy}{mm}{dd}",
        })
    return []


def date_matches(extracted: str, api_blob: str) -> int:
    variants = _normalize_date_to_variants(extracted)
    if not variants:
        return 0
    for v in variants:
        if v in api_blob:
            return 1
    dob = _digits_only(api_blob)
    for v in variants:
        if _digits_only(v) in dob:
            return 1
    return 0


def id_matches(extracted: str, api_blob: str) -> int:
    e = normalize_for_match(extracted)
    a = normalize_for_match(api_blob)
    return 1 if e and e in a else 0


_IFSC_BANK_PREFIX = {
    "UTIB": "AXIS BANK", "HDFC": "HDFC BANK", "ICIC": "ICICI BANK",
    "SBIN": "STATE BANK", "PUNB": "PUNJAB NATIONAL", "BARB": "BANK OF BARODA",
    "UBIN": "UNION BANK", "YESB": "YES BANK", "KKBK": "KOTAK", "IDFC": "IDFC",
    "CNRB": "CANARA", "BKID": "BANK OF INDIA", "IOBA": "INDIAN OVERSEAS",
    "MAHB": "BANK OF MAHARASHTRA", "CBIN": "CENTRAL BANK",
}


def bank_name_matches(extracted_bank_name: str, decrypted_obj: dict, api_blob: str) -> int:
    if not extracted_bank_name:
        return 0
    if loose_contains(extracted_bank_name, api_blob):
        return 1
    try:
        issuance = (decrypted_obj.get("eBGList", {}) or {}).get("eBGIssuanceList", [])
        if issuance and isinstance(issuance, list):
            ifsc = (issuance[0].get("issuingBranchIFSC") or "").strip().upper()
            if len(ifsc) >= 4:
                hint = _IFSC_BANK_PREFIX.get(ifsc[:4], "")
                if hint and hint in extracted_bank_name.upper():
                    return 1
    except Exception:
        pass
    return 0


def subject_matches(extracted: str, api_blob: str) -> int:
    if not extracted:
        return 0
    e = extracted.upper()
    blob = api_blob.upper()
    if "EMD" in e and re.search(r"\bEMD\b", blob):
        return 1
    if "PERFORMANCE" in e and "PERFORMANCE" in blob:
        return 1
    return 1 if loose_contains(extracted, api_blob) else 0

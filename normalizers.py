from __future__ import annotations
"""Text / amount / date / identifier normalization helpers."""
import re


# ---------------- Text ----------------

def normalize_spaces(t: str) -> str:
    if not t:
        return t
    t = re.sub(r"\r", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def dehyphenate(t: str) -> str:
    """Join OCR-broken words like '31-\\nJUL-2030' -> '31-JUL-2030'."""
    if not t:
        return t
    return re.sub(r"(-)\s*\n\s*([A-Za-z0-9])", lambda m: m.group(1) + m.group(2), t)


# ---------------- Identifier fixers ----------------

def fix_common_ocr_confusions_identifier(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    t = s
    t = re.sub(r"(?<=\d)I(?=\d)", "1", t)
    t = re.sub(r"(?<=\d)l(?=\d)", "1", t)
    t = re.sub(r"(?<=\d)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\d)o(?=\d)", "0", t)
    t = re.sub(r"^(\d+)I(\d+)$", r"\g<1>1\g<2>", t)
    t = re.sub(r"^(\d+)l(\d+)$", r"\g<1>1\g<2>", t)
    return t


def fix_ifsc_code(s: str) -> str:
    """IFSC = 4 letters + '0' + 6 alphanumerics."""
    if not s:
        return s
    t = s.strip().upper().replace(" ", "")
    if len(t) >= 5 and t[4] == "O":
        t = t[:4] + "0" + t[5:]
    if len(t) == 11:
        prefix = t[:4]
        mid = t[4]
        branch = list(t[5:])
        for i, ch in enumerate(branch):
            if ch == "O":
                branch[i] = "0"
            elif ch in {"I", "L"}:
                branch[i] = "1"
        t = prefix + mid + "".join(branch)
    if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", t or ""):
        return t
    return s


def fix_bg_number(s: str) -> str:
    if not s:
        return s
    t = re.sub(r"\s+", "", s.strip()).upper()
    t = t.replace("|", "I")
    t = re.sub(r"(?<=[A-Za-z])1(?=[A-Za-z])", "I", t)
    t = re.sub(r"(?<=\d)[Il](?=\d)", "1", t)
    t = re.sub(r"(?<=\d)[Oo](?=\d)", "0", t)
    return t


_DATE_LOOKING = re.compile(
    r"^\d{1,2}[-/.](?:\d{1,2}|[A-Z]{3,9})[-/.]\d{2,4}$", re.IGNORECASE
)


def is_valid_bg_number(s: str) -> bool:
    if not s:
        return False
    clean = re.sub(r"[^A-Z0-9]", "", s.upper())
    if len(clean) < 6:
        return False
    if not re.search(r"\d", clean):
        return False
    alpha_num = sum(1 for c in s if c.isalnum())
    if alpha_num < len(s) * 0.7:
        return False
    if _DATE_LOOKING.match(s.strip()):
        return False
    return True


def normalize_for_match(s: str) -> str:
    if not s:
        return ""
    t = s.upper()
    t = t.replace("I", "1").replace("L", "1").replace("O", "0")
    t = re.sub(r"\s+", "", t)
    return t


# -- OCR O↔0 / I↔1 disambiguation against bank-specific BG# patterns --

# Patterns observed in the sample corpus. Each is a strict shape:
#   <digit-block><letter-block><digit-block>  etc.
_BG_PATTERNS = [
    ("ICICI",                   re.compile(r"^\d{4}[A-Z]{4}\d{8}$")),
    ("HDFC",                    re.compile(r"^\d{3}[A-Z]{2}\d{11}$")),
    ("BANK OF BARODA",          re.compile(r"^\d{4}[A-Z]{3}\d{9}$")),
    ("AXIS",                    re.compile(r"^\d{4}[A-Z]{3}\d{6}$")),
    ("YES",                     re.compile(r"^\d{3}[A-Z]{2}\d{11}$")),
    ("RBL",                     re.compile(r"^[A-Z]{4}\d{11}$")),
    ("STATE BANK",              re.compile(r"^\d{7}[A-Z]{2}\d{7}$")),
    ("SBI",                     re.compile(r"^\d{7}[A-Z]{2}\d{7}$")),
    ("UNION",                   re.compile(r"^\d{6}[A-Z]{2}\d{7}$")),
    ("PUNJAB NATIONAL",         re.compile(r"^\d{6}[A-Z]{2}\d{6}$")),
]

# Ambiguous-char map. Bidirectional: {letter -> digit, digit -> letter(s)}.
_OCR_AMBIG_TO_DIGIT = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6"}
_OCR_AMBIG_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}


def _ocr_variants(s: str, max_positions: int = 14):
    """Yield BG-number strings obtained by toggling each ambiguous character
    between its digit/letter form. Bounded to ``max_positions`` ambiguous slots
    to keep enumeration < 2**14."""
    positions = []
    alts = []
    for i, ch in enumerate(s):
        if ch in _OCR_AMBIG_TO_DIGIT:
            positions.append(i)
            alts.append((ch, _OCR_AMBIG_TO_DIGIT[ch]))
        elif ch in _OCR_AMBIG_TO_LETTER:
            positions.append(i)
            alts.append((ch, _OCR_AMBIG_TO_LETTER[ch]))
        if len(positions) >= max_positions:
            break
    if not positions:
        yield s
        return
    n = len(positions)
    for mask in range(1 << n):
        arr = list(s)
        for j, pos in enumerate(positions):
            arr[pos] = alts[j][(mask >> j) & 1]
        yield "".join(arr)


def reconcile_bg_with_bank(bg: str, bank_name: str) -> str:
    """If the BG# looks malformed for the given bank, try OCR variants (O↔0,
    I/L↔1) and return the first one matching the bank's known pattern."""
    if not bg or not bank_name:
        return bg
    bg = bg.strip().upper().replace(" ", "")
    bank_up = bank_name.upper()
    pattern = None
    for key, pat in _BG_PATTERNS:
        if key in bank_up:
            pattern = pat
            break
    if pattern is None:
        return bg
    if pattern.match(bg):
        return bg
    for variant in _ocr_variants(bg):
        if pattern.match(variant):
            return variant
    return bg


# ---------------- Amount ----------------

def normalize_amount_numeric(s: str) -> str:
    """'INR 23,75,410.00' -> '2375410.00'. Picks the largest numeric token adjacent to
    a currency marker when possible, otherwise the largest numeric token overall.
    """
    if not s or not isinstance(s, str):
        return s
    # Prefer numbers that follow a currency marker
    currency_adj = re.findall(
        r"(?i)(?:Rs\.?|INR|Rupees|₹)\s*[:.]?\s*([\d,]+(?:\.\d+)?)", s
    )
    candidates = currency_adj if currency_adj else re.findall(r"[\d,]+(?:\.\d+)?", s)

    best = None
    best_raw = None
    for tok in candidates:
        clean = tok.replace(",", "")
        try:
            val = float(clean)
        except ValueError:
            continue
        if best is None or val > best:
            best = val
            best_raw = clean
    if best_raw is None:
        return re.sub(r"[^0-9]", "", s)
    if "." in best_raw:
        try:
            return f"{float(best_raw):.2f}"
        except ValueError:
            return best_raw
    return best_raw


# ---------------- Date ----------------

_MONTHS_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11",
    "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04", "june": "06",
    "july": "07", "august": "08", "september": "09", "october": "10",
    "november": "11", "december": "12",
}


def to_dd_mm_yyyy(date_str: str) -> str:
    if not date_str or not isinstance(date_str, str):
        return date_str
    date_str = date_str.strip()

    def _safe(dd, mm, yyyy):
        try:
            d, m = int(dd), int(mm)
            if 1 <= d <= 31 and 1 <= m <= 12:
                return f"{d:02d}/{m:02d}/{yyyy}"
        except ValueError:
            pass
        return date_str

    m = re.match(r"(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s,]+(\d{4})", date_str)
    if m:
        dd, mon, yyyy = m.group(1), m.group(2), m.group(3)
        mm = _MONTHS_MAP.get(mon[:3].lower())
        if mm:
            return _safe(dd, mm, yyyy)

    m = re.match(r"(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})", date_str) or \
        re.match(r"(\d{1,2})[.](\d{1,2})[.](\d{2,4})", date_str)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        if len(yyyy) == 2:
            yyyy = "20" + yyyy
        return _safe(dd, mm, yyyy)

    m = re.match(r"(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})", date_str)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return _safe(dd, mm, yyyy)

    m = re.match(r"^(\d{2})(\d{2})(\d{4})$", date_str)
    if m:
        return _safe(m.group(1), m.group(2), m.group(3))

    m = re.match(r"(\d{1,2})[a-z]{0,2}[\s.]+([A-Za-z]+)[,\s.]+(\d{4})", date_str)
    if m:
        dd, mon, yyyy = m.group(1), m.group(2), m.group(3)
        mm = _MONTHS_MAP.get(mon[:3].lower())
        if mm:
            return _safe(dd, mm, yyyy)

    return date_str

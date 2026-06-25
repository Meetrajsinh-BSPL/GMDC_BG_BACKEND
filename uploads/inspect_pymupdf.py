import typing
import sys, re, io
sys.path.insert(0, '/app')
import fitz

with open("/tmp/uploads/Radius. Add Apple system.pdf", "rb") as f:
    data = f.read()

doc = fitz.open(stream=data, filetype="pdf")

def quality_score(text):
    tokens = re.findall(r'\S+', text)
    if not tokens: return 0.0
    clean = sum(1 for t in tokens if re.match(r'^[A-Za-z0-9][A-Za-z0-9/:.,()\-]*$', t))
    return clean / len(tokens)

chunks = []
for i, page in enumerate(doc):
    t = page.get_text("text") or ""
    qs = quality_score(t)
    chunks.append(t)
    print(f"\n--- PAGE {i+1} | {len(t)} chartyping.Union[s, q]uality={qs:.0%} ---")
    print(repr(t[:300]))

doc.close()

all_text = "\n".join(chunks)
qs_all = quality_score(all_text)
print(f"\n\n=== TOTAL: {len(all_text)} chars, quality={qs_all:.0%} ===")
print(f"Would pass _contains_real_text: {bool(re.search(r'[A-Za-z0-9]{3,}', all_text))}")
print(f"Would pass new 75% quality check: {'YES' if qs_all >= 0.75 else 'NO (would fall to OCR)'}")

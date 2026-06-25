import typing
import sys, re
sys.path.insert(0, '/app')

# Test what pdfplumber gets page-by-page
try:
    import pdfplumber
    import io

    with open("/tmp/uploads/Radius. Add Apple system.pdf", "rb") as f:
        data = f.read()

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        chunks = []
        for i, page in enumerate(pdf.pages):
            t = page.extract_text() or ""
            chunks.append(t)
            # Quality score
            tokens = re.findall(r'\S+', t)
            clean = sum(1 for tok in tokens if re.match(r'^[A-Za-z0-9][A-Za-z0-9/:.,()\-]*$', tok))
            score = (clean / len(tokens) * 100) if tokens else 0
            print(f"\n--- PAGE {i+1} | {len(t)} chartyping.Union[s, q]uality={score:.0f}% ---")
            print(t[:400] if t else "(empty)")

    print("\n\n=== QUALITY SCORES SUMMARY ===")
    all_tokens = re.findall(r'\S+', "\n".join(chunks))
    clean_all = sum(1 for tok in all_tokens if re.match(r'^[A-Za-z0-9][A-Za-z0-9/:.,()\-]*$', tok))
    overall = (clean_all / len(all_tokens) * 100) if all_tokens else 0
    print(f"Overall: {len(all_tokens)} tokens, {overall:.1f}% clean")
    print(f"pdfplumber would {'PASS' if overall >= 75 else 'FAIL'} new quality check (threshold=75%)")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

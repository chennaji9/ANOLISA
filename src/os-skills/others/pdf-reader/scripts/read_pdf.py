#!/usr/bin/env python3
"""PDF text extractor (PyMuPDF)."""
import argparse, json, os, sys

def _install():
    """Return the PyMuPDF module, installing it when missing.

    Prefers the modern `pymupdf` import name: importing the legacy `fitz`
    alias prints a deprecation warning on stdout, which would corrupt the
    machine-readable --format json output.
    """
    try: import pymupdf; return pymupdf
    except ImportError: pass
    try: import fitz; return fitz
    except ImportError:
        import subprocess; subprocess.check_call([sys.executable,"-m","pip","install","-q","PyMuPDF"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try: import pymupdf; return pymupdf
        except ImportError: import fitz; return fitz

def _pages(spec, total):
    ps = set()
    for p in spec.split(","):
        p = p.strip()
        if "-" in p:
            a, b = p.split("-",1); [ps.add(i) for i in range(max(0,int(a)-1), min(total,int(b)))]
        else:
            i = int(p)-1
            if 0 <= i < total: ps.add(i)
    return sorted(ps)

def cap_pages_text(pages, limit):
    """Bound the combined page text to `limit` characters (mutates in place).

    Earlier pages keep their text first; the page at the boundary keeps a
    prefix plus an ellipsis, later non-empty pages reduce to an ellipsis.
    Ellipsis markers and JSON structure overhead are not counted against
    the limit. Returns True when any text was dropped.
    """
    remaining = limit
    dropped = False
    for p in pages:
        text = p["text"]
        if len(text) <= remaining:
            remaining -= len(text)
            continue
        keep = max(remaining, 0)
        p["text"] = (text[:keep] + "...") if keep > 0 else "..."
        dropped = True
        remaining = 0
    return dropped

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-f","--file",required=True)
    ap.add_argument("-p","--pages",default=None)
    ap.add_argument("-d","--metadata",action="store_true")
    ap.add_argument("--format",default="text",choices=["text","json"])
    ap.add_argument("-m","--max-length",type=int,default=0,
                    help="cap total extracted text length; JSON output stays parseable (pages are trimmed and \"truncated\": true is set)")
    a = ap.parse_args()

    fitz = _install()
    if not os.path.exists(a.file):
        print(f"ERROR: {a.file} not found",file=sys.stderr); sys.exit(1)
    doc = fitz.open(a.file)
    n = len(doc)
    idx = _pages(a.pages, n) if a.pages else list(range(n))

    meta = {}
    if a.metadata and doc.metadata:
        meta = {k:v for k,v in doc.metadata.items() if v}

    pages = []
    for i in idx:
        t = doc[i].get_text("text").strip()
        if not t:
            blocks = doc[i].get_text("blocks")
            t = "\n".join(b[4] for b in sorted(blocks,key=lambda b:(b[1],b[0])) if b[-1]==0).strip()
        pages.append({"page":i+1,"text":t})
    doc.close()

    if a.format == "json":
        out = {"total_pages":n,"pages":pages}
        if meta: out["metadata"] = meta
        # Trim before serializing: slicing the serialized document would
        # emit invalid JSON that no downstream consumer can parse.
        if a.max_length > 0 and cap_pages_text(pages, a.max_length):
            out["truncated"] = True
        r = json.dumps(out,ensure_ascii=False,indent=2)
    else:
        parts = []
        if meta:
            parts.append("=== Metadata ===")
            parts.extend(f"  {k}: {v}" for k,v in meta.items())
            parts.append(f"  total_pages: {n}\n")
        for p in pages:
            parts.append(f"--- Page {p['page']} ---")
            parts.append(p["text"]); parts.append("")
        r = "\n".join(parts)
        if a.max_length > 0 and len(r) > a.max_length:
            r = r[:a.max_length] + "\n...[truncated]"
    print(r)

if __name__ == "__main__":
    main()

"""
resume_util - store a resume and mine it for good-fit keywords.

Keeps the single most-recent resume in resumes/, plus a small JSON sidecar with
its metadata and the keyword hits found in it. Text extraction is standard-library
only for the common cases:

  .txt / .md / .rtf  -> decoded directly (rtf lightly de-marked-up)
  .docx              -> unzipped, text pulled from word/document.xml
  .pdf               -> best effort: used only if pdfminer or pypdf happens to be
                        installed (stdlib can't reliably read PDFs); otherwise the
                        file is stored but yields no suggestions.

Suggestions come from matching the resume text against a curated vocabulary of
terms that matter for entry-level / summer jobs, so the chips stay relevant
instead of being noisy n-grams.
"""

import io
import json
import os
import re
import zipfile

import jobhunt  # for HERE, has_term, dt

RESUMES_DIR = os.path.join(jobhunt.HERE, "resumes")
META_PATH = os.path.join(RESUMES_DIR, "_meta.json")
MAX_BYTES = 8 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md", ".text", ".rtf"}

# Terms worth surfacing for a teen's summer-job search. Roles first, then
# transferable skills, then certs/languages/tools -- this is also the order
# suggestions appear in the UI. Multi-word terms are fine; matching is
# word-boundary aware (see jobhunt.has_term).
SKILL_VOCAB = [
    # roles / job types
    "barista", "cashier", "retail", "sales associate", "server", "waiter",
    "waitress", "host", "hostess", "busser", "dishwasher", "line cook",
    "prep cook", "food service", "crew member", "stocker", "bagger", "scooper",
    "ice cream", "lifeguard", "camp counselor", "counselor", "babysitter",
    "babysitting", "nanny", "tutor", "tutoring", "coaching", "receptionist",
    "front desk", "library", "lab assistant", "landscaping", "groundskeeper",
    "delivery", "warehouse", "valet", "concession", "ticket", "usher",
    # transferable skills
    "customer service", "cash handling", "point of sale", "teamwork",
    "communication", "time management", "organization", "leadership",
    "problem solving", "multitasking", "attention to detail", "reliable",
    "punctual", "fast paced", "inventory", "scheduling", "cleaning", "stocking",
    # certs / languages
    "cpr", "first aid", "servsafe", "food handler", "lifeguard certification",
    "wsi", "bilingual", "spanish", "mandarin", "french", "portuguese",
    "haitian creole", "cantonese", "vietnamese",
    # tools
    "microsoft office", "excel", "word", "powerpoint", "google workspace",
    "social media", "canva", "photoshop", "quickbooks",
    # school / community
    "volunteer", "volunteering", "mentoring", "honor roll", "student council",
]


# --------------------------------------------------------------------------- #
# text extraction
# --------------------------------------------------------------------------- #
def extract_text(filename, data):
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".txt", ".md", ".text"):
        return data.decode("utf-8", "ignore")
    if ext == ".rtf":
        return _strip_rtf(data.decode("utf-8", "ignore"))
    if ext == ".docx":
        return _docx_text(data)
    if ext == ".pdf":
        return _pdf_text(data)
    return ""


def _docx_text(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)      # paragraph -> newline
    xml = re.sub(r"<[^>]+>", " ", xml)      # drop all tags, keep text nodes
    return re.sub(r"[ \t]+", " ", xml).strip()


def _strip_rtf(text):
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)   # escaped bytes
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)  # control words
    text = re.sub(r"[{}]", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _pdf_text(data):
    """PDFs need a real parser; use one only if it's already installed."""
    try:
        from pdfminer.high_level import extract_text as _pm
        return _pm(io.BytesIO(data)) or ""
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        rdr = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in rdr.pages)
    except Exception:
        return ""


def _vocab_hits(text):
    low = text.lower()
    if not low.strip():
        return []
    hits = []
    for term in SKILL_VOCAB:
        if jobhunt.has_term(term, low):
            hits.append(term)
    return hits


# --------------------------------------------------------------------------- #
# storage
# --------------------------------------------------------------------------- #
def sanitize_name(name):
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^A-Za-z0-9 ._-]", "_", name)
    name = name.strip(". ") or "resume"
    return name[:120]


def load_meta():
    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _remove_current_file():
    meta = load_meta()
    if meta:
        p = os.path.join(RESUMES_DIR, meta.get("filename", ""))
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def save_resume(filename, data):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"unsupported file type '{ext or '?'}' — use pdf, docx, txt, md, or rtf")
    if not data:
        raise ValueError("empty file")
    if len(data) > MAX_BYTES:
        raise ValueError(f"file too large ({len(data)//1024} KB; max {MAX_BYTES//1024} KB)")

    os.makedirs(RESUMES_DIR, exist_ok=True)
    _remove_current_file()                       # only one resume at a time
    safe = sanitize_name(filename)
    with open(os.path.join(RESUMES_DIR, safe), "wb") as f:
        f.write(data)

    text = extract_text(safe, data)
    meta = {
        "filename": safe,
        "size": len(data),
        "ext": ext,
        "uploaded": jobhunt.dt.datetime.now().isoformat(timespec="seconds"),
        "extracted": bool(text.strip()),
        "text_chars": len(text),
        "all_suggestions": _vocab_hits(text),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return meta


def delete_resume():
    _remove_current_file()
    if os.path.exists(META_PATH):
        os.remove(META_PATH)


def current_file_path():
    meta = load_meta()
    if not meta:
        return None
    p = os.path.realpath(os.path.join(RESUMES_DIR, meta.get("filename", "")))
    if p.startswith(os.path.realpath(RESUMES_DIR)) and os.path.isfile(p):
        return p
    return None


def get_state(existing_positive=()):
    """Resume metadata + the keyword suggestions not already in the profile."""
    meta = load_meta()
    if not meta:
        return {"resume": None, "suggestions": []}
    existing = {t.lower() for t in existing_positive}
    suggestions = [s for s in meta.get("all_suggestions", []) if s not in existing]
    public = {k: meta[k] for k in
              ("filename", "size", "ext", "uploaded", "extracted", "text_chars")
              if k in meta}
    return {"resume": public, "suggestions": suggestions}

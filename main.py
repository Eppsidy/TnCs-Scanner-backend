from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import re
import io
import nltk
import os

# NLP/model imports
from transformers import pipeline

# File parsers
import pdfplumber
import docx
import requests
from bs4 import BeautifulSoup

# Download NLTK data (with error handling for Azure)
try:
    nltk.download('punkt', quiet=True)
except Exception as e:
    print(f"Warning: Could not download NLTK data: {e}")

app = FastAPI(title="T&C Summarizer - Upgraded Backend")

# Make this narrow in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tncs-scanner.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Configurations
# -----------------------------
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")
CHUNK_TOKEN_LIMIT = int(os.getenv("CHUNK_TOKEN_LIMIT", "700"))  # approx words per chunk
PORT = int(os.getenv("PORT", 8000))  # Azure sets this automatically

# instantiate model (this may take time)
try:
    summarizer = pipeline("summarization", model=SUMMARIZER_MODEL, device=-1)  # Use CPU by default
    print(f"✅ Summarization model loaded: {SUMMARIZER_MODEL}")
except Exception as e:
    print(f"⚠️ Warning: Failed to initialize summarization pipeline: {e}")
    print("⚠️ Falling back to text truncation method")
    summarizer = None

# -----------------------------
# Utilities: file parsing
# -----------------------------

def extract_text_from_pdf_bytes(b: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx_bytes(b: bytes) -> str:
    doc = docx.Document(io.BytesIO(b))
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(paragraphs)


def fetch_text_from_url(url: str) -> str:
    r = requests.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    # naive extraction: join all paragraphs
    paragraphs = [p.get_text(separator=" ") for p in soup.find_all('p')]
    return "\n".join(paragraphs)

# -----------------------------
# Text cleaning and chunking
# -----------------------------

def clean_text(text: str) -> str:
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, max_words: int = CHUNK_TOKEN_LIMIT) -> List[str]:
    sentences = nltk.sent_tokenize(text)
    chunks = []
    current = []
    current_len = 0

    for s in sentences:
        words = len(s.split())
        if current_len + words <= max_words:
            current.append(s)
            current_len += words
        else:
            if current:
                chunks.append(" ".join(current))
            current = [s]
            current_len = words
    if current:
        chunks.append(" ".join(current))
    return chunks

# -----------------------------
# Clause classification & risk scoring (rule-based)
# -----------------------------

CLAUSE_KEYWORDS = {
    "Data Collection": ["collect", "personal data", "third party", "share your data", "cookies", "tracking"],
    "Refunds": ["refund", "cancel", "cancellation", "return", "chargeback"],
    "Auto-Renewal": ["auto-renew", "automatic renewal", "renewal"],
    "Liability": ["liab", "limitation of liability", "not liable", "indirect damages", "consequential"],
    "Arbitration": ["arbitration", "binding arbitration", "dispute resolution", "class action waiver"],
    "Intellectual Property": ["intellectual property", "copyright", "trademark", "license to use"],
}

RISK_KEYWORDS = {
    # keyword: weight
    "share your data": 3,
    "third party": 2,
    "binding arbitration": 3,
    "no refunds": 2,
    "automatic renewal": 2,
    "limitation of liability": 2,
    "class action waiver": 3,
}


def classify_clauses(text: str) -> Dict[str, List[str]]:
    matches = {k: [] for k in CLAUSE_KEYWORDS.keys()}
    lower = text.lower()

    # scan paragraph-wise for likely matches
    paragraphs = [p.strip() for p in re.split(r"\n{1,}", text) if p.strip()]
    for p in paragraphs:
        pl = p.lower()
        for label, kw_list in CLAUSE_KEYWORDS.items():
            for kw in kw_list:
                if kw in pl:
                    if len(matches[label]) < 10:  # cap per label
                        matches[label].append(p.strip())
                    break
    # remove empty lists
    return {k: v for k, v in matches.items() if v}


def compute_risk_score(text: str) -> Dict[str, Any]:
    score = 0
    found = []
    lower = text.lower()
    for kw, w in RISK_KEYWORDS.items():
        if kw in lower:
            score += w
            found.append(kw)
    # normalize to low/medium/high
    if score >= 6:
        level = "high"
    elif score >= 3:
        level = "medium"
    else:
        level = "low"
    return {"score": score, "level": level, "found": found}

# -----------------------------
# Response model
# -----------------------------

class SummaryResponse(BaseModel):
    title: str
    summary: str
    keyPoints: List[str]
    riskLevel: str
    readingTime: str
    importantClauses: List[str]
    raw_extracted: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

# -----------------------------
# API endpoints
# -----------------------------

@app.post("/summarizer", response_model=SummaryResponse)
async def summarize(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    text_body: Optional[str] = Form(None),
    include_raw: Optional[bool] = Form(False),
):
    """
    Accepts one of: file upload (txt/pdf/docx), url, or raw text in `text_body`.
    Returns structured summary JSON.
    """
    print(f"📄 Processing request - File: {file.filename if file else 'None'}, URL: {url}, Text length: {len(text_body) if text_body else 0}")

    if not any([file, url, text_body]):
        return SummaryResponse(
            title="",
            summary="",
            keyPoints=[],
            riskLevel="low",
            readingTime="0",
            importantClauses=[],
            raw_extracted=None,
            metadata={"error": "No input provided. Send a file, url, or text_body."}
        )

    extracted = ""
    filename = ""

    # 1) File upload
    if file:
        filename = file.filename
        content = await file.read()
        lower_name = filename.lower()
        try:
            if lower_name.endswith('.pdf'):
                extracted = extract_text_from_pdf_bytes(content)
            elif lower_name.endswith('.docx'):
                extracted = extract_text_from_docx_bytes(content)
            else:
                # assume plain text
                extracted = content.decode('utf-8', errors='ignore')
        except Exception as e:
            extracted = content.decode('utf-8', errors='ignore')

    # 2) URL
    elif url:
        filename = url
        try:
            extracted = fetch_text_from_url(url)
        except Exception as e:
            extracted = f"""Failed to fetch URL: {e}"""

    # 3) Raw text
    elif text_body:
        filename = "pasted_text"
        extracted = text_body

    cleaned = clean_text(extracted)

    # early short-circuit
    if not cleaned:
        return SummaryResponse(
            title=filename,
            summary="",
            keyPoints=[],
            riskLevel="low",
            readingTime="0",
            importantClauses=[],
            raw_extracted=None,
            metadata={"error": "No text extracted from input."}
        )

    # chunk and summarize
    chunks = chunk_text(cleaned)
    chunk_summaries = []
    for i, c in enumerate(chunks):
        if summarizer:
            try:
                # Use AI model for summarization
                s = summarizer(c, max_length=150, min_length=30, do_sample=False)[0]['summary_text']
            except Exception as e:
                print(f"⚠️ AI summarization failed for chunk {i}: {e}")
                # fallback: simple truncation
                s = ' '.join(c.split()[:120]) + ('...' if len(c.split())>120 else '')
        else:
            # No AI model available, use simple truncation
            s = ' '.join(c.split()[:120]) + ('...' if len(c.split())>120 else '')
        chunk_summaries.append(s)

    # combine chunk summaries into final summary and key points
    final_summary = "\n\n".join(chunk_summaries)

    # Produce key points by splitting sentences from the final summary and choosing top N
    final_sentences = nltk.sent_tokenize(final_summary)
    key_points = [s.strip() for s in final_sentences[:8]]

    # classify clauses
    clauses = classify_clauses(cleaned)
    important_clauses = []
    for label, items in clauses.items():
        for it in items[:3]:
            important_clauses.append(f"[{label}] {it}")

    # risk score
    risk = compute_risk_score(cleaned)

    # reading time estimate (words / 200 wpm)
    words = len(cleaned.split())
    minutes = max(1, int(words / 200))
    reading_time = f"{minutes} minutes"

    response = SummaryResponse(
        title=filename,
        summary=final_summary,
        keyPoints=key_points,
        riskLevel=risk['level'],
        readingTime=reading_time,
        importantClauses=important_clauses,
        raw_extracted=cleaned if include_raw else None,
        metadata={
            "chunks": len(chunks),
            "word_count": words,
            "risk_details": risk,
            "clauses_found_count": {k: len(v) for k, v in clauses.items()},
        }
    )

    print(f"✅ Successfully processed {filename} - {words} words, {len(chunks)} chunks, risk: {risk['level']}")
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "model": SUMMARIZER_MODEL}

# End of file

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import io, os, re, pdfplumber, docx, nltk
from bs4 import BeautifulSoup
import requests

app = FastAPI(title="TNCS Scanner Backend (Optimized for Azure)")

# --- Allow all CORS requests ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Download NLTK tokenizer only if missing ---
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

# --- Lazy-loaded models ---
summarizer = None
sentiment_analyzer = None


def get_summarizer():
    """Load summarizer only once (smaller model for faster loading)."""
    global summarizer
    if summarizer is None:
        from transformers import pipeline
        model_name = os.getenv("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")
        summarizer = pipeline("summarization", model=model_name, device=-1)
        print(f"✅ Summarizer model loaded: {model_name}")
    return summarizer


def get_sentiment_analyzer():
    """Load sentiment model only once."""
    global sentiment_analyzer
    if sentiment_analyzer is None:
        from transformers import pipeline
        sentiment_analyzer = pipeline("sentiment-analysis")
        print("✅ Sentiment model loaded.")
    return sentiment_analyzer


# --- Health check ---
@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Utility: Extract text from supported file types ---
def extract_text(file: UploadFile):
    content = file.file.read()
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = " ".join(page.extract_text() or "" for page in pdf.pages)
    elif filename.endswith(".docx"):
        doc = docx.Document(io.BytesIO(content))
        text = " ".join(p.text for p in doc.paragraphs)
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        text = ""

    return text.strip()


# --- Utility: Extract text from a website ---
def extract_from_url(url: str):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        return " ".join(p.text for p in soup.find_all("p"))
    except Exception:
        return ""


# --- Risk detection keywords ---
RISK_KEYWORDS = {
    "data": ["personal data", "third party", "tracking", "cookies"],
    "payment": ["credit card", "billing", "charges", "refund"],
    "legal": ["liability", "jurisdiction", "indemnify", "arbitration"],
}


def detect_risks(text: str) -> Dict[str, Any]:
    risks = {}
    for category, words in RISK_KEYWORDS.items():
        found = [w for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)]
        if found:
            risks[category] = found
    return risks


# --- API endpoint: Analyze document or URL ---
@app.post("/analyze")
async def analyze(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    text = ""

    if file:
        text = extract_text(file)
    elif url:
        text = extract_from_url(url)
    else:
        return {"error": "No input provided."}

    if not text.strip():
        return {"error": "Could not extract text."}

    # Get summarizer and sentiment models (lazy load)
    summarizer_model = get_summarizer()
    sentiment_model = get_sentiment_analyzer()

    # Summarize a limited portion for performance
    short_text = text[:2000]
    summary = summarizer_model(short_text, max_length=120, min_length=40, do_sample=False)[0]["summary_text"]

    # Analyze sentiment
    sentiment = sentiment_model(summary)[0]

    # Detect potential risks
    risks = detect_risks(text)

    return {
        "summary": summary,
        "sentiment": sentiment,
        "risks_detected": risks,
        "length": len(text),
    }

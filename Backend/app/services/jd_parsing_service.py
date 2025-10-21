# backend/app/services/jd_parsing_service.py
import os
import json
import mimetypes
from pathlib import Path
from datetime import datetime
import tempfile
import re

import google.generativeai as genai
from supabase import Client
import docx2txt
import fitz  # ✅ Import PyMuPDF
from app.config import settings

# --- MODIFIED FUNCTION ---
def extract_text(path: Path) -> str:
    """
    Extracts text from various file types, using PyMuPDF for PDFs
    to preserve formatting and line breaks.
    """
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".docx":
        return docx2txt.process(str(path)) or ""
    elif ext == ".pdf":
        # ✅ SWITCHED to PyMuPDF (fitz) for superior layout preservation
        full_text = ""
        with fitz.open(path) as doc:
            for page in doc:
                full_text += page.get_text()
        return full_text.strip()
    raise ValueError(f"Unsupported file type: {ext}")


def _normalize_key_requirements(value):
    """
    Normalize key_requirements returned by the model into a Python list of short strings.
    Accepts:
      - list -> returns cleaned list
      - JSON string representing list -> parses and returns list
      - plain string -> splits by newlines or commas and returns list
      - empty/None -> returns []
    """
    if not value:
        return []

    # If it's already a list
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        # Try parsing as JSON first (e.g. '["Python","SQL"]')
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                items = parsed
            else:
                # Fallback to splitting
                items = [value]
        except Exception:
            # split on newlines or commas
            if "\n" in value:
                items = [line.strip() for line in value.splitlines() if line.strip()]
            else:
                items = [part.strip() for part in value.split(",") if part.strip()]
    else:
        # Unknown type -> coerce to string and split
        items = [str(value).strip()]

    # Final cleanup: ensure all items are short strings, dedupe while preserving order
    seen = set()
    cleaned = []
    for it in items:
        if it is None:
            continue
        s = str(it).strip()
        if not s:
            continue
        # Normalize whitespace
        s = re.sub(r"\s+", " ", s).strip()
        if s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    return cleaned


def _strip_experience_from_requirement(req: str) -> str:
    """
    Remove experience-related phrases from a requirement string while preserving the skill/technology.
    Examples:
      - "3+ years Python" -> "Python"
      - "Experience with AWS and Docker" -> "AWS and Docker"
      - "5 years of experience in Java" -> "Java"
      - "Experience in machine learning" -> "machine learning"
    If removing experience phrases results in empty string, return empty string.
    """
    if not req:
        return ""

    s = req.strip()

    # Lowercase copy for pattern detection but preserve original for final extraction
    s_lower = s.lower()

    # Common experience words/phrases to remove
    # We'll attempt to remove different patterns while preserving the rest.
    # 1) Remove explicit numeric ranges like "3+ years", "2-4 years", "5 years"
    s = re.sub(r'\b\d+\s*\+\s*(years|yrs|year)\b', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r'\b\d+\s*-\s*\d+\s*(years|yrs|year)\b', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r'\b\d+\s*(years|yrs|year)\b', ' ', s, flags=re.IGNORECASE)

    # 2) Remove phrases like "x years of experience", "years of experience"
    s = re.sub(r'\b\d+\s*(?:\+)?\s*(years|yrs|year)\s+of\s+experience\b', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r'\b(years|yrs|experience|experience with|experience in|with experience of|with experience)\b', ' ', s, flags=re.IGNORECASE)

    # 3) Remove common 'y/o' notation like '3y/o' or '3 y/o'
    s = re.sub(r'\b\d+\s*y\/o\b', ' ', s, flags=re.IGNORECASE)

    # 4) Remove leading/trailing punctuation and excessive whitespace
    s = re.sub(r'[;:\-\(\)\[\]]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    # If the result contains only words like 'experience' or empty, return empty
    if not s or re.fullmatch(r'(experience|years|yrs|year|\+|-)+', s.strip(), flags=re.IGNORECASE):
        return ""

    # Additional defensive removal: if original req started with words like "experience" or "minimum", strip them
    s = re.sub(r'^(minimum|required|experience|required:)\s+', '', s, flags=re.IGNORECASE).strip()

    # Final trim
    s = s.strip(" ,.-")
    return s


def parse_jd_text(text: str) -> dict:
    """
    Calls the Google Gemini API to parse text and normalizes the response.
    Extracted fields:
      - location (string)
      - job_type (one of the allowed set or empty string)
      - experience_required (string)
      - jd_parsed_summary (string)
      - role (string)
      - key_requirements (list of short strings) -- note: experience-related text removed
    """
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # --- START: CORRECTION ---
        # The model name has been updated to the latest stable version.
        model = genai.GenerativeModel('gemini-2.5-flash')
        # --- END: CORRECTION ---

        prompt = f"""You are an expert job description parser. Extract the following fields from the provided job description text:

- role: Short job title (e.g. 'Senior Backend Engineer', 'Data Scientist') if present; else null/empty
- location: City/State/Country if present; else null/empty
- job_type: One of ['Full Time', 'Part Time', 'Internship', 'Contract'] if you can infer, else null/empty
- experience_required: Return as short free text, e.g. '2-3 years', '5+ years', or null/empty
- jd_parsed_summary: 2-4 sentence summary capturing the role, seniority, key responsibilities, and core skills.
- key_requirements: A short array/list of the most important requirements or qualifications (each as a short string), e.g. ["Python", "SQL", "Experience with AWS"].

IMPORTANT: Do NOT include experience durations, numeric year ranges, or the word "experience" inside key_requirements.
All experience/years MUST go into the `experience_required` field only. If a requirement mentions experience, extract the skill itself (for example "3+ years Python" -> "Python"; "Experience with AWS" -> "AWS"). Return key_requirements as an array of short skill/requirement strings WITHOUT any experience text.

If a field is not present, return it as an empty string for scalar fields or an empty array for key_requirements.
Return strictly as compact JSON with keys: role, location, job_type, experience_required, jd_parsed_summary, key_requirements.

Job Description Text:
---
{text[:120000]}
---"""

        response = model.generate_content(prompt)
        
        content = response.text.strip()
        # strip possible markdown fences
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)

        normalized_data = {
            "role": (data.get("role") or "").strip() if isinstance(data.get("role"), str) else (str(data.get("role")).strip() if data.get("role") is not None else ""),
            "location": (data.get("location") or "").strip(),
            "job_type": (data.get("job_type") or "").strip(),
            "experience_required": (data.get("experience_required") or "").strip(),
            "jd_parsed_summary": (data.get("jd_parsed_summary") or "").strip(),
            "key_requirements_raw": data.get("key_requirements") if "key_requirements" in data else None,
        }

        # Normalize job_type
        allowed_job_types = {"Full Time", "Part Time", "Internship", "Contract"}
        if normalized_data["job_type"] not in allowed_job_types:
            normalized_data["job_type"] = ""

        # Normalize key_requirements into a list of strings
        key_reqs = _normalize_key_requirements(normalized_data.pop("key_requirements_raw"))

        # Remove/strip any experience mentions from individual key requirements
        cleaned_key_reqs = []
        seen = set()
        for kr in key_reqs:
            stripped = _strip_experience_from_requirement(kr)
            if not stripped:
                continue
            # dedupe preserving order
            if stripped.lower() in seen:
                continue
            seen.add(stripped.lower())
            cleaned_key_reqs.append(stripped)

        normalized_data["key_requirements"] = cleaned_key_reqs

        return normalized_data

    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        raise


# --- MODIFIED FUNCTION ---
def process_jd_file(supabase: Client, file_path: Path, user_id: str) -> dict:
    """
    Processes a JD file:
    1. Extracts raw text with formatting preserved using PyMuPDF.
    2. Calls an AI model to parse the raw text into structured data.
    3. Saves the original file to storage.
    4. Inserts both the raw text and the parsed data into the database.
    """
    text = extract_text(file_path)
    if not text.strip():
        raise ValueError("No text could be extracted from the JD file.")

    # Get structured data from the AI parser
    parsed_data = parse_jd_text(text)

    # Upload the original file to Supabase storage
    bucket = "jds"
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    object_name = f"{user_id}/{ts}_{file_path.name}"
    
    with open(file_path, "rb") as f:
        content_type, _ = mimetypes.guess_type(file_path.name)
        supabase.storage.from_(bucket).upload(
            path=object_name, 
            file=f, 
            file_options={"contentType": content_type or "application/octet-stream"}
        )

    # Prepare the complete row for insertion into the 'jds' table
    row = {
        "user_id": user_id,
        "file_url": object_name,
        # ✅ Add the full, unprocessed text here
        "jd_text": text, 
        # Add the AI-parsed fields
        "location": parsed_data.get("location") or None,
        "job_type": parsed_data.get("job_type") or None,
        "experience_required": parsed_data.get("experience_required") or None,
        "jd_parsed_summary": parsed_data.get("jd_parsed_summary") or None,
        "role": parsed_data.get("role") or None,
        "key_requirements": parsed_data.get("key_requirements") or None,
    }
    
    # Execute the insert query
    res = supabase.table("jds").insert(row).execute()
    
    if not res.data:
        raise RuntimeError(f"Supabase insert error: No data returned after insert.")
        
    return res.data[0]
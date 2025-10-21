# backend/app/services/resume_parsing_service.py
import os
import json
import mimetypes
from pathlib import Path
from datetime import datetime
import tempfile
import re

# --- START: MODIFICATION ---
# Replaced OpenAI with the Gemini client and imported settings
import google.generativeai as genai
from app.config import settings
# --- END: MODIFICATION ---

from supabase import Client
import docx2txt
from pypdf import PdfReader

# --- Text Extraction Logic (This is your original code, UNCHANGED) ---
def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".docx":
        return docx2txt.process(str(path)) or ""
    elif ext == ".pdf":
        text_parts = []
        with open(path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts).strip()
    raise ValueError(f"Unsupported file type: {ext}")

# --- START: MODIFIED SECTION ---
# This is the only section that has been changed to use the Gemini API.

def parse_resume_text(text: str) -> dict:
    """
    Calls the Google Gemini API to parse resume text.
    This version includes robust JSON extraction to handle imperfect model output.
    """
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""You are an expert resume parser. Extract a comprehensive JSON profile from the resume text.

Return strictly valid JSON with these top-level keys:
- person_name: string (best guess, full name; empty if unknown)
- role: string (current or most recent role title; empty if unknown)
- company: string (current or most recent company; empty if unknown)
- profile_url: string (LinkedIn or personal site if present; empty if unknown)
- json_content: object with detailed fields.

Rules:
- Use empty strings, empty arrays, or nulls where information is missing.
- Do not invent data; infer conservatively from the text.

Resume Text:
---
{text[:120000]}
---"""

        response = model.generate_content(prompt)
        content = response.text.strip()

        # --- START: ROBUST JSON EXTRACTION ---
        # Use a regular expression to find the JSON block, even with markdown backticks
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Fallback for cases where there are no backticks
            json_str = content[content.find('{'):content.rfind('}')+1]
        
        return json.loads(json_str)
        # --- END: ROBUST JSON EXTRACTION ---

    except Exception as e:
        print(f"Error during Gemini API call for resume: {e}")
        raise

# --- END: MODIFIED SECTION ---


# --- This is your original process_resume_file function, modified to remove the OpenAI client ---
def process_resume_file(supabase: Client, file_path: Path, user_id: str, jd_id: str) -> dict:
    text = extract_text(file_path)
    if not text.strip():
        raise ValueError(f"No text could be extracted from the resume: {file_path.name}")

    # This now calls our modified Gemini function
    parsed_data = parse_resume_text(text)

    # The rest of your logic for uploading and storing remains the same.
    bucket = "resumes"
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    object_name = f"{user_id}/{ts}_{file_path.name}"
    
    with open(file_path, "rb") as f:
        content_type, _ = mimetypes.guess_type(file_path.name)
        supabase.storage.from_(bucket).upload(
            path=object_name, 
            file=f, 
            file_options={"contentType": content_type or "application/octet-stream"}
        )

    row = {
        "jd_id": jd_id,
        "user_id": user_id,
        "file_url": object_name,
        "json_content": parsed_data.get("json_content") or {},
        "person_name": (parsed_data.get("person_name") or "").strip() or None,
        "role": (parsed_data.get("role") or "").strip() or None,
        "company": (parsed_data.get("company") or "").strip() or None,
        "profile_url": (parsed_data.get("profile_url") or "").strip() or None,
    }
    
    # --- THIS IS THE FIX ---
    # Changed table name from "resumes" to "resume" to match the database schema.
    res = supabase.table("resume").insert(row).execute()
    # --- END OF FIX ---
    
    if not res.data:
        raise RuntimeError(f"Supabase insert error: No data returned after insert.")
        
    return res.data[0]
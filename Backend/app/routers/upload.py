import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List
import tempfile
from pathlib import Path

from app.dependencies import get_current_user, get_supabase_client
from app.services.jd_parsing_service import process_jd_file
from app.services.resume_parsing_service import extract_text, parse_resume_text
from app.models.user import User
from app.config import settings
# Import the async task
from app.worker import parse_jd_async_task

router = APIRouter(
    prefix="/upload",
    tags=["Upload & Parse"],
)

# Limit for bulk uploads to ensure server stability
MAX_BATCH_SIZE = 3

# This endpoint for JD uploads is preserved and remains unchanged.
@router.post("/jd")
async def upload_jd(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        result = process_jd_file(
            supabase=supabase,
            file_path=tmp_path,
            user_id=str(current_user.id)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

# This endpoint now correctly parses resumes and saves them to the 'resume' table.
@router.post("/resumes")
async def upload_resumes(
    files: List[UploadFile] = File(...),
    jd_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client)
):
    if not files:
        raise HTTPException(status_code=400, detail="No resume files provided.")

    rows_to_insert = []
    errors = []

    for file in files:
        if not file.filename:
            continue

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        try:
            # Step 1: Extract text and parse it
            text_content = extract_text(tmp_path)
            if not text_content.strip():
                raise ValueError("No text could be extracted from the resume.")
            
            parsed_data = parse_resume_text(text_content)

            # --- Step 2: Map parsed data to the 'resume' table schema ---
            row = {
                "resume_id": str(uuid.uuid4()),
                "jd_id": jd_id,
                "user_id": str(current_user.id),
                "json_content": json.dumps(parsed_data.get("json_content", {})),
                "person_name": parsed_data.get("person_name"),
                "role": parsed_data.get("role"),
                "company": parsed_data.get("company"),
                "profile_url": parsed_data.get("profile_url"),
                # file_url is left null as we are not storing the file itself in storage
            }
            rows_to_insert.append(row)

        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    # --- Step 3: Batch insert into the correct 'resume' table ---
    if rows_to_insert:
        try:
            supabase.table("resume").insert(rows_to_insert).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database insertion into 'resume' table failed: {e}")

    if not rows_to_insert and errors:
        raise HTTPException(status_code=500, detail={"message": "All resume uploads failed.", "errors": errors})

    return {"successful_uploads": len(rows_to_insert), "failed_uploads": errors}


# ==========================================
# NEW ENDPOINT: Bulk JD Uploads (Async)
# ==========================================
@router.post("/bulk-jds")
async def upload_bulk_jds(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Accepts multiple files and queues them for async processing via Celery.
    Enforced limit: 3 files max.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"Batch upload limit exceeded. To ensure system stability, please upload a maximum of {MAX_BATCH_SIZE} files at a time."
        )

    enqueued_files = []
    errors = []

    for file in files:
        try:
            # Read file content into memory to pass to Celery
            # JDs are usually small text/pdf files, so reading into memory is safe for small batches.
            content = await file.read()
            
            # Trigger the Celery task
            task = parse_jd_async_task.delay(
                file_content=content,
                filename=file.filename,
                user_id=str(current_user.id)
            )
            enqueued_files.append({"filename": file.filename, "task_id": task.id})
            
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {
        "message": f"Queued {len(enqueued_files)} files for background processing.",
        "queued_count": len(enqueued_files),
        "enqueued_files": enqueued_files,
        "errors": errors
    }
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from typing import List, Optional
import tempfile
from pathlib import Path
from pydantic import BaseModel
import os
from datetime import datetime, timedelta
from app.services.jd_parsing_service import process_jd_file, parse_jd_text
from app.dependencies import get_current_user, get_supabase_client
from app.models.user import User
from app.schemas.jd import JdSummary, JdUpdateContent
from app.services.jd_parsing_service import process_jd_file
from app.models.linkedin import LinkedIn
from app.schemas.linkedin import LinkedInCandidate
from app.dependencies import get_db, get_current_user
from sqlalchemy.orm import Session
from fastapi import Query
from datetime import datetime

router = APIRouter(
    tags=["Roles & JDs"],
)

class RoleStatusUpdate(BaseModel):
    status: str

@router.get("/", response_model=List[JdSummary])
async def get_user_jds(
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client),
    sort: Optional[str] = Query("created_at", description="Sort by 'created_at' or 'updated_at'"),
    filter: Optional[str] = Query("all", description="Filter by status: 'all', 'open', 'closed', 'de-prioritized'")
):
    """
    Fetches a list of all Job Descriptions (JDs) for the logged-in user.
    """
    try:
        # --- MODIFICATION: Added "jd_text" to the select query ---
        query = supabase.table("jds").select(
            "jd_id", "role", "location", "job_type", "experience_required",
            "jd_parsed_summary", "jd_text", "created_at", "updated_at", "key_requirements",
            "status", "candidates_liked", "candidates_contacted"
        ).eq("user_id", str(current_user.id))

        if filter and filter != "all":
            query = query.eq("status", filter)

        if sort:
            query = query.order(sort, desc=True)
        else:
            # Default sort if none is provided
            query = query.order("created_at", desc=True)

        response = query.execute()

        if not response.data:
            return []

        # Directly pass the data for Pydantic to validate
        roles_to_return = [JdSummary(**item) for item in response.data]
        return roles_to_return

    except Exception as e:
        print(f"Error fetching roles for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch roles.")


@router.post("/", response_model=JdSummary, status_code=201)
async def create_jd(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client)
):
    """
    Creates a new Job Description by uploading and parsing a file.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        new_jd_data = process_jd_file(
            supabase=supabase,
            file_path=Path(tmp_path),
            user_id=str(current_user.id)
        )
        return JdSummary(**new_jd_data)
    except Exception as e:
        print(f"An error occurred while creating a role: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink()

# --- NEW ENDPOINT: Allows editing of the full JD content ---
@router.patch("/{jd_id}", response_model=JdSummary)
def update_jd_content(
    jd_id: str,
    content_update: JdUpdateContent, # Uses the new schema with only jd_text
    supabase = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user)
):
    """
    Update the full text content (jd_text) of a specific Job Description.
    Re-parses the JD text and saves parsed fields (role, location, key_requirements, etc.)
    along with jd_text in one DB update.
    """
    try:
        # 1. Ownership Check (unchanged)
        owner_check = supabase.table("jds").select("user_id").eq("jd_id", jd_id).single().execute()

        if not owner_check.data:
            raise HTTPException(status_code=404, detail="Role not found")

        if str(owner_check.data.get("user_id")) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not authorized to update this role")

        # 2. Re-parse the JD text
        parsed_fields = parse_jd_text(content_update.jd_text)

        # Safety: ensure parsed_fields is a dict
        if not isinstance(parsed_fields, dict):
            parsed_fields = {}

        # 3. Build the update payload: always include jd_text and merge in parsed fields.
        # If parse_jd_text returns keys that don't match your DB columns, map them here.
        update_payload = {"jd_text": content_update.jd_text}
        # Merge parsed fields (parser keys should align with DB columns like 'role', 'location', 'key_requirements', etc.)
        update_payload.update(parsed_fields)

        # Example mapping (uncomment and adjust if your parser returns different key names):
        # mapped_payload = {
        #     "jd_text": content_update.jd_text,
        #     "role": parsed_fields.get("title") or parsed_fields.get("role"),
        #     "location": parsed_fields.get("location"),
        #     "key_requirements": parsed_fields.get("key_requirements") or parsed_fields.get("requirements"),
        #     # add other mappings as needed
        # }
        # update_payload = mapped_payload

        # 4. Update the row in Supabase
        update_response = supabase.table("jds").update(update_payload).eq("jd_id", jd_id).execute()

        # 5. Fetch the updated row to return full JdSummary (and updated_at)
        updated_row_response = supabase.table("jds").select("*").eq("jd_id", jd_id).single().execute()

        if not updated_row_response.data:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated JD content from database.")

        updated_data = updated_row_response.data
        if isinstance(updated_data, list):
             updated_data = updated_data[0]

        return JdSummary(**updated_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating content for role {jd_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred during content update.")


@router.patch("/{jd_id}/status", response_model=JdSummary)
def update_jd_status(
    jd_id: str,
    status_update: RoleStatusUpdate,
    supabase = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of a specific Job Description (Role).
    """
    try:
        owner_check = supabase.table("jds").select("user_id").eq("jd_id", jd_id).single().execute()

        if not owner_check.data:
            raise HTTPException(status_code=404, detail="Role not found")

        if str(owner_check.data.get("user_id")) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not authorized to update this role")

        # 1. Perform the update without requesting immediate return data
        # This is the most stable way to perform an update in Supabase-py
        update_response = supabase.table("jds").update(
            {"status": status_update.status}
        ).eq("jd_id", jd_id).execute()

        # 2. Check if the update succeeded and then manually fetch the updated row.
        # This guarantees we get the full JdSummary data, including the updated 'updated_at' timestamp.
        updated_row_response = supabase.table("jds").select("*").eq("jd_id", jd_id).single().execute()


        if not updated_row_response.data:
            # If the update occurred but we can't fetch the data (shouldn't happen if row exists)
            raise HTTPException(status_code=500, detail="Failed to retrieve updated role status from database.")

        updated_data = updated_row_response.data

        # We must adjust the retrieval to account for the Supabase single() structure
        # If .single() is used, updated_data is the dictionary itself, not a list of one item.
        if isinstance(updated_data, list):
            # If the Supabase client returns a list (e.g., if .single() wasn't used or behaves differently)
            updated_data = updated_data[0]

        return JdSummary(**updated_data)

    except HTTPException:
        raise # Re-raise 403/404 errors
    except Exception as e:
        print(f"Error updating status for role {jd_id}: {e}")
        # The HTTPException ensures the API returns the 500 status to the client
        raise HTTPException(status_code=500, detail="An internal server error occurred during status update.")

# --- NEW ENDPOINT: To delete a role ---
@router.delete("/{jd_id}", status_code=204)
def delete_jd(
    jd_id: str,
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client)
):
    """
    Deletes a specific Job Description (Role).
    """
    try:
        # 1. Ownership Check
        owner_check = supabase.table("jds").select("user_id").eq("jd_id", jd_id).single().execute()

        if not owner_check.data:
            raise HTTPException(status_code=404, detail="Role not found")

        if str(owner_check.data.get("user_id")) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not authorized to delete this role")

        # 2. Delete the row
        supabase.table("jds").delete().eq("jd_id", jd_id).execute()

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting role {jd_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred during role deletion.")
    
    
@router.get("/{jd_id}/linkedin_candidates", response_model=list[LinkedInCandidate])
def get_linkedin_candidates(
    jd_id: str,
    created_after: str = Query(..., description="ISO timestamp. Only return rows created after this time."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch LinkedIn-sourced candidates for a given JD created after a certain timestamp.

    Full route:
        GET /api/v1/roles/{jd_id}/linkedin_candidates?created_after=<ISO_TIMESTAMP>

    Behavior:
    - Only returns rows inserted after `created_after`
    - Includes a small tolerance window (default = 10 minutes)
    - Filters by current user + JD
    """
    try:
        # Parse ISO 8601 timestamp safely
        try:
            created_after_dt = datetime.fromisoformat(created_after.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ISO datetime format for created_after")

        # Configurable tolerance (default = 10 minutes)
        TOLERANCE_MINUTES = int(os.getenv("LINKEDIN_FETCH_TOLERANCE_MINUTES", "10"))
        cutoff_time = created_after_dt - timedelta(minutes=TOLERANCE_MINUTES)

        # Query the LinkedIn table
        results = (
            db.query(LinkedIn)
            .filter(LinkedIn.jd_id == jd_id)
            .filter(LinkedIn.user_id == current_user.id)
            .filter(LinkedIn.created_at >= cutoff_time)
            .order_by(LinkedIn.created_at.desc())
            .all()
        )

        # Return an empty list instead of raising an error if no results
        return results or []

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] get_linkedin_candidates failed for JD {jd_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch LinkedIn candidates.")
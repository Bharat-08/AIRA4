from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from typing import List, Optional
import tempfile
from pathlib import Path
from pydantic import BaseModel
import os
from datetime import datetime, timedelta
from app.services.jd_parsing_service import process_jd_file, parse_jd_text
from app.dependencies import get_current_user, get_supabase_client, get_db
from app.models.user import User
from app.schemas.jd import JdSummary, JdUpdateContent
from app.services.jd_parsing_service import process_jd_file
from app.models.linkedin import LinkedIn
from app.schemas.linkedin import LinkedInCandidate
from sqlalchemy.orm import Session
from sqlalchemy import func, asc, desc
from app.models.jd import JD
from app.models.candidate import RankedCandidate

router = APIRouter(
    tags=["Roles & JDs"],
)

class RoleStatusUpdate(BaseModel):
    status: str

@router.get("/", response_model=List[JdSummary])
async def get_user_jds(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    sort: Optional[str] = Query("created_at", description="Sort by 'created_at' or 'updated_at'"),
    order: Optional[str] = Query("desc", description="Order direction: 'asc' or 'desc'"),
    filter: Optional[str] = Query("all", description="Filter by status: 'all', 'open', 'closed', 'de-prioritized'")
):
    """
    Fetches a list of all Job Descriptions (JDs) for the logged-in user.
    Calculates actual counts for liked and contacted candidates.
    """
    try:
        # Subquery for counting liked candidates (favorite=True)
        liked_subquery = (
            db.query(func.count(RankedCandidate.rank_id))
            .filter(RankedCandidate.jd_id == JD.jd_id)
            .filter(RankedCandidate.favorite == True)
            .correlate(JD)
            .scalar_subquery()
        )

        # Subquery for counting contacted candidates (contacted=True)
        contacted_subquery = (
            db.query(func.count(RankedCandidate.rank_id))
            .filter(RankedCandidate.jd_id == JD.jd_id)
            .filter(RankedCandidate.contacted == True)
            .correlate(JD)
            .scalar_subquery()
        )

        # Main query selecting JD and the computed counts
        query = db.query(
            JD,
            liked_subquery.label("real_liked_count"),
            contacted_subquery.label("real_contacted_count")
        ).filter(JD.user_id == current_user.id)

        # Apply filtering
        if filter and filter != "all":
            query = query.filter(JD.status == filter)

        # Apply sorting
        # Determine which column to sort by
        if sort == "updated_at":
            sort_column = JD.updated_at
        else:
            sort_column = JD.created_at

        # Apply direction
        if order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        results = query.all()

        # Convert SQLAlchemy objects + counts to Pydantic models
        roles_to_return = []
        for jd_obj, liked_count, contacted_count in results:
            # Create a dictionary from the SQLAlchemy object
            jd_dict = {c.name: getattr(jd_obj, c.name) for c in jd_obj.__table__.columns}
            
            # --- FIX: Convert UUIDs to strings to satisfy Pydantic validation ---
            if jd_dict.get("jd_id"):
                jd_dict["jd_id"] = str(jd_dict["jd_id"])
            if jd_dict.get("user_id"):
                jd_dict["user_id"] = str(jd_dict["user_id"])
            
            # Override the static counts with the calculated ones
            jd_dict["candidates_liked"] = liked_count or 0
            jd_dict["candidates_contacted"] = contacted_count or 0
            
            roles_to_return.append(JdSummary(**jd_dict))

        return roles_to_return

    except Exception as e:
        # Improved error logging to see the specific validation error
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

        # 3. Build the update payload
        update_payload = {"jd_text": content_update.jd_text}
        update_payload.update(parsed_fields)

        # --- FIX: Manually update updated_at timestamp ---
        update_payload["updated_at"] = datetime.now().isoformat()

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

        # 1. Perform the update
        # --- FIX: Also update updated_at when status changes ---
        update_response = supabase.table("jds").update(
            {
                "status": status_update.status,
                "updated_at": datetime.now().isoformat()
            }
        ).eq("jd_id", jd_id).execute()

        # 2. Fetch updated row
        updated_row_response = supabase.table("jds").select("*").eq("jd_id", jd_id).single().execute()


        if not updated_row_response.data:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated role status from database.")

        updated_data = updated_row_response.data

        if isinstance(updated_data, list):
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
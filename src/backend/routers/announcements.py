"""
Announcements router for managing school announcements
"""

from fastapi import APIRouter, HTTPException, Query, Header
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from ..database import announcements_collection, teachers_collection
from bson import ObjectId
from bson.errors import InvalidId
import logging

router = APIRouter(prefix="/announcements", tags=["announcements"])

logger = logging.getLogger(__name__)


def verify_authenticated_user(username: Optional[str]) -> str:
    """
    Verify that the user is authenticated by checking if username exists in database.
    Returns the username if valid, raises HTTPException otherwise.
    """
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    return username


class AnnouncementCreate(BaseModel):
    """Model for creating a new announcement"""
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str
    created_by: str


class AnnouncementUpdate(BaseModel):
    """Model for updating an announcement"""
    message: Optional[str] = Field(None, min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: Optional[str] = None


@router.get("")
async def get_announcements(active_only: bool = Query(False)):
    """
    Get all announcements or only active ones.
    Active announcements are those within their date range.
    """
    try:
        announcements = list(announcements_collection.find({}))
        
        # Convert ObjectId to string for JSON serialization
        for announcement in announcements:
            if "_id" in announcement:
                announcement["id"] = str(announcement["_id"])
                del announcement["_id"]
        
        # Filter active announcements if requested
        if active_only:
            current_date = datetime.now().date().isoformat()
            active_announcements = []
            
            for announcement in announcements:
                start_date = announcement.get("start_date")
                expiration_date = announcement.get("expiration_date")
                
                # Check if announcement is within date range
                is_started = not start_date or start_date <= current_date
                is_not_expired = expiration_date >= current_date
                
                if is_started and is_not_expired:
                    active_announcements.append(announcement)
            
            return active_announcements
        
        return announcements
    except Exception as e:
        logger.exception(f"Error fetching announcements: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch announcements")


@router.post("")
async def create_announcement(announcement: AnnouncementCreate, username: Optional[str] = Header(None, alias="X-Username")):
    """
    Create a new announcement. Requires authentication.
    """
    # Verify user is authenticated
    verify_authenticated_user(username)
    
    try:
        # Validate dates
        if announcement.start_date:
            try:
                datetime.fromisoformat(announcement.start_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
        
        try:
            datetime.fromisoformat(announcement.expiration_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiration_date format. Use YYYY-MM-DD")
        
        # Check that expiration is after start (if start is provided)
        if announcement.start_date and announcement.expiration_date:
            if announcement.expiration_date < announcement.start_date:
                raise HTTPException(
                    status_code=400,
                    detail="Expiration date must be after start date"
                )
        
        # Create announcement document
        announcement_doc = {
            "message": announcement.message,
            "start_date": announcement.start_date,
            "expiration_date": announcement.expiration_date,
            "created_by": announcement.created_by,
            "created_at": datetime.now().isoformat()
        }
        
        result = announcements_collection.insert_one(announcement_doc)
        
        # Return created announcement with id
        created_announcement = announcement_doc.copy()
        created_announcement["id"] = str(result.inserted_id)
        
        return created_announcement
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to create announcement")


@router.put("/{announcement_id}")
async def update_announcement(announcement_id: str, announcement: AnnouncementUpdate, username: Optional[str] = Header(None, alias="X-Username")):
    """
    Update an existing announcement. Requires authentication.
    """
    # Verify user is authenticated
    verify_authenticated_user(username)
    
    try:
        # Convert string ID to ObjectId
        try:
            obj_id = ObjectId(announcement_id)
        except (InvalidId, ValueError):
            raise HTTPException(status_code=400, detail="Invalid announcement ID format")
        
        # Get existing announcement to merge with updates
        existing = announcements_collection.find_one({"_id": obj_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Build update document with only provided fields
        update_doc = {}
        if announcement.message is not None:
            update_doc["message"] = announcement.message
        if announcement.start_date is not None:
            try:
                datetime.fromisoformat(announcement.start_date)
                update_doc["start_date"] = announcement.start_date
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
        if announcement.expiration_date is not None:
            try:
                datetime.fromisoformat(announcement.expiration_date)
                update_doc["expiration_date"] = announcement.expiration_date
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid expiration_date format. Use YYYY-MM-DD")
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Validate date logic: expiration must be after start
        final_start_date = update_doc.get("start_date", existing.get("start_date"))
        final_expiration_date = update_doc.get("expiration_date", existing.get("expiration_date"))
        
        if final_start_date and final_expiration_date:
            if final_expiration_date < final_start_date:
                raise HTTPException(
                    status_code=400,
                    detail="Expiration date must be after start date"
                )
        
        # Update the announcement
        result = announcements_collection.update_one(
            {"_id": obj_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Return updated announcement
        updated = announcements_collection.find_one({"_id": obj_id})
        if updated:
            updated["id"] = str(updated["_id"])
            del updated["_id"]
        
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to update announcement")


@router.delete("/{announcement_id}")
async def delete_announcement(announcement_id: str, username: Optional[str] = Header(None, alias="X-Username")):
    """
    Delete an announcement. Requires authentication.
    """
    # Verify user is authenticated
    verify_authenticated_user(username)
    
    try:
        # Convert string ID to ObjectId
        try:
            obj_id = ObjectId(announcement_id)
        except (InvalidId, ValueError):
            raise HTTPException(status_code=400, detail="Invalid announcement ID format")
        
        result = announcements_collection.delete_one({"_id": obj_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        return {"message": "Announcement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete announcement")

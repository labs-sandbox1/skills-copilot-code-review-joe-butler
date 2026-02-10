"""
Announcements router for managing school announcements
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from ..database import announcements_collection
import logging

router = APIRouter(prefix="/announcements", tags=["announcements"])

logger = logging.getLogger(__name__)


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
        logger.error(f"Error fetching announcements: {e}")
        return []


@router.post("")
async def create_announcement(announcement: AnnouncementCreate):
    """
    Create a new announcement. Requires authentication.
    """
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
async def update_announcement(announcement_id: str, announcement: AnnouncementUpdate):
    """
    Update an existing announcement. Requires authentication.
    """
    try:
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
        
        # Update the announcement
        result = announcements_collection.update_one(
            {"_id": announcement_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        # Return updated announcement
        updated = announcements_collection.find_one({"_id": announcement_id})
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
async def delete_announcement(announcement_id: str):
    """
    Delete an announcement. Requires authentication.
    """
    try:
        result = announcements_collection.delete_one({"_id": announcement_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        
        return {"message": "Announcement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting announcement: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete announcement")

from fastapi import APIRouter, HTTPException, Depends
from firebase_admin import firestore
import asyncio
from auth import get_current_user_data

router = APIRouter(prefix="/recent-interviews", tags=["Recent Interviews"])
db = firestore.client()

@router.get("/{interview_id}")
async def get_recent_interview_details(interview_id: str, user_data: dict = Depends(get_current_user_data)):
    interview_ref = db.collection('interviews').document(interview_id)
    interview_doc = await asyncio.to_thread(interview_ref.get)
    if not interview_doc.exists:
        raise HTTPException(status_code=404, detail="Interview not found.")
    interview_data = interview_doc.to_dict()
    if interview_data.get('user_uid') != user_data['uid']:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    # Return only the relevant fields
    return {
        "role": interview_data.get('role'),
        "experience": interview_data.get('experience'),
        "date": interview_data.get('created_at', ''),
        "questions": interview_data.get('questions', []),
        "answers": interview_data.get('answers', []),
        "score": interview_data.get('score', None),
        "overall_feedback": interview_data.get('overall_feedback', None)
    } 
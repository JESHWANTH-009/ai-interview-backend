# ai-interview-coach-backend/routes/user.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from firebase_admin import firestore
# Corrected import path: assuming auth.py is one level up (in backend root)
from auth import get_current_user_data 

# Get Firestore client instance
db = firestore.client()

router = APIRouter()

class UserProfile(BaseModel):
    uid: str
    email: str
    display_name: str | None = None
    created_at: str # Use string for datetime from Firestore for simplicity in Pydantic

@router.get("/profile", response_model=UserProfile)
async def get_user_profile(email: str):
    users_ref = db.collection('users')
    query = users_ref.where("email", "==", email).limit(1)
    results = query.get()

    if not results:
        raise HTTPException(status_code=404, detail="User not found.")

    user_doc = results[0]
    profile_data = user_doc.to_dict()
    profile_data['uid'] = user_doc.id  # Get UID from document ID

    # Convert Firestore Timestamp to ISO string
    if 'created_at' in profile_data and hasattr(profile_data['created_at'], 'isoformat'):
        profile_data['created_at'] = profile_data['created_at'].isoformat()
    return UserProfile(**profile_data)

# @router.get('/interview/{interview_id}')
# async def get_interview_by_id(interview_id: str, user_data: dict = Depends(get_current_user_data)):
#     interview_ref = db.collection('interviews').document(interview_id)
#     interview_doc = interview_ref.get()
#     if not interview_doc.exists:
#         raise HTTPException(status_code=404, detail='Interview not found')
#     interview = interview_doc.to_dict()
#     if interview.get('user_uid') != user_data['uid']:
#         raise HTTPException(status_code=403, detail='Not authorized to view this interview')
#     # Only return safe fields
#     return {
#         'id': interview_id,
#         'role': interview.get('role'),
#         'experience': interview.get('experience'),
#         'num_questions': interview.get('num_questions'),
#         'is_active': interview.get('is_active'),
#         'created_at': interview.get('created_at'),
#         'ended_at': interview.get('ended_at'),
#     }
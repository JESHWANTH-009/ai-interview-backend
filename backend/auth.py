# ai-interview-coach-backend/auth.py
import firebase_admin
from firebase_admin import auth, credentials, firestore
from fastapi import HTTPException, status, Depends, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Define the auth router
auth_router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# Firebase Initialization (only once)
if not firebase_admin._apps:
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH")#firebase file
    if not service_account_path or not os.path.exists(service_account_path):
        raise FileNotFoundError(
            f"Firebase service account key file not found at {service_account_path}. "
            "Please ensure FIREBASE_SERVICE_ACCOUNT_KEY_PATH is set correctly in your .env file."
        )
    cred = credentials.Certificate(service_account_path)# certificate object is created 
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized successfully.")

# Get Firestore client
db = firestore.client()

#HTTPBearer
bearer_scheme = HTTPBearer()

# Extract and verify Firebase token from Bearer
async def get_current_user_data(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token. Error: {e}"
        )

#Used in frontend to verify token after Firebase login
class Token(BaseModel):
    idToken: str

@auth_router.post("/verify-token")
async def verify_token(token: Token):
    try:
        decoded_token = auth.verify_id_token(token.idToken)
        uid = decoded_token['uid']
        email = decoded_token.get('email')

        # Check or create user profile
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            user_ref.set({
                "uid": uid,
                "email": email,
                "display_name": decoded_token.get('name'),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print(f"New user profile created for UID: {uid}")

        return {"uid": uid, "email": email, "message": "Token verified successfully"}

    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

#Signup user from Swagger /signup route
class UserCreate(BaseModel):
    email: str
    password: str
    display_name: str | None = None

@auth_router.post("/signup")
async def signup_user(user_data: UserCreate):
    try:
        user = auth.create_user(email=user_data.email, password=user_data.password)
        uid = user.uid
        email = user.email
        display_name = user_data.display_name or None

        # Create Firestore profile
        user_ref = db.collection('users').document(uid)
        user_ref.set({
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "created_at": firestore.SERVER_TIMESTAMP
        })

        return {"uid": uid, "email": email, "message": "User created successfully "}
    except Exception as e:
        print(f"Signup failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

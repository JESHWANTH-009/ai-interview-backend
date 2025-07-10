from fastapi import FastAPI
from routes.user import router as user_router
from routes.interview import router as interview_router
from fastapi.middleware.cors import CORSMiddleware
from auth import auth_router
from dotenv import load_dotenv, find_dotenv
from routes.dashboard import router as dashboard_router
from routes.recent_interviews import router as recent_interviews_router
from fastapi.openapi.utils import get_openapi#to customize openapi
import os
load_dotenv(find_dotenv(".env"))
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173","http://127.0.0.1:5173","https://interview-coach-two.vercel.app","https://polite-grass-08411f31e.1.azurestaticapps.net"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Custom OpenAPI for Bearer token in Swagger UI to manage the authorization button that to be takken the token and verify
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="AI Interview Coach API" ,#title to show 
        version="1.0.0",
        description="API with Firebase Authentication",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema
app.openapi = custom_openapi #overrides the default fastapi openapi generater with created

# Include your routes

app.include_router(auth_router) 
app.include_router(user_router,prefix="/user")
app.include_router(interview_router, tags=["Interview Flow"]) 
app.include_router(dashboard_router, prefix="/user", tags=["Dashboard"])
app.include_router(recent_interviews_router, tags=["Recent Interviews"])

@app.get("/")
async def read_root():
    """
    Root endpoint for the AI Interview Coach Backend.
    """
    return {"message": "Welcome to the AI Interview Coach Backend!"}
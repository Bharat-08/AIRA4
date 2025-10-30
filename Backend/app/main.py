# recruiter-platform/backend/app/main.py

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import auth, health, me, orgs, superadmin, favorites, upload, roles, search
from app.routers import pipeline
from app.routers import candidates

app = FastAPI(
    title="Recruiter Platform API",
    description="API for the multi-tenant recruiter platform.",
    version="0.1.0",
)

# --- CORS Middleware Configuration ---
origins = [
    settings.FRONTEND_BASE_URL,
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SessionMiddleware ---
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
)

# --- API Routers ---
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(upload.router)
app.include_router(orgs.router)
app.include_router(superadmin.router, prefix="/superadmin", tags=["Super Admin"])
app.include_router(favorites.router, tags=["Favorites"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(roles.router, prefix="/roles", tags=["Roles"])
app.include_router(pipeline.router)

# --- ADDED CANDIDATE ROUTER ---
# This line activates the new endpoints in app/routers/candidates.py
# The prefix="/candidates" and tags=["Candidates"] are already set in that file.
app.include_router(candidates.router)
# --- END OF ADD ---
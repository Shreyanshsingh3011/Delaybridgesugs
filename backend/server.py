"""DelayBridge — FastAPI server entrypoint."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from auth import seed_admin

# Routers
from routes_admin import router as admin_router
from routes_public import router as public_router


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("delaybridge")

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


app = FastAPI(title="DelayBridge API", version="0.1.0")

# Health route at /api/ (matches K8s ingress /api prefix)
health_router = APIRouter(prefix="/api")


@health_router.get("/")
async def root():
    return {
        "app": "DelayBridge",
        "version": "0.1.0",
        "status": "ok",
        "endpoints": {
            "auth": ["/api/auth/login", "/api/auth/logout", "/api/auth/me"],
            "sessions": ["/api/sessions", "/api/sessions/{id}", "/api/sessions/{id}/sheets", "/api/sessions/{id}/analyze"],
            "public": [
                "/api/public/{token}",
                "/api/public/{token}/flags",
                "/api/public/{token}/variances",
                "/api/public/{token}/correlations",
                "/api/public/{token}/dependencies",
                "/api/public/{token}/downstream/{email}",
                "/api/public/{token}/chat",
                "/api/public/{token}/chat/suggestions",
                "/api/public/{token}/onboarding",
                "/api/public/{token}/status",
                "/api/public/{token}/refresh",
                "/api/public/{token}/flag/{id}/acknowledge",
                "/api/public/{token}/flag/{id}/resolve",
                "/api/public/{token}/alerts",
                "/api/public/{token}/chat/history",
            ],
        },
        "demo_token": os.environ.get("DEMO_TOKEN", "demo-nit76-operations"),
    }


@health_router.get("/health")
async def health():
    return {"ok": True}


app.include_router(health_router)
app.include_router(admin_router)
app.include_router(public_router)


# CORS
origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    # Indexes
    try:
        await db.users.create_index("email", unique=True)
        await db.sessions.create_index("public_token", unique=True)
        await db.sessions.create_index("owner_id")
        await db.chat_logs.create_index("token")
        await db.alert_log.create_index("created_at")
    except Exception as e:
        logger.warning("Index creation issue: %s", e)
    await seed_admin(db)
    logger.info("DelayBridge ready. Demo token: %s", os.environ.get("DEMO_TOKEN"))


@app.on_event("shutdown")
async def on_shutdown():
    client.close()

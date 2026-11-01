"""FastAPI application for CogLayer.

Wires all protocols, repositories, and routers under /v1/assessment.
Enables CORS for Streamlit (localhost:8501) and iframe sandbox (null).

Requirements: R-005.6, design §3.4
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from coglayer.api.routers import (
    admin,
    brain_twin,
    coach,
    consent,
    daily_plan,
    ioi,
    onboarding,
    profile,
    projection,
    sessions,
    tasks,
)
from coglayer.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory creating the configured FastAPI application instance."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="CogLayer Assessment API",
        description="Cognitive coaching assessment layer - non-clinical.",
        version="0.1.0",
    )

    if settings is not None:
        from coglayer.api.deps import get_db_settings

        app.dependency_overrides[get_db_settings] = lambda: app_settings

    # Enable CORS for Streamlit and sandboxed iframe components (null origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",
            "http://127.0.0.1:8501",
            "null",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Combined assessment router under /v1/assessment prefix
    assessment_router = APIRouter(prefix="/v1/assessment")
    assessment_router.include_router(consent.router)
    assessment_router.include_router(sessions.router)
    assessment_router.include_router(tasks.router)
    assessment_router.include_router(profile.router)
    assessment_router.include_router(coach.router)
    assessment_router.include_router(admin.router)
    assessment_router.include_router(ioi.router)
    assessment_router.include_router(brain_twin.router)
    assessment_router.include_router(projection.router)
    assessment_router.include_router(daily_plan.router)
    assessment_router.include_router(onboarding.router)

    app.include_router(assessment_router)

    @app.get("/healthz")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "provider": app_settings.llm_provider}

    return app


# Default ASGI application instance for uvicorn
app = create_app()

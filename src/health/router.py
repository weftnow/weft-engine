from fastapi import APIRouter

from src.health.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness; this does not assert matching readiness."""
    return HealthResponse()

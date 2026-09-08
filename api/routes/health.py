from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health", summary="API health check")
def health() -> dict[str, str]:
    return {"status": "ok"}

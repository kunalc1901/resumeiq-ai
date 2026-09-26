from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Health check endpoint (public)."""
    return {"status": "ok"}
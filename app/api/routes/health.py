from fastapi import APIRouter

router = APIRouter()

@router.get("/readiness", include_in_schema=False)
async def readiness():
    return { "status": "ok" };

@router.get("/liveness", include_in_schema=False)
async def liveness():
    return { "status": "ok" };

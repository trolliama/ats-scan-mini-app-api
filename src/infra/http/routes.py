from fastapi import APIRouter

router = APIRouter()

# Deferred: POST /scans (202, BackgroundTasks, Depends(get_uow, verify_api_key))

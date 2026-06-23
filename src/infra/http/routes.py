from fastapi import APIRouter, BackgroundTasks, Depends, Request

from core.services.scan_service import create_scan, process_scan
from infra.db.unit_of_work import UoWContext
from infra.http.dependencies import get_uow, verify_api_key
from infra.http.schemas import CreateScanRequest, CreateScanResponse

router = APIRouter()


@router.post(
    "/scans",
    status_code=202,
    dependencies=[Depends(verify_api_key)],
    response_model=CreateScanResponse,
)
async def create_scan_route(
    body: CreateScanRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    uow: UoWContext = Depends(get_uow),
) -> CreateScanResponse:
    response = create_scan(uow, body)
    background_tasks.add_task(
        process_scan,
        str(body.scan_id),
        request.app.state.session_factory,
    )
    return response

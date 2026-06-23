from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import ScanStatus
from core.models import ATSScanResult


class CreateScanRequest(BaseModel):
    scan_id: UUID
    session_id: UUID
    file_key: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    bucket: str = Field(min_length=1)


class CreateScanResponse(BaseModel):
    scan_id: UUID
    status: ScanStatus


class WebhookProcessingPayload(BaseModel):
    scanId: str
    status: ScanStatus


class WebhookCompletedPayload(BaseModel):
    scanId: str
    status: ScanStatus
    atsScore: int
    jobTitleDetected: str | None
    result: ATSScanResult


class WebhookFailedPayload(BaseModel):
    scanId: str
    status: ScanStatus
    failureReason: str

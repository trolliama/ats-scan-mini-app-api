from uuid import uuid4

import factory

from core.enums import ATSCategoryKey, ATSIssueSeverity, CVContactType
from core.models import (
    ATSScanResult,
    ATSIssue,
    CVContactItem,
    CVPreview,
    ScanCreate,
)


class ScanCreateFactory(factory.Factory):
    class Meta:
        model = ScanCreate

    scan_id = factory.LazyFunction(uuid4)
    session_id = factory.LazyFunction(uuid4)
    file_key = "resumes/sess/file.pdf"
    bucket = "test-bucket"
    original_filename = "resume.pdf"


class CVPreviewFactory(factory.Factory):
    class Meta:
        model = CVPreview

    name = "Jane Doe"
    contact = factory.LazyFunction(
        lambda: [CVContactItem(type=CVContactType.EMAIL, value="jane@example.com")]
    )
    experience = factory.LazyFunction(list)
    education = factory.LazyFunction(list)


class ATSIssueFactory(factory.Factory):
    class Meta:
        model = ATSIssue

    id = "issue-1"
    category = "keywords"
    severity = ATSIssueSeverity.WARNING
    description = "Missing keyword"
    solution = "Add keyword"


class ATSScanResultFactory(factory.Factory):
    class Meta:
        model = ATSScanResult

    overall_score = 72
    category_scores = factory.LazyFunction(
        lambda: {key: 70 for key in ATSCategoryKey.all_keys()}
    )
    missing_keywords = ["kubernetes"]
    found_keywords = ["python"]
    issues = factory.LazyFunction(lambda: [ATSIssueFactory.build()])
    cv_preview = factory.SubFactory(CVPreviewFactory)

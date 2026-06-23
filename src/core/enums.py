from enum import StrEnum


class ScanStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ATSCategoryKey(StrEnum):
    KEYWORDS = "keywords"
    FORMATTING = "formatting"
    CONTENT = "content"
    PROFESSIONAL_EXPERIENCE = "professional_experience"
    HEADER_CONTACT = "header_contact"
    PROFESSIONAL_SUMMARY = "professional_summary"
    SKILLS = "skills"
    EDUCATION = "education"

    @classmethod
    def all_keys(cls) -> tuple[ATSCategoryKey, ...]:
        return tuple(cls)


class ATSIssueSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CVContactType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    LOCATION = "location"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    WEBSITE = "website"
    CUSTOM = "custom"

from io import BytesIO
from pathlib import PurePath

from markitdown import MarkItDown

from core.models import CVPreview

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx"})

_converter = MarkItDown()


def file_extension(filename: str | None) -> str:
    if not filename:
        return ""
    return PurePath(filename).suffix.lower()


def validate_resume_filename(filename: str | None) -> str:
    ext = file_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported resume format{f' ({ext})' if ext else ''}. "
            f"Supported formats: {supported}"
        )
    return ext


def extract_markdown_from_resume(content: bytes, filename: str) -> str:
    ext = validate_resume_filename(filename)
    result = _converter.convert_stream(
        BytesIO(content),
        file_extension=ext,
    )
    markdown = (result.text_content or "").strip()
    if not markdown:
        raise ValueError("Could not extract text from resume")
    return markdown


def extract_cv_preview(markdown: str) -> CVPreview:
    """Deferred: ATS scan worker — heuristic CV preview extraction."""
    raise NotImplementedError

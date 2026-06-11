from core.models import CVPreview
from ai.resume_parser import extract_cv_preview


def test_contains_required_fields_when_markdown_provided():
    """extract_cv_preview returns a CVPreview with all required model fields."""
    preview = extract_cv_preview("# Resume\n\nExperience section")

    assert isinstance(preview, CVPreview)
    assert hasattr(preview, "name")
    assert hasattr(preview, "headline")
    assert hasattr(preview, "contact")
    assert hasattr(preview, "summary")
    assert hasattr(preview, "experience")
    assert hasattr(preview, "education")
    assert hasattr(preview, "skills")


def test_returns_empty_name_string_when_stub():
    """P1 stub returns an empty string for name without network I/O."""
    preview = extract_cv_preview("Jane Doe\nSoftware Engineer")

    assert isinstance(preview.name, str)
    assert preview.name == ""
    assert preview.contact == []
    assert preview.experience == []
    assert preview.education == []

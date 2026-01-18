import pytest
from src.utils import derive_company_name, default_company_structure

def test_derive_company_name_basic():
    assert derive_company_name("https://www.google.com") == "Google"
    assert derive_company_name("http://example.org/path") == "Example"
    assert derive_company_name("https://sub.domain.co.uk") == "Sub"

def test_derive_company_name_wellness():
    assert derive_company_name("https://www.bluecrestwellness.com") == "Bluecrest Wellness"
    assert derive_company_name("https://mywellness.com") == "My Wellness"

def test_derive_company_name_empty():
    assert derive_company_name("") == "Company"
    assert derive_company_name(None) == "Company"

def test_default_company_structure_defaults():
    cfg = {}
    structure = default_company_structure(cfg, "TestCo", "http://test.co")
    
    assert structure["company_name"] == "TestCo"
    assert structure["url"] == "http://test.co"
    assert "preventive health" in structure["focus_keywords"]
    assert "health screening" in structure["focus_keywords"]

def test_default_company_structure_with_config():
    cfg = {
        "pipeline": {
            "keywords": ["AI", "Machine Learning"]
        }
    }
    structure = default_company_structure(cfg, "TechCo")
    
    assert structure["company_name"] == "TechCo"
    assert "ai" in structure["focus_keywords"]
    assert "machine learning" in structure["focus_keywords"]
    assert "preventive health" not in structure["focus_keywords"]

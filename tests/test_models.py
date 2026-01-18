import pytest
from src.models import CompanyContext

def test_company_context_initialization():
    ctx = CompanyContext(
        url="http://example.com",
        company_name="Example Corp",
        raw_summary="Raw summary",
        offer_summary="Offer summary",
        business_goals=["Goal 1", "Goal 2"],
        key_products=["Product A"],
        market_position="Leader",
        focus_keywords=["keyword1"]
    )
    
    assert ctx.url == "http://example.com"
    assert ctx.company_name == "Example Corp"
    assert len(ctx.business_goals) == 2

def test_company_context_as_prompt():
    ctx = CompanyContext(
        url="http://example.com",
        company_name="Example Corp",
        raw_summary="Raw",
        offer_summary="Great offers",
        business_goals=["Make money"],
        key_products=["Widget"],
        market_position="Top",
        focus_keywords=["alpha", "beta"]
    )
    
    prompt = ctx.as_prompt()
    
    assert "Company: Example Corp" in prompt
    assert "Company URL: http://example.com" in prompt
    assert "Offering Summary: Great offers" in prompt
    assert "Business Goals:" in prompt
    assert "- Make money" in prompt
    assert "Key Products/Services:" in prompt
    assert "- Widget" in prompt
    assert "Market Position: Top" in prompt
    assert "Focus Keywords: alpha, beta" in prompt

def test_company_context_as_prompt_minimal():
    ctx = CompanyContext(
        url="http://minimal.com",
        company_name="Min Corp",
        raw_summary="",
        offer_summary="",
        business_goals=[],
        key_products=[],
        market_position="",
        focus_keywords=[]
    )
    
    prompt = ctx.as_prompt()
    
    assert "Company: Min Corp" in prompt
    assert "Company URL: http://minimal.com" in prompt
    assert "Offering Summary" not in prompt
    assert "Business Goals" not in prompt
    assert "Key Products/Services" not in prompt
    assert "Market Position" not in prompt
    assert "Focus Keywords" not in prompt

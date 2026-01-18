from urllib.parse import urlparse
from typing import Dict, Any, List

def derive_company_name(url: str) -> str:
    if not url:
        return "Company"
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.replace("www.", "")
    base = host.split(".")[0].replace("-", " ")
    if "wellness" in base and " " not in base:
        base = base.replace("wellness", " wellness")
    return base.title() or "Company"

def default_company_structure(cfg: Dict[str, Any], company_name: str, url: str = "") -> Dict[str, Any]:
    keywords = cfg.get("pipeline", {}).get("keywords", [])
    focus_keywords = [kw.lower() for kw in keywords] or [
        "preventive health",
        "health screening",
        "diagnostics",
    ]
    return {
        "company_name": company_name,
        "url": url,
        "offer_summary": "Affordable, nationwide health screening and wellness packages for individuals and employers.",
        "business_goals": [
            "Expand preventive health screening reach across the UK",
            "Promote early detection services to employers and consumers",
            "Differentiate through clinical quality and customer experience",
        ],
        "key_products": [
            "Comprehensive health screening packages",
            "On-site corporate wellness clinics",
            "Remote diagnostic tests",
        ],
        "market_position": "Preventive health screening provider focused on proactive wellness.",
        "focus_keywords": focus_keywords,
    }

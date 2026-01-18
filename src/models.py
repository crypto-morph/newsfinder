from dataclasses import dataclass
from typing import List

@dataclass
class CompanyContext:
    url: str
    company_name: str
    raw_summary: str
    offer_summary: str
    business_goals: List[str]
    key_products: List[str]
    market_position: str
    focus_keywords: List[str]

    def as_prompt(self) -> str:
        lines = [f"Company: {self.company_name}", f"Company URL: {self.url}"]
        if self.offer_summary:
            lines.append(f"Offering Summary: {self.offer_summary}")
        if self.business_goals:
            lines.append("Business Goals:")
            lines.extend([f"- {goal}" for goal in self.business_goals])
        if self.key_products:
            lines.append("Key Products/Services:")
            lines.extend([f"- {product}" for product in self.key_products])
        if self.market_position:
            lines.append(f"Market Position: {self.market_position}")
        if self.focus_keywords:
            lines.append(
                "Focus Keywords: " + ", ".join(sorted(set(self.focus_keywords)))
            )
        return "\n".join(lines)

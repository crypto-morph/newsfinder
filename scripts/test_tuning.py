import logging
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.analysis.llm_client import OllamaClient
from src.settings import load_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_tuning")

def test_tuning():
    config = load_config("config.yaml")
    
    # Initialize client
    llm_conf = config.get("llm", {})
    client = OllamaClient(
        base_url=llm_conf.get("base_url", "http://localhost:11434"),
        model=llm_conf.get("model", "llama3.1:8b")
    )
    
    # Load Context
    context_path = config.get("storage", {}).get("context_cache", "logs/company_context.txt")
    if os.path.exists(context_path):
        with open(context_path, "r") as f:
            context = f.read()
    else:
        logger.error("Context file not found!")
        return

    # Test Cases based on verification failures
    test_cases = [
        {
            "title": "Plane Crash Incident",
            "text": """
            British man is only passenger to survive India plane crash.
            A British man was the only passenger to survive a plane crash in India that killed 18 people.
            The flight from Mumbai to Calcutta crashed shortly after takeoff.
            Emergency services rushed to the scene but found mostly wreckage.
            The survivor is being treated for burns in a local hospital.
            """
        },
        {
            "title": "Trademark Dispute",
            "text": """
            Hugo Boss gives Liverpool pet store 10 days to change name.
            Fashion giant Hugo Boss has issued a cease and desist to a small pet store in Liverpool called 'Hugo's Paws'.
            The lawyers claim the font and naming infringe on their trademark.
            The shop owner says they named it after their dog.
            Legal experts say this is a classic David vs Goliath trademark battle.
            """
        },
        {
            "title": "NHS Maternity Funding",
            "text": """
            Streeting accused of 'betrayal' over maternity funding plan.
            The Health Secretary faces criticism for delaying promised funding for NHS maternity units.
            Midwives say the system is at breaking point and needs urgent investment to ensure patient safety.
            The government argues that reform must come before cash.
            The opposition calls it a betrayal of mothers and babies across the UK.
            """
        },
        {
            "title": "Relevant: Private Blood Testing",
            "text": """
            Rise in demand for private blood tests as NHS waiting lists grow.
            More patients are turning to private providers for diagnostic blood tests.
            Companies like Randox and Bluecrest are seeing record booking numbers.
            Patients say they value the speed and convenience of getting a 'health MOT' without a GP referral.
            Doctors warn that private tests can sometimes lead to anxiety if results aren't interpreted correctly.
            """
        }
    ]
    
    print("\n=== RUNNING TUNING TESTS ===\n")
    
    for case in test_cases:
        print(f"Testing: {case['title']}...")
        result = client.analyze_article(case["text"], context=context)
        
        print(f"  Score: {result.get('relevance_score')}")
        print(f"  Reasoning: {result.get('relevance_reasoning')}")
        print(f"  Impact: {result.get('impact_score')}")
        print("-" * 40)

if __name__ == "__main__":
    test_tuning()

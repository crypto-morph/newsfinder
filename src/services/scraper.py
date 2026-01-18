import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def fetch_html(url: str, timeout: int = 10) -> str:
    """
    Fetches HTML content from a URL with a standard User-Agent.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        raise

def extract_section_by_keywords(soup: BeautifulSoup, keywords: List[str]) -> str:
    """
    Attempts to find a semantic section (section, div, p, article) containing
    one of the provided keywords. Returns the stripped text of the found section.
    """
    for keyword in keywords:
        # We look for tags that contain the keyword in their text
        # This is a heuristic and might need refinement
        section = soup.find(
            lambda tag: tag.name in {"section", "div", "p", "article"}
            and keyword in tag.get_text(strip=True).lower()
        )
        if section:
            return section.get_text(strip=True)
    return ""

def fetch_company_content(url: str) -> str:
    """
    Scrapes the main landing page and attempts to find an 'About' page.
    Returns combined text content optimized for LLM context.
    """
    if not url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (NewsFinder Context Profiler)"
    }
    
    combined_text = ""
    
    # 1. Scrape Landing Page
    try:
        logger.info(f"Scraping landing page: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Clean up
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=" ", strip=True)
        combined_text += f"--- LANDING PAGE ---\n{text[:5000]}\n\n" # Limit length
        
        # 2. Try to find "About" link
        about_link = None
        for a in soup.find_all("a", href=True):
            href = a['href'].lower()
            if "about" in href or "mission" in href:
                # Handle relative URLs
                if href.startswith("http"):
                    about_link = a['href']
                elif href.startswith("/"):
                    about_link = url.rstrip("/") + href
                else:
                    about_link = url.rstrip("/") + "/" + href
                break
        
        if about_link:
            logger.info(f"Found potential About page: {about_link}")
            try:
                resp_about = requests.get(about_link, headers=headers, timeout=10)
                if resp_about.status_code == 200:
                    soup_about = BeautifulSoup(resp_about.content, "html.parser")
                    for script in soup_about(["script", "style", "nav", "footer"]):
                        script.decompose()
                    about_text = soup_about.get_text(separator=" ", strip=True)
                    combined_text += f"--- ABOUT PAGE ---\n{about_text[:5000]}\n\n"
            except Exception as e:
                logger.warning(f"Failed to scrape About page {about_link}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        
    return combined_text

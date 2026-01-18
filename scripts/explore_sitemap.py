import requests
from bs4 import BeautifulSoup

def explore_sitemap(url):
    print(f"Fetching {url}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'xml')
        
        # Check if it's a sitemap index
        sitemaps = soup.find_all('sitemap')
        if sitemaps:
            print(f"Found {len(sitemaps)} sub-sitemaps.")
            for i, sm in enumerate(sitemaps):
                loc = sm.find('loc').text
                if i < 5:  # Print first 5
                    print(f"  Sample: {loc}")
        else:
            urls = soup.find_all('url')
            print(f"Found {len(urls)} URLs.")
            if urls:
                print(f"Sample: {urls[0].find('loc').text}")

    except Exception as e:
        print(f"Error: {e}")

def inspect_sitemap_dates(url):
    print(f"Inspecting {url}...")
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'xml')
        urls = soup.find_all('url')
        if urls:
            first = urls[0].find('loc').text
            last = urls[-1].find('loc').text
            print(f"  Count: {len(urls)}")
            print(f"  First: {first}")
            print(f"  Last:  {last}")
            
            # Try to extract date from first/last if possible to guess range
            # Heuristic: look for /YYYY/MM/
            import re
            date_pattern = r'/(\d{4})/(\d{2})/'
            
            m_first = re.search(date_pattern, first)
            m_last = re.search(date_pattern, last)
            
            if m_first: print(f"  First Date: {m_first.group(1)}-{m_first.group(2)}")
            if m_last: print(f"  Last Date:  {m_last.group(1)}-{m_last.group(2)}")

    except Exception as e:
        print(f"Error: {e}")

def inspect_sitemap_content(url):
    print(f"Inspecting content of {url}...")
    try:
        response = requests.get(url, timeout=10)
        # Print raw first 500 characters to see structure
        print(response.content[:1000].decode('utf-8'))
        
        soup = BeautifulSoup(response.content, 'xml')
        urls = soup.find_all('url')
        if urls:
            print("\nFirst Entry Tags:")
            for child in urls[0].children:
                if child.name:
                    print(f"  {child.name}: {child.text}")

    except Exception as e:
        print(f"Error: {e}")

print("Checking UK Archive 1...")
inspect_sitemap_dates("https://www.bbc.co.uk/sitemaps/https-sitemap-uk-archive-1.xml")
print("\nChecking UK Archive 25...")
inspect_sitemap_dates("https://www.bbc.co.uk/sitemaps/https-sitemap-uk-archive-25.xml")
print("\nChecking UK Archive 50...")
inspect_sitemap_dates("https://www.bbc.co.uk/sitemaps/https-sitemap-uk-archive-50.xml")

inspect_sitemap_content("https://www.bbc.co.uk/sitemaps/https-sitemap-uk-archive-50.xml")

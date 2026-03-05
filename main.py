import os
import hashlib
import json
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GH_MODELS_TOKEN = os.getenv("GH_MODELS_TOKEN")

# AI Keywords
AI_KEYWORDS = [
    "LLM", "RAG", "Agent", "Prompt", "Transformer", "Vector Database", 
    "Diffusion", "Fine-tuning", "Multi-modal", "Knowledge Graph", 
    "Context Window", "Memory module"
]

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def get_trending_repos():
    """Scrape GitHub Trending (All Languages)"""
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch trending: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    repos = []
    articles = soup.find_all("article", class_="Box-row")
    
    for article in articles[:25]:
        title_tag = article.find("h2", class_="h3")
        title = title_tag.text.strip().replace("\n", "").replace(" ", "") if title_tag else ""
        
        desc_tag = article.find("p", class_="col-9")
        description = desc_tag.text.strip() if desc_tag else ""
        
        url_tag = title_tag.find("a") if title_tag else None
        repo_url = f"https://github.com{url_tag['href']}" if url_tag else ""
        
        author = title.split("/")[0] if "/" in title else ""
        
        repos.append({
            "title": title,
            "description": description,
            "url": repo_url,
            "author": author
        })
    return repos

def filter_ai_repos(repos):
    """Filter repos based on AI keywords"""
    filtered = []
    for repo in repos:
        content = (repo["title"] + " " + repo["description"]).lower()
        if any(keyword.lower() in content for keyword in AI_KEYWORDS):
            filtered.append(repo)
    return filtered

def process_with_ai(repo):
    """Process repo info with GitHub Models (GPT-4o-mini)"""
    if not GH_MODELS_TOKEN:
        print("GH_MODELS_TOKEN not found, skipping AI processing.")
        return None

    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=GH_MODELS_TOKEN,
    )

    prompt = f"""
    Analyze the following GitHub repository:
    Title: {repo['title']}
    Description: {repo['description']}
    URL: {repo['url']}

    Please provide:
    1. A concise summary in Chinese (max 50 words).
    2. A list of Tags (categories) in Chinese.
    3. A list of Keywords (technical terms, keep original English terms).
    4. An 'Aha Index' (0.0 to 1.0) representing how innovative or surprising the project is.
    5. Expert Insight in Chinese (Markdown format, deep technical perspective).

    Output MUST be a structured JSON with keys: summary, tags, keywords, aha_index, expert_insight.
    All text fields (summary, tags, expert_insight) MUST be written in Chinese.
    Keywords should keep the original English technical terms.
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a senior AI engineer summarizing technical projects."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o-mini",
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI processing error for {repo['title']}: {e}")
        return None

def save_to_db(repo, ai_data):
    """Save raw and processed data to Supabase"""
    if not supabase:
        print("Supabase client not initialized, skipping DB save.")
        return

    # Calculate MD5 ID
    item_id = hashlib.md5(repo["url"].encode()).hexdigest()

    # 1. Upsert into raw_items
    raw_item = {
        "id": item_id,
        "title": repo["title"],
        "original_url": repo["url"],
        "source_name": "GitHub",
        "source_type": "REPO",
        "author": repo["author"],
        "published_at": datetime.utcnow().isoformat()
    }
    
    try:
        supabase.table("raw_items").upsert(raw_item).execute()
        print(f"Saved raw_item: {repo['title']}")
    except Exception as e:
        print(f"Error saving raw_item {repo['title']}: {e}")
        return

    # 2. Upsert into processed_items
    if ai_data:
        processed_item = {
            "item_id": item_id,
            "summary": ai_data.get("summary"),
            "tags": ai_data.get("tags", []),
            "keywords": ai_data.get("keywords", []),
            "aha_index": float(ai_data.get("aha_index", 0.5)),
            "expert_insight": ai_data.get("expert_insight"),
            "updated_at": datetime.utcnow().isoformat()
        }
        try:
            supabase.table("processed_items").upsert(processed_item).execute()
            print(f"Saved processed_item: {repo['title']}")
        except Exception as e:
            print(f"Error saving processed_item {repo['title']}: {e}")

def main():
    print("Starting GitHub AI discovery...")
    all_repos = get_trending_repos()
    print(f"Fetched {len(all_repos)} trending repos.")
    
    ai_repos = filter_ai_repos(all_repos)
    print(f"Filtered {len(ai_repos)} AI-related repos.")
    
    for repo in ai_repos:
        print(f"Processing {repo['title']}...")
        ai_data = process_with_ai(repo)
        save_to_db(repo, ai_data)
    
    print("Discovery complete.")

if __name__ == "__main__":
    main()

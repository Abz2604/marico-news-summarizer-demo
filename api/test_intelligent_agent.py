#!/usr/bin/env python3
"""
Test the 2-step intelligent agent
"""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

from agent.brightdata_fetcher import fetch_url
from agent.page_analyzer import analyze_page_for_content
from agent.link_extractor import extract_article_links_with_ai


async def test_intelligent_navigation():
    """Test the 2-step intelligent agent"""
    print("=" * 70)
    print("🧠 Testing 2-Step Intelligent Agent")
    print("=" * 70)
    
    seed_url = "https://www.moneycontrol.com/company-article/marico/news/M13"
    user_prompt = "Create an executive summary with bullet points for recent Marico news"
    
    print(f"\n📍 Seed URL: {seed_url}")
    print(f"💬 User Prompt: {user_prompt}")
    print()
    
    # Fetch the page
    print("🔄 Step 0: Fetching page with Bright Data...")
    html = await fetch_url(seed_url, timeout=30)
    if not html:
        print("❌ Failed to fetch page")
        return False
    print(f"✅ Fetched {len(html):,} bytes")
    print()
    
    # Step 1: Analyze the page
    print("🧠 Step 1: Analyzing page...")
    analysis = await analyze_page_for_content(
        html=html,
        page_url=seed_url,
        user_prompt=user_prompt
    )
    
    print(f"\n📊 Analysis Results:")
    print(f"  Page Type: {analysis.page_type}")
    print(f"  Has Relevant Content: {analysis.has_relevant_content}")
    print(f"  Needs Navigation: {analysis.needs_navigation}")
    print(f"  Ready to Extract Links: {analysis.ready_to_extract_links}")
    print(f"  Confidence: {analysis.confidence}")
    print(f"  Summary: {analysis.analysis_summary}")
    
    if analysis.needs_navigation and analysis.navigation_link:
        print(f"\n🧭 AI suggests navigating to:")
        print(f"  {analysis.navigation_link}")
        print(f"  Reason: {analysis.navigation_reason}")
        
        # Follow the navigation
        print(f"\n🔄 Fetching navigation target...")
        nav_html = await fetch_url(analysis.navigation_link, timeout=30)
        if nav_html:
            html = nav_html
            seed_url = analysis.navigation_link
            print(f"✅ Navigated successfully")
        else:
            print(f"⚠️  Navigation failed, using original page")
    
    print()
    
    # Step 2: Extract links
    print("🔗 Step 2: Extracting article links...")
    article_urls = await extract_article_links_with_ai(
        html=html,
        seed_url=seed_url,
        user_prompt=user_prompt,
        max_links=5
    )
    
    print(f"\n📄 Found {len(article_urls)} article links:")
    for i, url in enumerate(article_urls, 1):
        print(f"  {i}. {url}")
    
    print()
    print("=" * 70)
    if article_urls:
        print("🎉 SUCCESS! Intelligent agent found relevant articles!")
    else:
        print("⚠️  No articles found - may need tuning")
    print("=" * 70)
    
    return len(article_urls) > 0


if __name__ == "__main__":
    success = asyncio.run(test_intelligent_navigation())
    exit(0 if success else 1)


#!/usr/bin/env python3
"""
🔍 Comprehensive Diagnostics Script
Tests all external service connections and configurations.
"""

import sys
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def print_header(title: str):
    """Print a fancy header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_result(service: str, status: str, message: str = ""):
    """Print test result with color coding"""
    status_icon = {
        "✅": "✅",
        "❌": "❌", 
        "⚠️": "⚠️",
        "ℹ️": "ℹ️"
    }
    icon = status_icon.get(status, status)
    print(f"{icon} {service:25} {message}")

async def test_config() -> Dict[str, Any]:
    """Test configuration loading"""
    print_header("Configuration Loading")
    result = {"status": "failed", "errors": []}
    
    try:
        from config import get_settings
        settings = get_settings()
        
        print_result("Config Module", "✅", "Loaded successfully")
        
        # Check critical settings
        checks = {
            "OpenAI API Key": settings.openai_api_key,
            "OpenAI Model": settings.openai_model,
            "Snowflake Account": settings.snowflake_account,
            "Snowflake Database": settings.snowflake_database,
            "Email Password": settings.smtp_password,
            "BrightData API Key": settings.brightdata_api_key,
        }
        
        print("\nEnvironment Variables Status:")
        for name, value in checks.items():
            if value:
                masked = f"{value[:8]}..." if len(str(value)) > 8 else "***"
                print_result(name, "✅", f"Set ({masked})")
            else:
                print_result(name, "⚠️", "Not set")
                result["errors"].append(f"{name} not configured")
        
        result["status"] = "success"
        result["settings"] = settings
        return result
        
    except Exception as e:
        print_result("Config Loading", "❌", f"Error: {e}")
        result["errors"].append(str(e))
        return result

async def test_snowflake(settings) -> Dict[str, Any]:
    """Test Snowflake connection"""
    print_header("Snowflake Database Connection")
    result = {"status": "skipped", "info": {}}
    
    if not settings.use_snowflake:
        print_result("Snowflake", "ℹ️", "USE_SNOWFLAKE=False, skipping test")
        return result
    
    if not all([settings.snowflake_account, settings.snowflake_user, 
                settings.snowflake_password, settings.snowflake_database]):
        print_result("Snowflake", "⚠️", "Missing required credentials")
        result["status"] = "failed"
        result["error"] = "Missing credentials"
        return result
    
    try:
        from services.db import fetch_dicts
        
        print_result("Connection", "ℹ️", "Attempting to connect...")
        
        # Test basic connectivity
        rows = fetch_dicts("SELECT CURRENT_VERSION() as version")
        version = rows[0]['version'] if rows else "unknown"
        print_result("Version Check", "✅", f"Snowflake v{version}")
        
        # Test context
        context = fetch_dicts("""
            SELECT 
                CURRENT_ROLE() as role,
                CURRENT_WAREHOUSE() as warehouse,
                CURRENT_DATABASE() as database,
                CURRENT_SCHEMA() as schema
        """)
        
        if context:
            ctx = context[0]
            print("\nActive Context:")
            print_result("Role", "✅", ctx['role'])
            print_result("Warehouse", "✅", ctx['warehouse'])
            print_result("Database", "✅", ctx['database'])
            print_result("Schema", "✅", ctx['schema'])
            result["info"]["context"] = ctx
        
        # Test table access
        tables = fetch_dicts("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
            AND TABLE_NAME LIKE 'AI_NW_SUMM_%'
            ORDER BY TABLE_NAME
        """)
        
        if tables:
            print(f"\nFound {len(tables)} application tables:")
            for t in tables[:5]:  # Show first 5
                print_result("Table", "✅", t['table_name'])
            if len(tables) > 5:
                print_result("...", "ℹ️", f"and {len(tables)-5} more")
            result["info"]["tables"] = [t['table_name'] for t in tables]
        else:
            print_result("Tables", "⚠️", "No AI_NW_SUMM_* tables found")
        
        result["status"] = "success"
        print_result("\nSnowflake", "✅", "All checks passed!")
        
    except Exception as e:
        print_result("Snowflake", "❌", f"Error: {e}")
        result["status"] = "failed"
        result["error"] = str(e)
    
    return result

async def test_openai(settings) -> Dict[str, Any]:
    """Test OpenAI API connection"""
    print_header("OpenAI API Connection")
    result = {"status": "failed"}
    
    if not settings.openai_api_key:
        print_result("OpenAI", "⚠️", "API key not configured")
        return result
    
    try:
        from langchain_openai import ChatOpenAI
        
        print_result("API Key", "✅", f"Configured ({settings.openai_api_key[:8]}...)")
        print_result("Model", "ℹ️", f"Using {settings.openai_model}")
        
        # Test with a simple call
        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=0
        )
        
        print_result("Connection", "ℹ️", "Sending test request...")
        response = await asyncio.to_thread(
            llm.invoke,
            "Say 'OK' if you can read this."
        )
        
        if response and response.content:
            print_result("Response", "✅", f"Received: {response.content[:50]}")
            result["status"] = "success"
            result["response"] = response.content
        else:
            print_result("Response", "❌", "Empty response")
            
    except Exception as e:
        print_result("OpenAI", "❌", f"Error: {e}")
        result["error"] = str(e)
    
    return result

async def test_email(settings) -> Dict[str, Any]:
    """Test email configuration (no actual send)"""
    print_header("Email Service Configuration")
    result = {"status": "success"}
    
    print_result("SMTP Host", "✅", settings.smtp_host)
    print_result("SMTP Port", "✅", str(settings.smtp_port))
    print_result("Sender Email", "✅", settings.smtp_sender_email)
    
    if settings.smtp_password:
        print_result("SMTP Password", "✅", "Configured (masked)")
        print("\nℹ️  Email service configured. Skipping actual send test.")
        print("   To test sending, use the campaign endpoints in the API.")
    else:
        print_result("SMTP Password", "⚠️", "Not configured")
        result["status"] = "warning"
        result["message"] = "SMTP password not set"
    
    return result

async def test_brightdata(settings) -> Dict[str, Any]:
    """Test BrightData configuration"""
    print_header("BrightData Scraping API")
    result = {"status": "skipped"}
    
    if settings.brightdata_api_key:
        print_result("API Key", "✅", f"Configured ({settings.brightdata_api_key[:8]}...)")
        print_result("Zone", "✅", settings.brightdata_zone)
        print("\nℹ️  BrightData configured. API will use it for web scraping.")
        result["status"] = "success"
    else:
        print_result("BrightData", "⚠️", "Not configured (will use fallback fetching)")
        result["status"] = "warning"
    
    return result

async def test_agent_modules() -> Dict[str, Any]:
    """Test that agent modules load correctly"""
    print_header("Agent System Modules")
    result = {"status": "success", "loaded": []}
    
    modules = [
        ("agent.graph", "Core Agent Graph"),
        ("agent.intent_extractor", "Intent Extractor"),
        ("agent.context_extractor_llm", "Context Extractor"),
        ("agent.content_validator", "Content Validator"),
        ("agent.date_parser", "Date Parser"),
        ("agent.deduplicator", "Deduplicator"),
        ("agent.link_extractor", "Link Extractor"),
        ("agent.page_analyzer", "Page Analyzer"),
    ]
    
    for module_name, display_name in modules:
        try:
            __import__(module_name)
            print_result(display_name, "✅", "Loaded")
            result["loaded"].append(module_name)
        except Exception as e:
            print_result(display_name, "❌", f"Error: {e}")
            result["status"] = "failed"
    
    return result

async def main():
    """Run all diagnostics"""
    print("\n" + "🔍 " + "="*66)
    print("  MARICO NEWS SUMMARIZER - SYSTEM DIAGNOSTICS")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)
    
    results = {}
    
    # Test 1: Configuration
    config_result = await test_config()
    results["config"] = config_result
    
    if config_result["status"] != "success":
        print("\n❌ Configuration loading failed. Cannot continue.")
        return results
    
    settings = config_result["settings"]
    
    # Test 2: Agent Modules
    results["agent"] = await test_agent_modules()
    
    # Test 3: OpenAI
    results["openai"] = await test_openai(settings)
    
    # Test 4: Snowflake
    results["snowflake"] = await test_snowflake(settings)
    
    # Test 5: Email
    results["email"] = await test_email(settings)
    
    # Test 6: BrightData
    results["brightdata"] = await test_brightdata(settings)
    
    # Summary
    print_header("SUMMARY")
    
    status_counts = {
        "success": 0,
        "failed": 0,
        "warning": 0,
        "skipped": 0
    }
    
    for service, result in results.items():
        status = result.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        
        icon = {
            "success": "✅",
            "failed": "❌",
            "warning": "⚠️",
            "skipped": "ℹ️"
        }.get(status, "❓")
        
        print_result(service.upper(), icon, status.upper())
    
    print("\n" + "-"*70)
    print(f"✅ Successful: {status_counts['success']}")
    print(f"❌ Failed: {status_counts['failed']}")
    print(f"⚠️  Warnings: {status_counts['warning']}")
    print(f"ℹ️  Skipped: {status_counts['skipped']}")
    print("-"*70)
    
    if status_counts["failed"] > 0:
        print("\n❌ Some tests failed. Please review the errors above.")
        return 1
    elif status_counts["warning"] > 0:
        print("\n⚠️  All critical tests passed, but some warnings exist.")
        return 0
    else:
        print("\n✅ All tests passed! System is ready.")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


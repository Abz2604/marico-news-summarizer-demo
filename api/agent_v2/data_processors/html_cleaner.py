"""
HTML Cleaner - Optimizes HTML for LLM processing

Removes noise, preserves structure, converts to clean format.
"""

import logging
import re
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def clean_html_for_llm(
    html: str,
    max_chars: int = 15000,
    preserve_structure: bool = True
) -> str:
    """
    Clean HTML for LLM processing.
    
    Strategy:
    1. Remove noise (scripts, styles, ads, navigation)
    2. Preserve structure (headings, paragraphs, lists)
    3. Convert to clean text with structure markers
    4. Truncate intelligently if needed
    
    Args:
        html: Raw HTML content
        max_chars: Maximum characters to return
        preserve_structure: Whether to preserve headings/lists structure
        
    Returns:
        Cleaned text optimized for LLM
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Step 1: Remove complete noise (no value for content)
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'canvas']):
        tag.decompose()
    
    # Step 2: Remove navigation and boilerplate
    for tag in soup.find_all(['nav', 'aside', 'footer', 'header']):
        tag.decompose()
    
    # Remove common ad/navigation classes
    noise_patterns = ['nav', 'menu', 'sidebar', 'footer', 'header', 'ads', 'advertisement', 'cookie']
    for pattern in noise_patterns:
        for tag in soup.find_all(class_=lambda x: x and pattern in str(x).lower()):
            tag.decompose()
        for tag in soup.find_all(id=lambda x: x and pattern in str(x).lower()):
            tag.decompose()
    
    # Step 3: Replace images with alt text (preserves context)
    for img in soup.find_all('img'):
        alt_text = img.get('alt', '').strip()
        if alt_text:
            img.replace_with(f"[Image: {alt_text}]")
        else:
            img.decompose()
    
    # Step 4: Extract text with structure
    if preserve_structure:
        lines = []
        
        # Preserve headings
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = heading.get_text(strip=True)
            if text:
                level = int(heading.name[1])
                prefix = '#' * level
                lines.append(f"\n{prefix} {text}\n")
        
        # Preserve lists
        for list_tag in soup.find_all(['ul', 'ol']):
            list_items = list_tag.find_all('li', recursive=False)
            if list_items:
                lines.append("\n")
                for item in list_items:
                    text = item.get_text(strip=True)
                    if text:
                        lines.append(f"- {text}\n")
                lines.append("\n")
        
        # Preserve paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Skip very short paragraphs
                lines.append(f"{text}\n\n")
        
        # If structure extraction got nothing, fallback to simple text
        if not lines:
            main_content = soup.find('main') or soup.find('article') or soup.find('body') or soup
            text = main_content.get_text(separator='\n', strip=True)
            lines = [text]
        
        text = ''.join(lines)
    else:
        # Simple extraction
        main_content = soup.find('main') or soup.find('article') or soup.find('body') or soup
        text = main_content.get_text(separator='\n', strip=True)
    
    # Step 5: Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
    text = re.sub(r' {2,}', ' ', text)  # Max 1 space
    text = text.strip()
    
    # Step 6: Intelligent truncation
    if len(text) > max_chars:
        # Try to break at paragraph boundary
        truncated = text[:max_chars]
        last_para = truncated.rfind('\n\n')
        if last_para > max_chars * 0.8:  # If we're close enough
            text = truncated[:last_para]
        else:
            text = truncated
        text += "\n\n... (content truncated)"
    
    logger.debug(f"Cleaned HTML: {len(html)} → {len(text)} chars")
    
    return text


def extract_main_content(html: str) -> Optional[str]:
    """
    Extract main content area from HTML.
    
    Tries to find article/main content, falls back to body.
    
    Args:
        html: Raw HTML
        
    Returns:
        Main content text or None
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try semantic HTML5 tags first
    main_content = (
        soup.find('article') or
        soup.find('main') or
        soup.find(class_=lambda x: x and 'content' in str(x).lower()) or
        soup.find('body')
    )
    
    if main_content:
        # Remove noise from main content
        for tag in main_content.find_all(['script', 'style', 'nav', 'aside']):
            tag.decompose()
        
        return main_content.get_text(separator='\n', strip=True)
    
    return None


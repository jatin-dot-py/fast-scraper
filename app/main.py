from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from typing import List, Dict, Any, Optional
import random
from pydantic import BaseModel
import time
import logging
from urllib.parse import urlparse
import os
from app.config import get_proxy_list, get_settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Model for the request body
class ScrapeRequest(BaseModel):
    urls: List[str]
    proxy_type: str = "datacenter"  # Default to datacenter proxies

# List of user agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
]

async def scrape_url(url: str, max_retries: int = 3, timeout: int = 30, proxy_type: str = "datacenter") -> Dict[str, Any]:
    """Scrape a single URL with retry logic."""
    start_time = time.time()
    
    # Rotate user agent
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    # Get a random proxy (always use datacenter proxies regardless of what was requested)
    proxies = get_proxy_list("datacenter")
    if not proxies:
        logger.warning("No proxies configured. Proceeding without proxy.")
        proxy = None
    else:
        # Format proxy for httpx
        proxy_url = random.choice(proxies)
        proxy = {
            "http://": proxy_url,
            "https://": proxy_url
        }
    
    # Extract domain for per-domain rate limiting
    domain = urlparse(url).netloc
    
    # Try to use HTTP/2 for better performance
    for attempt in range(max_retries):
        try:
            # Create a client with HTTP/2 support
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(
                http2=True,
                limits=limits,
                proxies=proxy,
                timeout=timeout,
                follow_redirects=True,
                verify=False  # Disable SSL verification for performance
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                content = response.text
                elapsed = time.time() - start_time
                
                return {
                    "url": url,
                    "status_code": response.status_code,
                    "content": content,
                    "elapsed_seconds": elapsed,
                    "success": True,
                    "proxy_used": "datacenter",  # Always reporting datacenter
                }
        except httpx.TimeoutException:
            logger.warning(f"Attempt {attempt+1} timed out for {url}")
            # Get a different proxy for the retry
            if proxies:
                proxy_url = random.choice(proxies)
                proxy = {
                    "http://": proxy_url,
                    "https://": proxy_url
                }
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "error": "All retry attempts timed out",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter",
                }
        except httpx.HTTPStatusError as e:
            # Don't retry for client errors (4xx)
            if 400 <= e.response.status_code < 500:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "status_code": e.response.status_code,
                    "error": f"HTTP error: {e}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter",
                }
            # Server errors might be transient, continue retrying
            logger.warning(f"Attempt {attempt+1} failed with HTTP error {e.response.status_code} for {url}")
            # Get a different proxy for the retry
            if proxies:
                proxy_url = random.choice(proxies)
                proxy = {
                    "http://": proxy_url,
                    "https://": proxy_url
                }
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "status_code": e.response.status_code,
                    "error": f"All retry attempts failed with HTTP errors: {e}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter",
                }
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed with unexpected error for {url}: {e}")
            # Get a different proxy for the retry
            if proxies:
                proxy_url = random.choice(proxies)
                proxy = {
                    "http://": proxy_url,
                    "https://": proxy_url
                }
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "error": f"All retry attempts failed with unexpected errors: {e}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter",
                }
    
    # This should never happen, but added for completeness
    elapsed = time.time() - start_time
    return {
        "url": url,
        "error": "Unknown failure in retry logic",
        "elapsed_seconds": elapsed,
        "success": False,
        "proxy_used": "datacenter",
    }

@app.post("/scrape")
async def scrape_urls(request: ScrapeRequest) -> Dict[str, Any]:
    """Scrape multiple URLs concurrently."""
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    start_time = time.time()
    
    # For now, we always use datacenter proxies regardless of what is requested
    proxy_type = "datacenter"
    logger.info(f"Using {proxy_type} proxies for scraping {len(request.urls)} URLs")
    
    # Create tasks for each URL
    tasks = [scrape_url(url, proxy_type=proxy_type) for url in request.urls]
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    successful = sum(1 for r in results if r.get("success", False))
    failed = len(results) - successful
    
    logger.info(f"Scraped {len(results)} URLs in {total_time:.2f} seconds. Success: {successful}, Failed: {failed}")
    
    return {
        "results": results,
        "total": len(results),
        "successful": successful,
        "failed": failed,
        "total_time_seconds": total_time,
        "proxy_type_used": proxy_type
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": get_settings().app_version}
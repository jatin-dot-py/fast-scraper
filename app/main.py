from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from typing import List, Dict, Any, Optional
import random
from pydantic import BaseModel
import time
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

# Get proxy list from environment
def get_proxy_list():
    """Get datacenter proxies from environment variable."""
    proxies_str = os.getenv("DATACENTER_PROXIES", "")
    if not proxies_str:
        logger.warning("No proxies configured in DATACENTER_PROXIES environment variable.")
        return []
    
    # Split by comma
    return [proxy.strip() for proxy in proxies_str.split(",") if proxy.strip()]

async def scrape_url(url: str, max_retries: int = 3, timeout: int = 30) -> Dict[str, Any]:
    """Scrape a single URL with retry logic."""
    start_time = time.time()
    
    # Rotate user agent
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    # Get proxies
    proxies = get_proxy_list()
    if not proxies:
        logger.warning(f"No proxies configured. Proceeding without proxy for {url}")
        proxy_url = None
    else:
        # Get a random proxy
        proxy_url = random.choice(proxies)
        logger.info(f"Using proxy {proxy_url} for {url}")
    
    # Try to fetch the URL with retries
    for attempt in range(max_retries):
        try:
            # Create a client for this request
            client_args = {
                "timeout": timeout,
                "follow_redirects": True,
                "http2": False  # Disable HTTP2 for compatibility
            }
            
            # Add proxy if available
            if proxy_url:
                client_args["proxy"] = proxy_url
                
            async with httpx.AsyncClient(**client_args) as client:
                response = await client.get(url, headers=headers)
                
                response.raise_for_status()
                content = response.text
                elapsed = time.time() - start_time
                
                logger.info(f"Successfully scraped {url} in {elapsed:.2f} seconds")
                
                return {
                    "url": url,
                    "status_code": response.status_code,
                    "content": content,
                    "elapsed_seconds": elapsed,
                    "success": True,
                    "proxy_used": "datacenter" if proxy_url else "none",
                }
        except httpx.TimeoutException:
            logger.warning(f"Attempt {attempt+1}/{max_retries} timed out for {url}")
            # Get a different proxy for the retry if available
            if proxies:
                proxy_url = random.choice(proxies)
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "error": "All retry attempts timed out",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter" if proxy_url else "none",
                }
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            # Don't retry for client errors (4xx)
            if 400 <= status_code < 500:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "status_code": status_code,
                    "error": f"HTTP error: {e}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter" if proxy_url else "none",
                }
            # Server errors might be transient, continue retrying
            logger.warning(f"Attempt {attempt+1}/{max_retries} failed with HTTP error {status_code} for {url}")
            
            # Get a different proxy for the retry if available
            if proxies:
                proxy_url = random.choice(proxies)
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "status_code": status_code,
                    "error": f"All retry attempts failed with HTTP errors: {e}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter" if proxy_url else "none",
                }
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}/{max_retries} failed with unexpected error for {url}: {e}")
            
            # Get a different proxy for the retry if available
            if proxies:
                proxy_url = random.choice(proxies)
            
            # If this was the last attempt, return error
            if attempt == max_retries - 1:
                elapsed = time.time() - start_time
                return {
                    "url": url,
                    "error": f"All retry attempts failed with unexpected errors: {str(e)}",
                    "elapsed_seconds": elapsed,
                    "success": False,
                    "proxy_used": "datacenter" if proxy_url else "none",
                }
    
    # This should never happen, but added for completeness
    elapsed = time.time() - start_time
    return {
        "url": url,
        "error": "Unknown failure in retry logic",
        "elapsed_seconds": elapsed,
        "success": False,
        "proxy_used": "datacenter" if proxy_url else "none",
    }

@app.post("/scrape")
async def scrape_urls(request: ScrapeRequest) -> Dict[str, Any]:
    """Scrape multiple URLs concurrently."""
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    start_time = time.time()
    
    # Log the number of proxies available
    proxies = get_proxy_list()
    proxy_count = len(proxies)
    logger.info(f"Using {proxy_count} datacenter proxies for scraping {len(request.urls)} URLs")
    
    # Create tasks for each URL
    tasks = [scrape_url(url) for url in request.urls]
    
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
        "proxy_type_used": "datacenter"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": os.getenv("APP_VERSION", "0.1.0")}
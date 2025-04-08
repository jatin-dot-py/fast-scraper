# This file is kept for backwards compatibility
# All configuration moved to main.py to simplify the implementation
import os
from typing import List
import logging

logger = logging.getLogger(__name__)

def get_settings():
    """Get application settings."""
    return {
        "app_name": os.getenv("APP_NAME", "scraper-api"),
        "app_version": os.getenv("APP_VERSION", "0.1.0"),
    }

def get_proxy_list(proxy_type: str) -> List[str]:
    """Get a list of proxies based on the proxy type."""
    # This is kept for backwards compatibility
    # Always use datacenter proxies
    proxies_str = os.getenv("DATACENTER_PROXIES", "")
    if not proxies_str:
        logger.warning("No proxies configured in DATACENTER_PROXIES environment variable.")
        return []
    
    # Split by comma
    return [proxy.strip() for proxy in proxies_str.split(",") if proxy.strip()]
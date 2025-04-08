import os
from typing import List, Dict, Optional
from pydantic_settings import BaseSettings
from pydantic import validator
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    app_name: str = "scraper-api"
    app_version: str = "0.1.0"
    
    # Proxy settings
    datacenter_proxies: str = ""  # Comma-separated list of datacenter proxies
    
    # Performance settings
    max_concurrent_requests: int = 100
    request_timeout: int = 30
    max_retries: int = 3
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
    @validator("datacenter_proxies")
    def split_datacenter_proxies(cls, v):
        """Split comma-separated list of proxies."""
        if not v:
            return []
        return [proxy.strip() for proxy in v.split(",") if proxy.strip()]

# Global settings instance
_settings = None

def get_settings() -> Settings:
    """Get application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

def get_proxy_list(proxy_type: str) -> List[str]:
    """Get a list of proxies based on the proxy type."""
    settings = get_settings()
    
    # Always return datacenter proxies regardless of requested type
    if proxy_type != "datacenter":
        logger.warning(f"Requested proxy type '{proxy_type}' not supported. Using datacenter proxies.")
    
    proxies = settings.datacenter_proxies
    
    if not proxies:
        logger.warning(f"No {proxy_type} proxies configured.")
    else:
        logger.info(f"Loaded {len(proxies)} {proxy_type} proxies.")
    
    return proxies
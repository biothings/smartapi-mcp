"""
SmartAPI Registry Integration

Handles interaction with the SmartAPI registry.
"""

import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SmartAPIRegistry:
    """Client for interacting with SmartAPI registry."""
    
    def __init__(self, base_url: str = "https://smart-api.info/api"):
        """Initialize SmartAPI registry client.
        
        Args:
            base_url: Base URL for SmartAPI registry API
        """
        self.base_url = base_url
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            
    async def search_apis(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for APIs in the SmartAPI registry.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of API metadata dictionaries
        """
        if not self.session:
            raise RuntimeError("SmartAPIRegistry must be used as async context manager")
            
        url = f"{self.base_url}/query"
        params = {
            "q": query,
            "size": limit
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("hits", [])
        except Exception as e:
            logger.error(f"Error searching SmartAPI registry: {e}")
            return []
            
    async def get_api_spec(self, api_id: str) -> Optional[Dict[str, Any]]:
        """Get OpenAPI specification for a specific API.
        
        Args:
            api_id: SmartAPI ID for the API
            
        Returns:
            OpenAPI specification dictionary or None if not found
        """
        if not self.session:
            raise RuntimeError("SmartAPIRegistry must be used as async context manager")
            
        url = f"{self.base_url}/metadata/{api_id}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"Error fetching API spec for {api_id}: {e}")
            return None
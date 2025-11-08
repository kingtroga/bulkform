import json
import logging
import os
from typing import Optional, Dict, Any
from functools import wraps
import redis

logger = logging.getLogger(__name__)

# Redis connection (same as your Celery Redis)
redis_client = redis.from_url(
    os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    decode_responses=True
)

TEMPLATE_CACHE_TTL = 3600  # 1 hour cache
TEMPLATE_CACHE_PREFIX = "template:"


def cache_template(ttl: int = TEMPLATE_CACHE_TTL):
    """
    Decorator to cache template lookups in Redis
    
    Usage:
        @cache_template(ttl=3600)
        def get_template(template_id, user_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, template_id: str, user_id: str, *args, **kwargs):
            # Create cache key
            cache_key = f"{TEMPLATE_CACHE_PREFIX}{user_id}:{template_id}"
            
            # Try cache first
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    print(f"✅ CACHE HIT: {cache_key}")
                    logger.info(f"✅ CACHE HIT: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
            
            # Cache miss - call the function
            print(f"🔄 CACHE MISS: {cache_key} → Hitting database")
            logger.info(f"🔄 CACHE MISS: {cache_key} → Hitting database")
            result = func(self, template_id, user_id, *args, **kwargs)
            
            # Store in cache
            if result:
                try:
                    redis_client.setex(
                        cache_key,
                        ttl,
                        json.dumps(result, default=str)  # default=str for datetime objects
                    )
                    print(f"💾 CACHED: {cache_key} for {ttl}s")
                    logger.info(f"💾 CACHED: {cache_key} for {ttl}s")
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")
            
            return result
        
        return wrapper
    return decorator


def invalidate_template_cache(template_id: str, user_id: str):
    """Invalidate a specific template from cache"""
    cache_key = f"{TEMPLATE_CACHE_PREFIX}{user_id}:{template_id}"
    try:
        redis_client.delete(cache_key)
        logger.info(f"🗑️ Invalidated template cache: {cache_key}")
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")


def invalidate_user_templates(user_id: str):
    """Invalidate all templates for a user (when templates are updated)"""
    try:
        pattern = f"{TEMPLATE_CACHE_PREFIX}{user_id}:*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"🗑️ Invalidated {len(keys)} templates for user {user_id}")
    except Exception as e:
        logger.warning(f"Batch cache invalidation error: {e}")
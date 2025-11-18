import json
import logging
import os
from typing import Callable
from functools import wraps
import redis

logger = logging.getLogger(__name__)

redis_client = redis.from_url(
    os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    decode_responses=True,
)

SESSION_CACHE_TTL = 300  # 5 minutes (sessions change more often)
SESSION_LIST_PREFIX = "sessions:list:"
SESSION_COUNT_PREFIX = "sessions:count:"


def cache_user_sessions(ttl: int = SESSION_CACHE_TTL):
    """
    Cache paged user sessions (list endpoint).

    Decorates: get_user_sessions(self, user_id, limit=50, offset=0, ...)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, user_id: str, limit: int = 50, offset: int = 0, *args, **kwargs):
            cache_key = f"{SESSION_LIST_PREFIX}{user_id}:{limit}:{offset}"

            # Try cache
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    print(f"✅ SESSION CACHE HIT: {cache_key}")
                    logger.info(f"✅ SESSION CACHE HIT: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Session cache read error: {e}")

            # Miss → DB
            print(f"🔄 SESSION CACHE MISS: {cache_key} → Hitting database")
            logger.info(f"🔄 SESSION CACHE MISS: {cache_key} → Hitting database")
            result = func(self, user_id, limit, offset, *args, **kwargs)

            # Store
            if result is not None:
                try:
                    redis_client.setex(
                        cache_key,
                        ttl,
                        json.dumps(result, default=str),
                    )
                    print(f"💾 SESSION LIST CACHED: {cache_key} for {ttl}s")
                    logger.info(f"💾 SESSION LIST CACHED: {cache_key} for {ttl}s")
                except Exception as e:
                    logger.warning(f"Session cache write error: {e}")

            return result

        return wrapper
    return decorator


def cache_session_count(ttl: int = SESSION_CACHE_TTL):
    """
    Cache session count per user.

    Decorates: count_user_sessions(self, user_id)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, user_id: str, *args, **kwargs):
            cache_key = f"{SESSION_COUNT_PREFIX}{user_id}"

            try:
                cached = redis_client.get(cache_key)
                if cached is not None:
                    print(f"✅ SESSION COUNT CACHE HIT: {cache_key}")
                    logger.info(f"✅ SESSION COUNT CACHE HIT: {cache_key}")
                    return int(cached)
            except Exception as e:
                logger.warning(f"Session count cache read error: {e}")

            print(f"🔄 SESSION COUNT CACHE MISS: {cache_key} → Hitting database")
            logger.info(f"🔄 SESSION COUNT CACHE MISS: {cache_key} → Hitting database")
            count = func(self, user_id, *args, **kwargs)

            try:
                redis_client.setex(cache_key, ttl, str(count))
                print(f"💾 SESSION COUNT CACHED: {cache_key} for {ttl}s")
                logger.info(f"💾 SESSION COUNT CACHED: {cache_key} for {ttl}s")
            except Exception as e:
                logger.warning(f"Session count cache write error: {e}")

            return count

        return wrapper
    return decorator


def invalidate_user_sessions(user_id: str):
    """
    Invalidate ALL session-related cache for a user
    (both lists & counts).
    """
    try:
        list_pattern = f"{SESSION_LIST_PREFIX}{user_id}:*"
        count_key = f"{SESSION_COUNT_PREFIX}{user_id}"

        keys = redis_client.keys(list_pattern)
        keys.append(count_key)

        # Filter out non-existing / duplicates
        keys = list({k for k in keys if k})

        if keys:
            redis_client.delete(*keys)
            logger.info(f"🗑️ Invalidated {len(keys)} session cache key(s) for user {user_id}")
        else:
            logger.info(f"ℹ️ No session cache keys to invalidate for user {user_id}")
    except Exception as e:
        logger.warning(f"Session cache invalidation error: {e}")

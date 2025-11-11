import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

executor = ThreadPoolExecutor(max_workers=30, thread_name_prefix="bulkform")

async def run_async(func, *args, **kwargs):
    """Run any blocking operation in thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        partial(func, *args, **kwargs)
    )
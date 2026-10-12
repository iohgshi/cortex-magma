import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastmcp import FastMCP

# asyncio.to_thread 默认线程池为 min(32, 核数+4),高并发时会排队;
# 在 lifespan 里(事件循环已启动)把默认线程池调大到 64。
DEFAULT_EXECUTOR_MAX_WORKERS = 64


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=DEFAULT_EXECUTOR_MAX_WORKERS))
    yield


mcp = FastMCP("cortex-magma", lifespan=_lifespan)

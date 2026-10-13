import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp_tasks import TasksExtension

import tools


DEFAULT_EXECUTOR_MAX_WORKERS = 64


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=DEFAULT_EXECUTOR_MAX_WORKERS))
    yield


mcp = FastMCP("cortex-magma", lifespan=_lifespan)
mcp.add_extension(TasksExtension())  # 启用后台任务扩展(SEP-2663),默认 memory:// 队列,无需 Redis
tools.register(mcp)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="http", host="0.0.0.0", port=8000)
import asyncio
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp_tasks import TasksExtension

from . import tools


DEFAULT_EXECUTOR_MAX_WORKERS = 64
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=DEFAULT_EXECUTOR_MAX_WORKERS))
    yield


mcp = FastMCP("cortex-magma", lifespan=_lifespan)
mcp.add_extension(TasksExtension())  # 启用后台任务扩展(SEP-2663),默认 memory:// 队列,无需 Redis
tools.register(mcp)


def main() -> None:
    """命令行入口:装完包后直接 `cortex-magma` 启动。"""
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    main()

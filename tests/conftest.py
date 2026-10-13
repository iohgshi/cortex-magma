"""共享夹具:内存直连的 MCP 客户端。

无需启动服务进程,Client(mcp) 走内存传输,lifespan(线程池 + 任务扩展)照常生效。
"""

import pytest
from fastmcp import Client

from server import mcp


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c

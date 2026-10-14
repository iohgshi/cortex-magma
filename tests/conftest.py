"""全局 pytest 配置:只负责把客户端连到已经启动好的 server。

server 由你手动起(另开一个终端 `python server.py`),测试这边不起进程。
地址默认 http://127.0.0.1:8000/mcp/ ,换端口用 MCP_URL 覆盖。
"""

import os

import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp/")


@pytest.fixture
async def client():
    async with Client(MCP_URL) as c:
        yield c
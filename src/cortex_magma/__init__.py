"""cortex-magma:一个基于 FastMCP 的 MCP server。

`mcp` 实例在这里建好并完成全部工具注册,server.py 只负责跑起来。
"""

from .server import mcp

__all__ = ["mcp"]

"""工具包:register(mcp) 汇总各工具模块的注册。新增工具模块时在这里加一行。"""

from fastmcp import FastMCP

from . import greet, job, system

_MODULES = (greet, job, system)


def register(mcp: FastMCP) -> None:
    for module in _MODULES:
        module.register(mcp)

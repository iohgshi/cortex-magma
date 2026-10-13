import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

logger = logging.getLogger("cortex-magma.greet")

GREET_USER_DESCRIPTION = '''生成一句问候语。当用户想打招呼、或测试服务是否在线时调用。

触发示例:
- 用户说「hi」「你好」「在吗」→ 调用本工具,用户没报名字时 name 填 "朋友"
- 用户说「跟我大哥打个招呼」→ 调用本工具,name 填 "大哥"
- 用户说「测试下服务通不通」→ 调用本工具,name 填 "test"

返回示例:name="大哥" → 返回 "我是cortex-magma"'''


def greet(
    name: Annotated[str, Field(description="要问候的人的名字")],
) -> str:

    # 本地日志:输出到服务端终端
    logger.info("greet_user 被调用: name=%r", name)

    return f"我是cortex-magma"


def register(mcp: FastMCP) -> None:
    mcp.tool(
        greet,
        name="greet_user",
        description=GREET_USER_DESCRIPTION,
    )

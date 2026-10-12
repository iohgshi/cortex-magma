import asyncio
import logging
import time
import uuid
from typing import Annotated

from app import mcp
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from pydantic import Field

logger = logging.getLogger("cortex-magma.task")


def _client_info() -> str:
    """取调用方的 IP:端口(TCP 对端地址);非 HTTP 传输(如 stdio)时返回 unknown。"""
    try:
        request = get_http_request()
    except RuntimeError:
        return "unknown"
    client = request.client  # Starlette 的 AddressPair: host + port
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


__NAME = "run_task"
__DESCRIPTION = '''根据一个任务名字执行任务
* 期间通过 MCP progress 通知上报实时进度,完成后返回任务结果(含任务 ID、最终进度、总耗时)。
'''
async def run(task_name: Annotated[str, Field(description="任务名称,仅用于展示")] = "模拟任务",
    ctx: Context = None
) -> str:

    task_id = uuid.uuid4().hex[:8]
    logger.info("run_task 被调用: 调用方=%s, task_name=%r, task_id=%s", _client_info(), task_name, task_id)

    total = 100
    started = time.monotonic()
    for progress in range(10, total + 1, 10):
        await asyncio.sleep(1)
        await ctx.report_progress(progress, total)  # MCP 进度通知:progress/total
        logger.info("任务 %s(%s)进度:%d%%", task_name, task_id, progress)

    elapsed = time.monotonic() - started
    logger.info("任务 %s(%s)执行完成,耗时 %.1f 秒", task_name, task_id, elapsed)

    return (
        f"任务「{task_name}」执行完成:"
        f"task_id={task_id},最终进度 100%,总耗时 {elapsed:.1f} 秒"
    )



@mcp.tool(
    name=__NAME,
    description=__DESCRIPTION,
)
async def run_task(
    task_name: Annotated[str, Field(description="任务名称,仅用于展示")] = "模拟任务",
    ctx: Context = None,
) -> str:
    return await run(task_name, ctx)

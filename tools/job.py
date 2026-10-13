"""模拟后台长任务:演示 tasks 扩展(task=True 工具)的两种调用方式。

同步调用:客户端 call_tool 阻塞到任务结束拿最终结果。
后台任务:客户端 call_tool_task 立刻拿到句柄,通过 tasks/get 轮询状态,任务跑在 Docket 队列上。
"""

import asyncio
import logging
import time
import uuid
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

logger = logging.getLogger("cortex-magma.job")


__NAME = "run_background_job"
__DESCRIPTION = '''模拟一个耗时后台任务:
* 逐秒推进并上报进度;既可同步调用等待最终结果,也可提交为后台任务后轮询状态(working/completed/failed)。
* duration_seconds 控制总时长,默认 5 秒。
'''
async def run(job_name: Annotated[str, Field(description="任务名称,仅用于展示")] = "模拟任务",
    duration_seconds: Annotated[int, Field(description="任务总时长(秒)", ge=1, le=60)] = 5,
    ctx: Context = None
) -> dict:
    job_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    logger.info("后台任务 %s(%s)启动: 时长 %ds, 调用方=%s", job_name, job_id, duration_seconds, _client_info())

    for i in range(1, duration_seconds + 1):
        await asyncio.sleep(1)
        await ctx.report_progress(round(i / duration_seconds * 100), 100)  # 每秒上报一次进度
        logger.info("后台任务 %s(%s)进度: %d/%ds", job_name, job_id, i, duration_seconds)

    elapsed = time.monotonic() - started
    logger.info("后台任务 %s(%s)完成,耗时 %.1f 秒", job_name, job_id, elapsed)

    return {
        "job_id": job_id,
        "job_name": job_name,
        "duration_seconds": duration_seconds,
        "elapsed_seconds": round(elapsed, 1),
        "message": f"任务 {job_name!r} 完成,耗时 {elapsed:.1f} 秒",
    }


def _client_info() -> str:
    """取调用方的 IP:端口;非 HTTP 传输(如后台任务 worker)时返回 unknown。"""
    from fastmcp.server.dependencies import get_http_request

    try:
        request = get_http_request()
    except RuntimeError:
        return "unknown"
    client = request.client
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


async def run_background_job(
    job_name: Annotated[str, Field(description="任务名称,仅用于展示")] = "模拟任务",
    duration_seconds: Annotated[int, Field(description="任务总时长(秒)", ge=1, le=60)] = 5,
    ctx: Context = None,
) -> dict:
    return await run(job_name, duration_seconds, ctx)


def register(mcp: FastMCP) -> None:
    mcp.tool(
        run_background_job,
        name=__NAME,
        description=__DESCRIPTION,
        task=True,  # 标记为可后台执行:客户端可提交为任务并轮询状态
    )

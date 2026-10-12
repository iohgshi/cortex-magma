import asyncio
import logging
import platform
import time
import uuid
from datetime import datetime
from typing import Annotated

import psutil
from app import mcp
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from pydantic import Field

logger = logging.getLogger("cortex-magma.system")


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


def _query_current_info() -> dict:
    """查询当前信息:本机时间、主机名、操作系统。"""
    return {
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }


def _query_cpu() -> dict:
    """查询 CPU:使用率(采样 1 秒)、核心数。"""
    time.sleep(1)

    return {
        "usage_percent": psutil.cpu_percent(interval=1),
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(logical=True),
    }


def _query_memory() -> dict:
    """查询内存:总量、已用、可用、使用率。"""
    time.sleep(2)
    vm = psutil.virtual_memory()
    return {
        "total_gb": round(vm.total / 1024**3, 2),
        "used_gb": round(vm.used / 1024**3, 2),
        "available_gb": round(vm.available / 1024**3, 2),
        "usage_percent": vm.percent,
    }


def _query_disk() -> dict:
    """查询磁盘(根分区):总量、已用、可用、使用率。

    macOS 的多个 APFS 卷共享一个容器,psutil 的 used 只统计根卷自身(约十几个 GB 的系统文件),
    不含 Data 卷上的用户数据;跨平台统一用 total - free 计算整个容器的真实已用量。
    """
    time.sleep(3)

    du = psutil.disk_usage("/")
    total_gb = du.total / 1024**3
    available_gb = du.free / 1024**3
    used_gb = total_gb - available_gb
    return {
        "total_gb": round(total_gb, 2),
        "used_gb": round(used_gb, 2),
        "available_gb": round(available_gb, 2),
        "usage_percent": round(used_gb / total_gb * 100, 1),
    }


__NAME = "query_system_info"
__DESCRIPTION = '''查询 magma 系统的信息、CPU、内存与磁盘使用情况:
* 分四步执行(当前信息 → CPU → 内存 → 磁盘),每步完成通过 MCP progress 通知上报进度(25%/50%/75%/100%),全部完成后返回汇总数据。
* CPU 使用率需阻塞采样 1 秒,整体约需 7 秒。
'''
async def run(query_name: Annotated[str, Field(description="查询名称,仅用于展示")] = "系统信息查询",
    ctx: Context = None
) -> dict:
    query_id = uuid.uuid4().hex[:8]
    logger.info("query_system_info 被调用: 调用方=%s, query_name=%r, query_id=%s", _client_info(), query_name, query_id)

    started = time.monotonic()

    # 第一步:查当前信息
    current_info = _query_current_info()
    await ctx.report_progress(25, 100)  # 当前信息查完:进度 25%
    logger.info("查询 %s(%s)当前信息查询完成: %s", query_name, query_id, current_info)

    # 第二步:查 CPU(cpu_percent(interval=1) 需阻塞采样 1 秒,放线程池避免卡住事件循环)
    cpu = await asyncio.to_thread(_query_cpu)
    await ctx.report_progress(50, 100)  # CPU 查完:进度 50%
    logger.info("查询 %s(%s)CPU 查询完成: %s", query_name, query_id, cpu)

    # 第三步:查内存(含模拟耗时,同样放线程池,否则 sleep 会卡住事件循环、进度通知发不出去)
    memory = await asyncio.to_thread(_query_memory)
    await ctx.report_progress(75, 100)  # 内存查完:进度 75%
    logger.info("查询 %s(%s)内存查询完成: %s", query_name, query_id, memory)

    # 第四步:查磁盘(根分区,同上放线程池)
    disk = await asyncio.to_thread(_query_disk)
    await ctx.report_progress(100, 100)  # 磁盘查完:进度 100%
    logger.info("查询 %s(%s)磁盘查询完成: %s", query_name, query_id, disk)

    elapsed = time.monotonic() - started
    logger.info("查询 %s(%s)执行完成,耗时 %.1f 秒", query_name, query_id, elapsed)

    return {
        "query_id": query_id,
        "query_name": query_name,
        "elapsed_seconds": round(elapsed, 1),
        "current_info": current_info,
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
    }


@mcp.tool(
    name=__NAME,
    description=__DESCRIPTION,
)
async def query_system_info(
    query_name: Annotated[str, Field(description="查询名称,仅用于展示")] = "系统信息查询",
    ctx: Context = None,
) -> dict:
    return await run(query_name, ctx)

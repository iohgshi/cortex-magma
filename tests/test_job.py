"""run_background_job 工具测试:同步调用、参数校验、进度通知、后台任务生命周期。"""

import asyncio

import pytest
from fastmcp.exceptions import ToolError
from fastmcp_tasks import call_tool_task


async def test_sync_call(client):
    """同步调用:阻塞到完成,返回最终结果。"""
    result = await client.call_tool(
        "run_background_job", {"job_name": "同步测试", "duration_seconds": 1}
    )
    assert result.data["job_name"] == "同步测试"
    assert result.data["elapsed_seconds"] >= 1


async def test_param_validation(client):
    """duration_seconds 超出 [1, 60] 应报错。"""
    with pytest.raises(ToolError):
        await client.call_tool("run_background_job", {"duration_seconds": 0})
    with pytest.raises(ToolError):
        await client.call_tool("run_background_job", {"duration_seconds": 61})


async def test_progress_notifications(client):
    """每秒上报一次进度:2 秒任务应收到 50、100。"""
    received: list[float] = []

    async def on_progress(progress, total, message):
        received.append(progress)

    await client.call_tool(
        "run_background_job", {"duration_seconds": 2}, progress_handler=on_progress
    )
    assert received == [50.0, 100.0]


async def test_background_task_lifecycle(client):
    """后台任务:提交立刻返回句柄,轮询到 completed 后取回结果。"""
    task = await call_tool_task(
        client, "run_background_job", {"job_name": "后台测试", "duration_seconds": 2}
    )
    assert task.task_id  # 提交即刻拿到任务 id,无需等待

    final = await task.wait(timeout=15)
    assert final.status == "completed"

    result = await task.result()
    assert "后台测试" in result.data["message"]


async def test_cancel_background_task(client):
    """后台任务可取消:长任务提交后 cancel,终态应为 cancelled。"""
    task = await call_tool_task(
        client, "run_background_job", {"job_name": "取消测试", "duration_seconds": 30}
    )
    # 等任务真正跑起来再取消
    while (await task.status()).status != "working":
        await asyncio.sleep(0.1)

    await task.cancel()
    final = await task.wait(timeout=15)
    assert final.status == "cancelled"

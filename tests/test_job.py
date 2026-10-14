"""job 工具的测试:把 agent 调用 MCP 工具的流程写死成 if 判断。"""

import asyncio

import pytest
from fastmcp_tasks import call_tool_task

TERMINAL = ("completed", "failed", "cancelled")


async def test_run_background_job(client):
    # 1. agent 先看 server 上有哪些工具
    tools = await client.list_tools()
    if not any(t.name == "run_background_job" for t in tools):
        pytest.fail("server 上没有 run_background_job")
    print(f"\navailable tools: {[t.name for t in tools]}")

    # 2. 调工具,拿到返回。task=True 的工具返回的是任务句柄,不是结果
    task = await call_tool_task(
        client,
        "run_background_job",
        {"job_name": "测试任务", "duration_seconds": 3},
    )
    if not task.task_id:
        pytest.fail(f"没拿到 task_id: {task}")
    print(f"已启动, task_id={task.task_id}")

    # 3. agent 会轮询状态直到终态,这里用 while 替掉判断
    while True:
        status = await task.status()
        print(f"    进度: {status.status_message or '（无）'} · {status.status}")

        if status.status in TERMINAL:
            break
        if status.status == "working":
            await asyncio.sleep(0.3)
            continue
        pytest.fail(f"意外状态: {status.status}")

    # 4. agent 看终态决定:成功取结果,失败报错误
    if status.status != "completed":
        pytest.fail(f"任务没成功: {status.status}")

    result = await task.result()
    if result.data["job_name"] != "测试任务":
        pytest.fail(f"结果不对: {result.data}")
    print(f"    结果: {result.data}")
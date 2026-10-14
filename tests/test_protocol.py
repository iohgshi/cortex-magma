"""协议层测试:逐个覆盖 cortex-magma server 实际处理的 JSON-RPC 方法。

分三组:
1. 能力与发现 —— initialize 握手、server/discover
2. 三原语—— tools/list、tools/call、resources/*、prompts/*
3. 扩展与通知 —— tasks/*、notifications/progress,以及当前协议版本下不可用的方法

每个用例都按"发出请求 → 判断响应"写成显式 if,不依赖 pytest.raises 做黑盒断言。
"""

import asyncio

import mcp_types
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp_tasks import call_tool_task
from fastmcp_tasks.client_models import UpdateTaskRequest, UpdateTaskRequestParams
from mcp.shared.exceptions import MCPError

from conftest import MCP_URL

TERMINAL = ("completed", "failed", "cancelled")


# ---------------------------------------------------------------------------
# 1. 能力与发现:initialize / server/discover
# ---------------------------------------------------------------------------

async def test_initialize_handshake(client):
    """握手在 Client 首次发请求时自动完成,这里验证它协商出了什么。"""
    await client.list_tools()  # 触发 initialize + server/discover

    info = client.server_info
    if info is None or info.name != "cortex-magma":
        pytest.fail(f"server_info 不对: {info}")

    version = client.protocol_version
    print(f"\n[initialize] server={info.name} v{info.version} protocol={version}")

    # 走到 2026-07-28 才走 server/discover;老协议是 initialize,两种都要能取到
    result = client.session.discover_result or client.session.initialize_result
    if result is None:
        pytest.fail("握手结果为空:discover_result 和 initialize_result 都是 None")

    caps = result.capabilities
    print(f"[discover] capabilities={caps}")
    if caps.tools is None:
        pytest.fail("capabilities 里没有 tools")


async def test_discover_advertises_tasks_extension(client):
    """server/discover 的 capabilities.extensions 里应有 tasks 扩展。

    注意它只声明扩展名,不列举 tasks/get 等方法名 —— 方法名是规范写死的。
    """
    await client.list_tools()
    caps = client.session.discover_result.capabilities

    exts = caps.extensions or {}
    print(f"\n[server/discover] extensions={list(exts)}")
    if "io.modelcontextprotocol/tasks" not in exts:
        pytest.fail(f"没有声明 tasks 扩展: {list(exts)}")


# ---------------------------------------------------------------------------
# 2. 三原语:tools / resources / prompts
# ---------------------------------------------------------------------------

async def test_tools_list_returns_registered_tools(client):
    """tools/list:只返回 tools/ 目录下注册的工具,MCP 自身不贡献任何内置工具。"""
    tools = await client.list_tools()
    names = sorted(t.name for t in tools)
    print(f"\n[tools/list] {names}")

    expected = ["greet_user", "query_system_info", "run_background_job"]
    if names != expected:
        pytest.fail(f"工具列表不对:期望 {expected},实际 {names}")

    # 每个工具都必须有 name + description + inputSchema,否则 LLM 无法调用
    for t in tools:
        if not t.description:
            pytest.fail(f"{t.name} 没有 description")
        if t.input_schema.get("type") != "object":
            pytest.fail(f"{t.name} 的 inputSchema.type 不是 object: {t.input_schema}")


async def test_tool_input_schema_reaches_llm_intact(client):
    """锁住注册链路:Annotated[Field] 的约束必须完整出现在 inputSchema 里。

    这一层就是 LLM 做 function-calling 时看到的参数定义,
    改 Annotated 参数却没反映到这里,就会静默影响模型行为。
    """
    tools = {t.name: t for t in await client.list_tools()}
    job = tools.get("run_background_job")
    if job is None:
        pytest.fail("没有 run_background_job")

    props = job.input_schema["properties"]
    print(f"\n[tools/list] run_background_job 参数={props}")

    # Field(description=...) 必须进 schema —— LLM 全靠它决定参数填什么
    if props.get("job_name", {}).get("description") != "任务名称,仅用于展示":
        pytest.fail(f"job_name 的 description 没进 schema: {props.get('job_name')}")

    # ge=1 / le=60 必须变成 minimum / maximum,给模型硬约束
    dur = props.get("duration_seconds", {})
    if dur.get("minimum") != 1 or dur.get("maximum") != 60:
        pytest.fail(f"duration_seconds 的范围约束丢了: {dur}")

    # 有默认值的参数不应出现在 required 里
    if "required" in job.input_schema:
        pytest.fail(f"两个参数都有默认值,不该有 required: {job.input_schema}")


async def test_call_tool_sync_waits_for_result(client):
    """tools/call 同步路径:阻塞到执行结束,直接拿最终结果,不经过 tasks/*。"""
    result = await client.call_tool("greet_user", {"name": "大哥"})
    print(f"\n[tools/call] greet_user -> {result.data}")
    if result.data != "我是cortex-magma":
        pytest.fail(f"结果不对: {result.data}")


async def test_call_tool_raw_mcp_shape(client):
    """*_mcp 变体返回未解析的 MCP 协议对象,这里能看到线上报文的真实形状。"""
    raw = await client.call_tool_mcp("greet_user", {"name": "协议"})
    dumped = raw.model_dump(by_alias=True, exclude_none=True)
    print(f"\n[tools/call 原始] {dumped}")

    if raw.structured_content is None:
        pytest.fail(f"structuredContent 为空: {dumped}")
    if not any(getattr(c, "type", "") == "text" for c in raw.content):
        pytest.fail(f"content 里没有 text 块: {raw.content}")


async def test_call_tool_unknown_name(client):
    """tools/call 打不存在的工具:返回 ToolError,不崩连接。"""
    try:
        await client.call_tool("不存在的工具", {})
    except ToolError as e:
        print(f"\n[tools/call 未知工具] ToolError: {e}")
        return
    pytest.fail("调用不存在的工具居然成功了")


async def test_resources_and_prompts_are_empty(client):
    """resources/* 与 prompts/*:本 server 没注册,应返回空列表而不是报错。"""
    resources = await client.list_resources()
    templates = await client.list_resource_templates()
    prompts = await client.list_prompts()
    print(f"\n[resources/list]={resources} [resources/templates/list]={templates} [prompts/list]={prompts}")

    if list(resources) or list(templates) or list(prompts):
        pytest.fail("本 server 没注册 resource/prompt,应全为空")


async def test_read_unknown_resource_and_prompt(client):
    """resources/read 与 prompts/get 打到不存在的条目:返回 MCPError。"""
    for label, coro in [
        ("resources/read", client.read_resource("file:///不存在")),
        ("prompts/get", client.get_prompt("不存在的 prompt")),
    ]:
        try:
            await coro
            pytest.fail(f"{label} 对不存在的条目居然成功了")
        except MCPError as e:
            print(f"\n[{label}] MCPError: {e}")


# ---------------------------------------------------------------------------
# 3. 当前协议版本下不可用的方法
# ---------------------------------------------------------------------------

async def test_ping_not_available(client):
    """ping:低层 server 只在 on_ping 非 None 时注册,FastMCP 不传,故未注册。

    另外 2026-07-28 的方法表里也没有 ping,即使注册也会被版本门挡住。
    """
    try:
        await client.ping()
    except MCPError as e:
        print(f"\n[ping] MCPError: {e}")
        return
    pytest.fail("ping 本应不可用,居然成功了")


async def test_completion_not_available(client):
    """completion/complete:同样是 on_completion 为 None 时不注册。"""
    ref = mcp_types.PromptReference(type="ref/prompt", name="greet_user")
    try:
        await client.complete(ref, {"name": "name", "value": "大哥"})
    except MCPError as e:
        print(f"\n[completion/complete] MCPError: {e}")
        return
    pytest.fail("completion/complete 本应不可用,居然成功了")


async def test_logging_set_level_blocked_client_side(client):
    """logging/setLevel:2026-07-28 没有 per-session 服务端状态,客户端直接拒绝发送。"""
    try:
        await client.set_logging_level("debug")
    except RuntimeError as e:
        print(f"\n[logging/setLevel] 客户端拦截: {e}")
        return
    pytest.fail("set_logging_level 本应被客户端拦截,居然没拦")


# ---------------------------------------------------------------------------
# 4. 通知:notifications/progress
# ---------------------------------------------------------------------------

async def test_progress_notification_delivered_to_client():
    """notifications/progress:服务端 report_progress → 客户端 progress_handler 回调。

    query_system_info 分四步上报 25/50/75/100,这里验证通知确实回流到了客户端。
    需要带 progress_handler,故不用 client fixture,自己开连接。
    """
    seen: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        seen.append((progress, total, message))

    async with Client(MCP_URL, progress_handler=on_progress) as c:
        result = await c.call_tool("query_system_info", {"query_name": "进度用例"})

    print(f"\n[notifications/progress] 收到 {len(seen)} 条: {seen}")
    if [p for p, _, _ in seen] != [25.0, 50.0, 75.0, 100.0]:
        pytest.fail(f"进度序列不对: {seen}")
    if result.data["query_name"] != "进度用例":
        pytest.fail(f"结果不对: {result.data}")


# ---------------------------------------------------------------------------
# 5. 扩展方法:tasks/*
# ---------------------------------------------------------------------------

async def test_tasks_get_polls_until_terminal(client):
    """tasks/get:提交后台任务后轮询状态直到终态。

    这是 agent 若要手工控制任务时需要的最小回路;正常 agent 不会这么写,
    因为 TasksClientExtension 已经在 client.call_tool 内部透明地做完了。
    """
    task = await call_tool_task(
        client, "run_background_job", {"job_name": "协议用例", "duration_seconds": 2}
    )
    if not task.task_id:
        pytest.fail(f"没拿到 task_id: {task}")
    print(f"\n[tasks/get] 已提交 taskId={task.task_id}")

    while True:
        status = await task.status()  # 底层就是一次 tasks/get
        print(f"    status={status.status:<10} message={status.status_message or '（无）'}")
        if status.status in TERMINAL:
            break
        if status.status != "working":
            pytest.fail(f"意外状态: {status.status}")
        await asyncio.sleep(0.3)

    if status.status != "completed":
        pytest.fail(f"任务没成功: {status.status}")

    result = await task.result()
    if result.data["job_name"] != "协议用例":
        pytest.fail(f"结果不对: {result.data}")


async def test_tasks_cancel_moves_to_cancelled(client):
    """tasks/cancel:协作式取消,任务转 cancelled 终态。"""
    task = await call_tool_task(
        client, "run_background_job", {"job_name": "待取消", "duration_seconds": 30}
    )
    print(f"\n[tasks/cancel] 提交 taskId={task.task_id} 后取消")

    await task.cancel()
    status = await task.wait()
    print(f"[tasks/cancel] 取消后 status={status.status}")

    if status.status != "cancelled":
        pytest.fail(f"取消后状态应为 cancelled,实际 {status.status}")

    # 默认 raise_on_error=True,cancelled 会抛 ToolError
    try:
        await task.result()
        pytest.fail("cancelled 的任务取结果居然成功了")
    except ToolError as e:
        print(f"[tasks/cancel] 取结果如期抛错: {e}")


async def test_tasks_update_on_working_task_is_noop(client):
    """tasks/update:给一个没在等输入的任务回填,服务端接受但无效果(空 ack)。

    真正有意义的场景是任务停在 input_required 时回填答案,本 server 没用到。
    """
    task = await call_tool_task(
        client, "run_background_job", {"job_name": "回填探针", "duration_seconds": 3}
    )
    try:
        await client.session.send_request(
            UpdateTaskRequest(
                params=UpdateTaskRequestParams(task_id=task.task_id, input_responses={"x": "y"})
            ),
            mcp_types.Result,
        )
        print(f"\n[tasks/update] 对 working 任务回填:服务端接受,无报错")
    except MCPError as e:
        pytest.fail(f"tasks/update 意外失败: {e}")

    final = await task.wait()
    print(f"[tasks/update] 任务不受影响,仍跑到 {final.status}")
    if final.status != "completed":
        pytest.fail(f"回填不应影响任务,但状态是 {final.status}")
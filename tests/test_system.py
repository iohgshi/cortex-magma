async def test_query_system_info(client):
    """调一次工具,打印最终结果和期间收到的进度通知。"""

    print("start")
    async def on_progress(value: float, total: float | None, message: str | None) -> None:
        print("on_progress", (value, total, message))

    # progress_handler 优先级高于 Client 构造时传的那个,这里按调用传
    result = await client.call_tool(
        "query_system_info",
        {"query_name": "系统用例"},
        progress_handler=on_progress,
    )
    data = result.data
    print(f"\n[结果] elapsed={data['elapsed_seconds']}s")

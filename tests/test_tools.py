"""工具注册测试。"""


async def test_all_tools_registered(client):
    """三个工具都应注册到共享 mcp 实例上。"""
    names = {t.name for t in await client.list_tools()}
    assert names == {"greet_user", "query_system_info", "run_background_job"}

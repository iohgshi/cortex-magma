"""greet_user 工具测试。"""


async def test_greet_user(client):
    """带名字调用,返回固定问候语。"""
    result = await client.call_tool("greet_user", {"name": "测试"})
    assert result.data == "我是cortex-magma"

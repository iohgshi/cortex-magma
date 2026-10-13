"""query_system_info 工具测试。"""


async def test_query_system_info(client):
    """四个查询段齐全,耗时与四步模拟延迟(约 7 秒)吻合。"""
    result = await client.call_tool("query_system_info", {})
    data = result.data

    assert data["query_id"]
    assert data["query_name"] == "系统信息查询"  # 未传参时用默认值
    for section in ("current_info", "cpu", "memory", "disk"):
        assert section in data, f"缺少 {section} 段"
    # 1(CPU 采样)+ 1 + 2 + 3(模拟延迟),留一点余量
    assert data["elapsed_seconds"] >= 6.5

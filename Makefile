.PHONY: sync server test add

sync:            ## 按 uv.lock 装依赖
	uv sync

server:          ## 启动 MCP server(0.0.0.0:8000,前台运行)
	uv run cortex-magma

test:            ## 跑测试。需先在另一个终端 make server
	uv run pytest tests/test_system.py -v

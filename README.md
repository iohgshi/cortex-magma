# cortex-magma

一个基于 [FastMCP](https://github.com/jlowin/fastmcp) 的 MCP(Model Context Protocol)server,
提供系统信息查询、后台任务执行等工具。

## 安装

从 Git 仓库安装(不发布到 PyPI):

```bash
pip install "git+ssh://git@github.com/iohgshi/cortex-magma.git"
```

本地开发:

```bash
git clone git@github.com:iohgshi/cortex-magma.git
cd cortex-magma
uv sync
```

## 运行

装完包后直接用命令行入口:

```bash
cortex-magma        # 或 uv run cortex-magma(开发时)
```

默认监听 `0.0.0.0:8000`,MCP 客户端接入地址为 `http://127.0.0.1:8000/mcp`。
也支持 `uv run python -m cortex_magma`。

## 在 pi 中接入

`pi` 走 Streamable HTTP,所以用 `--url` 接入(server 需要已经在跑):

```bash
pi mcp add cortex-magma \
  --url http://127.0.0.1:8000/mcp \
  --description "系统信息与后台任务工具:query_system_info 查询本机 CPU/内存/磁盘;run_background_job 提交耗时后台任务并按秒回报进度;greet_user 探活"
```

`--description` 会被写进 pi 的 system prompt,模型靠它决定何时调用,所以要写清**每个工具做什么**,
不要只写"生成问候语等工具"这种以偏概全的说法 —— 后两个工具就没被提及,模型基本不会去调。

其他常用选项:

| 选项 | 用途 |
| --- | --- |
| `-l` / `--local` | 写进项目的 `.pi/mcp.json` 而不是全局 `~/.pi/agent/mcp.json`,便于随仓库共享 |
| `--exposure <mode>` | 工具暴露方式:`codemode`(默认)、`deferred`、`direct`、`hidden` |
| `--header KEY=VALUE` | 给请求加 HTTP 头,可重复 |

接完用 `pi mcp list` 确认状态和工具是否被正确识别:

```bash
pi mcp list
```

## 测试

测试是打真实 HTTP 的,所以需要先在另一个终端把 server 起起来:

```bash
make server   # 终端 1
make test     # 终端 2
```

换端口用 `MCP_URL` 覆盖:

```bash
MCP_URL=http://127.0.0.1:9000/mcp/ uv run pytest -v
```

## 工具

| 工具 | 说明 |
| --- | --- |
| `greet_user` | 生成一句问候语,用于探活 |
| `query_system_info` | 分四段采集并返回 CPU / 内存 / 磁盘等系统信息,期间上报进度 |
| `run_background_job` | 后台任务,需以任务模式提交,按秒上报进度 |

## 代码结构

```
src/cortex_magma/
├── server.py          # 入口:mcp 实例 + lifespan + 工具注册
└── tools/             # 一个模块一个工具域,各自导出 register(mcp)
```

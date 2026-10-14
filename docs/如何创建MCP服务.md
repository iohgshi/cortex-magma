# 如何创建一个 MCP 服务

面向没写过 MCP 服务的人。照着走一遍,你会得到一个能被 Claude、pi 等客户端接入的
HTTP MCP server,别人 `pip install` 之后就能跑。

示例用 Python + [FastMCP](https://github.com/jlowin/fastmcp)(目前最主流的 MCP Python SDK)。
文末的示例代码来自真实可运行的项目,18 个测试全绿。

---

## 目录

1. [MCP 服务是什么](#1-mcp-服务是什么)
2. [创建项目](#2-创建项目)
3. [项目结构](#3-项目结构)
4. [写入口文件](#4-写入口文件serverpy)
5. [写第一个工具](#5-写第一个工具)
6. [长耗时工具与进度通知](#6-长耗时工具与进度通知)
7. [后台任务](#7-后台任务tasks-扩展)
8. [运行与传输方式](#8-运行与传输方式)
9. [打包与分发](#9-打包与分发)
10. [写测试](#10-写测试)
11. [接入客户端](#11-接入客户端)
12. [踩坑清单](#12-踩坑清单)

---

## 1. MCP 服务是什么

MCP(Model Context Protocol)是让 AI 应用调用外部能力的标准协议。一个 MCP server 本质上就是
**一组带描述的函数**:

- 有名字(`greet_user`)
- 有描述(告诉模型"什么时候该调它")
- 有带说明和约束的参数(生成的 JSON Schema 模型能直接看懂)
- 返回结构化数据

模型看到的是这些元数据,决定要不要调、怎么调。所以**描述写得好不好,直接决定服务有没有人用**。

MCP server 可以暴露三种原语,本文只讲最常用的 **tools**(函数)。resources(可读数据)和
prompts(提示词模板)结构类似,FastMCP 里写法也几乎一样。

---

## 2. 创建项目

```bash
uv init --package --name my-mcp-server --python 3.12 my-mcp-server
cd my-mcp-server
uv add "fastmcp[tasks]"
uv add --dev pytest pytest-asyncio
```

### `--package` 必须加

不加 `uv init` 生成的是**虚拟项目**——没有 `[build-system]`。后果是:

- `uv sync` 只装依赖,**永远不安装项目自己**
- 没有命令行入口
- 不能 `pip install`

`uv init --package` 会自动生成 `src/` 布局和 `[build-system]`,省掉这堆麻烦。

> 已经有项目了?直接往 `pyproject.toml` 里补下面的 `[build-system]` 和 `[tool.*.packages]` 即可。

### pyproject.toml

```toml
[project]
name = "my-mcp-server"
version = "0.1.0"
description = "一句话说明这个 server 提供什么"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastmcp[tasks]>=4.1.0",   # [tasks] 额外依赖:后台任务扩展 + 客户端库
]

[project.scripts]
my-mcp-server = "my_mcp_server.server:main"   # 装完直接敲 my-mcp-server 起服务

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_mcp_server"]              # 告诉构建后端包在哪

[dependency-groups]
dev = ["pytest>=9.1.1", "pytest-asyncio>=1.4.0"]

[tool.pytest.ini_options]
asyncio_mode = "auto"        # async 测试不用再挂 @pytest.mark.asyncio
testpaths = ["tests"]
pythonpath = ["."]           # 让测试能 import 到 tests/conftest.py
addopts = "-s"               # 不捕获 stdout,测试里的 print 直接显示
```

**构建后端两种都行**:

- `hatchling`(本文用的)。选它是因为能显式写 `packages`,把包名从构建产物里摘干净。
- `uv_build`(uv 自带,`uv init --package` 的默认值)。零额外依赖,同样能装。

`[project.scripts]` 是体验的关键:装完之后用户不用管你的源码结构,直接敲命令名就能起服务。

---

## 3. 项目结构

```
my-mcp-server/
├── pyproject.toml
├── README.md
├── src/
│   └── my_mcp_server/
│       ├── __init__.py       # 对外导出
│       ├── __main__.py       # 支持 python -m my_mcp_server
│       ├── server.py         # 入口:mcp 实例 + lifespan + 注册 + main()
│       └── tools/
│           ├── __init__.py   # 汇总各模块的 register
│           ├── greet.py      # 最简单的同步工具
│           ├── system.py     # 长耗时 + 进度通知
│           └── job.py        # 后台任务
└── tests/
    ├── conftest.py           # client fixture
    └── test_*.py
```

**为什么必须用 `src/` 布局**:如果你有个顶层包叫 `tools`,flat 布局会把 `tools` 原样放进
`site-packages/tools/`——这几乎必然和别的库撞名(项目里的 `tools/` 脚本目录也可能被误 import)。
`src/` 布局让包名带上项目前缀(`my_mcp_server.tools`),wheel 里也只会有你自己的包。

验证构建产物干不干净——应该只有你的包和 dist-info:

```bash
uv build
python -c "import zipfile,glob; print('\n'.join(sorted(zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist())))"
```

---

## 4. 写入口文件(server.py)

```python
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp_tasks import TasksExtension

from . import tools

DEFAULT_EXECUTOR_MAX_WORKERS = 64
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

logging.basicConfig(level=logging.INFO)      # 模块级配置,不要放 __main__ 里


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=DEFAULT_EXECUTOR_MAX_WORKERS))
    yield


mcp = FastMCP("my-mcp-server", lifespan=_lifespan)
mcp.add_extension(TasksExtension())   # 后台任务扩展,默认内存队列,不需要 Redis
tools.register(mcp)


def main() -> None:
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    main()
```

`__main__.py`:

```python
from .server import main

main()
```

三个关键约定:

**1. `mcp` 实例只建一次**,放在 `server.py`,其它模块从这儿导入。

**2. 模块级绝对不要调 `mcp.run()`。** 一旦在 import 时就跑起来,任何 `import my_mcp_server`
都会启动服务,测试直接卡死。跑服务的逻辑一律收在 `main()` 里——这也是 `[project.scripts]` 需要的形态。

**3. lifespan 里放大线程池。** 默认 executor 的 worker 很少,几个阻塞型工具并发就互相饿死。

---

## 5. 写第一个工具

**一个工具一个模块**,模块里放**普通函数 + 一个 `register(mcp)`**。

```python
# src/my_mcp_server/tools/greet.py
import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

logger = logging.getLogger("my-mcp-server.greet")

GREET_USER_DESCRIPTION = '''生成一句问候语。当用户想打招呼、或测试服务是否在线时调用。

触发示例:
- 用户说「hi」「你好」「在吗」→ 调用本工具,用户没报名字时 name 填 "朋友"
- 用户说「测试下服务通不通」→ 调用本工具,name 填 "test"

返回示例:name="大哥" → 返回 "我是 my-mcp-server"'''


def greet(name: Annotated[str, Field(description="要问候的人的名字")]) -> str:
    logger.info("greet_user 被调用: name=%r", name)   # 日志用 %s 占位,别用 f-string
    return "我是 my-mcp-server"


def register(mcp: FastMCP) -> None:
    mcp.tool(greet, name="greet_user", description=GREET_USER_DESCRIPTION)
```

在 `tools/__init__.py` 里挂上:

```python
from . import greet, job, system

_MODULES = (greet, job, system)


def register(mcp: FastMCP) -> None:
    for module in _MODULES:
        module.register(mcp)
```

新增工具时:建一个模块 → 写函数和 `register` → 加进 `_MODULES`。完事。

### 六条硬约定

**1. 注册是显式的,不做 import 副作用。**
不要在模块顶层直接 `mcp.tool(...)` 然后靠 import 触发注册。那样导入顺序决定注册顺序,
测试也没法单独拿到函数。统一走 `register(mcp)`。

**2. 工具函数保持"纯"。**
不依赖注册实例,`from my_mcp_server.tools.greet import greet` 就能直接调。测试和复用都靠这个。

**3. 参数用 `Annotated` + `Field(description=...)`。**
生成的 JSON Schema 自带说明,模型不用猜参数含义。`Field` 还能加约束:

```python
duration_seconds: Annotated[int, Field(description="任务总时长(秒)", ge=1, le=60)] = 5
```

这样不用手写校验,超范围的值会被 FastMCP 直接拒掉。

**4. 描述写"什么时候该调",而不是"它干了什么"。**

这是全文最重要的一条。描述是模型唯一的决策依据。写成"返回问候语"模型不知道什么时候用;
写成"用户打招呼时调用 / 测试服务是否在线时调用"才有信息量。把**触发示例**直接写进去:

```
- 用户说「hi」「在吗」→ 调用本工具,name 填 "朋友"
- 用户说「测试下服务通不通」→ 调用本工具,name 填 "test"
```

**5. 长描述放模块级常量**,别塞在 docstring 里——两者都会进 schema,容易重复。

**6. 别用 f-string 记日志。** 用 `logger.info("...%s", value)`,大对象不格式化就不产生字符串开销。

---

## 6. 长耗时工具与进度通知

超过几秒的工具要报进度,否则用户面对一个不动的光标。FastMCP 通过 `Context` 提供:

```python
from fastmcp import Context

async def run(query_name: str, ctx: Context) -> dict:
    current_info = _query_current_info()
    await ctx.report_progress(25, 100)        # (已完成, 总量)

    cpu = await asyncio.to_thread(_query_cpu)  # ← 必须
    await ctx.report_progress(50, 100)
    ...
```

### 最大的坑:阻塞调用会卡死事件循环

`psutil.cpu_percent(interval=1)`、`time.sleep(2)`、同步 HTTP 请求这类**同步阻塞**调用,
一旦直接跑在事件循环里,整个 server 在这几秒内什么都干不了——**包括发进度通知**。

症状:客户端干等好几秒,然后进度一次性跳到 100%。你以为进度通知坏了,其实是事件循环被堵了。

处理:**阻塞调用一律包 `asyncio.to_thread()`**,再配合 lifespan 里放大的线程池。

### 客户端侧

```python
async def on_progress(progress: float, total: float | None, message: str | None) -> None:
    print(progress, total, message)

result = await client.call_tool("query_system_info", {...}, progress_handler=on_progress)
```

注意 `progress_handler` **按调用传的优先级高于** `Client` 构造时传的那个。

### 拿到调用方信息(调试很有用)

```python
from fastmcp.server.dependencies import get_http_request

def _client_info() -> str:
    try:
        request = get_http_request()
    except RuntimeError:      # 非 HTTP 传输(stdio、后台 worker)时没有 request
        return "unknown"
    client = request.client  # Starlette AddressPair: host + port
    return f"{client.host}:{client.port}" if client else "unknown"
```

**后台任务的 worker 跑在没有 HTTP request 的上下文里**,忘了 catch 这个 `RuntimeError`,
后台任务一执行就直接抛异常。

---

## 7. 后台任务(tasks 扩展)

有些任务不该让客户端干等(跑几分钟、要人手动确认、agent 想并行做几件事)。
FastMCP 的 tasks 扩展(SEP-2663,底层是 [Docket](https://github.com/aiwire-tech/docket))
支持把工具提交成后台任务。

启用只要一行:

```python
mcp.add_extension(TasksExtension())   # 默认内存队列,不需要 Redis/Postgres
```

然后在工具上声明:

```python
from fastmcp.utilities.tasks import TaskConfig

def register(mcp: FastMCP) -> None:
    mcp.tool(
        run_background_job,
        name="run_background_job",
        description=__DESCRIPTION,
        task=TaskConfig(mode="required"),   # 只能以任务方式提交
    )
```

`TaskConfig(mode=...)` 三档:

| mode | 含义 |
| --- | --- |
| `"required"` | 只能以任务方式提交 |
| `"optional"`(等于旧的 `task=True`) | 两种都行,客户端可以直接阻塞调用 |
| `"disabled"`(默认) | 普通工具 |

工具本质上就是"必须跑很久、不适合让客户端干等"的,用 `"required"`。

### 客户端两种调用方式

**同步**:客户端 `call_tool` 阻塞到结束,拿最终结果。(mode 为 required 时不可用)

**后台任务**:不阻塞,拿句柄再轮询:

```python
from fastmcp_tasks import call_tool_task

task = await call_tool_task(client, "run_background_job", {"duration_seconds": 3})
task.task_id                                  # 提交即刻拿到,不用等

while True:
    status = await task.status()
    print(status.status, status.status_message)
    if status.status in ("completed", "failed", "cancelled"):
        break
    await asyncio.sleep(0.3)

result = await task.result()                  # completed 之后取;取消/失败会抛错
await task.cancel()                           # 随时可取消
```

**后台模式下进度不走 `notifications/progress`**,而是写进任务的 `status_message`,
由 `tasks/get` 轮询拿到。所以 `report_progress` 的第三个参数(message)在这里特别有用。

---

## 8. 运行与传输方式

```python
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

- **Streamable HTTP**,客户端接入地址 `http://127.0.0.1:8000/mcp`(结尾斜杠可有可无)。
- `host="0.0.0.0"` 才能被容器/局域网访问。只写 `127.0.0.1` 的话外部连不上。
- 其它传输:`transport="stdio"`(本地子进程,Claude Desktop 常用)、
  `transport="sse"`(旧版,新项目别用)。

**别用裸 curl 测**:

```bash
curl -X POST http://127.0.0.1:8000/mcp    # 返回 400 —— 正常!
```

Streamable HTTP 要求 `Accept: application/json, text/event-stream` 等头,裸 curl 必然 400。
这不代表服务有问题,用 MCP 客户端连,或者:

```bash
npx @modelcontextprotocol/inspector http://127.0.0.1:8000/mcp
```

Inspector 是官方的调试 UI,能列出所有工具、手动调用、看 schema。**开发期强烈建议挂上。**

---

## 9. 打包与分发

```bash
uv build                                   # dist/*.whl 和 *.tar.gz
pip install -e .                           # 本地开发,可编辑
pip install "git+ssh://git@github.com/<user>/my-mcp-server.git"    # 从 git 装
pip install dist/my_mcp_server-0.1.0-py3-none-any.whl               # 从 wheel 装
```

装完就有命令行入口(`my-mcp-server`),和 `[project.scripts]` 里声明的一致。

### 发到 PyPI

不发布的话不用管。真要发:

```bash
uv build
uv publish --token <你的 PyPI token>
```

PyPI 上的**包名必须全局唯一**,发上去就基本不能改了(可以加字母后缀,但没法删除重发)。
建议先用 `my-mcp-server-<你的用户名>` 这种带后缀的名字在 PyPI 上搜一下确认没人占。

发布前记得在 `pyproject.toml` 补上元数据:

```toml
license = "MIT"
authors = [{ name = "你的名字", email = "you@example.com" }]
```

以及**认真写 README**——PyPI 页面就是它。

---

## 10. 写测试

### 别用内存传输

FastMCP 支持 `Client(mcp)` 直连内存,不用起进程,看起来很美。但它**把真正的线上行为全遮住了**:
传输层、HTTP 头、会话管理、后台任务队列、进度通知,一个都测不到。测试全绿,线上照样挂。

**打真实 HTTP**:

```python
# tests/conftest.py
import os
import pytest
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp/")


@pytest.fixture
async def client():
    async with Client(MCP_URL) as c:
        yield c
```

代价是 server 得先起来。配个 Makefile:

```makefile
server:          ## 启动 MCP server(0.0.0.0:8000,前台运行)
	uv run my-mcp-server

test:            ## 跑测试。需先在另一个终端 make server
	uv run pytest -v
```

```bash
make server                              # 终端 1
make test                                # 终端 2
MCP_URL=http://127.0.0.1:9000/mcp/ uv run pytest -v   # 换端口
```

### 几个配置说明

- `asyncio_mode = "auto"`:async 测试函数不用挂 `@pytest.mark.asyncio`。
- `addopts = "-s"`:关掉输出捕获,测试里 `print` 直接显示。调协议时非常有用。
- `pythonpath = ["."]`:让测试能 import 到 `tests/conftest.py`。

### 测试什么

除了常规的返回值断言,**优先测协议本身**。这个项目里最有价值的几个用例全是协议层的:

- `initialize` 握手返回对不对
- `tools/list` 里该有的工具在不在
- 调不存在的工具、参数类型错、参数越界,分别报什么错
- 进度通知收没收得到、顺序对不对
- 后台任务能不能提交、轮询、取消,取消后取结果是否如期报错

写这类用例时别偷懒用黑盒断言,把"发什么 → 期望什么"显式写出来:

```python
status = await task.status()
if status.status != "completed":
    pytest.fail(f"任务没成功: {status.status}")
```

---

## 11. 接入客户端

### pi

```bash
pi mcp add my-mcp-server \
  --url http://127.0.0.1:8000/mcp \
  --description "一句话说明这个 server 提供什么能力"

pi mcp list
```

`--description` 是**写进 pi 的 system prompt** 的,模型靠它决定何时调用。所以要写清
**每个工具做什么**;写成"提供各种工具"这种概括,等于把具体工具对模型隐藏了。

其它常用项:`-l/--local`(写项目级 `.pi/mcp.json`)、`--exposure`
(codemode/deferred/direct/hidden)、`--header K=V`。

### Claude Desktop / Claude Code

stdio 传输,配置写在 JSON 里:

```json
{
  "mcpServers": {
    "my-mcp-server": {
      "command": "uv",
      "args": ["--directory", "/abs/path/to/my-mcp-server", "run", "my-mcp-server"]
    }
  }
}
```

HTTP 传输:

```json
{
  "mcpServers": {
    "my-mcp-server": { "type": "http", "url": "http://127.0.0.1:8000/mcp" }
  }
}
```

### 其它客户端

核心就两件事:**传输方式**(stdio 还是 URL)和**描述写得好不好**。
接完之后拿模型真问一句"你能做什么",看它会不会主动调你的工具——不会的话,回去改描述。

---

## 12. 踩坑清单

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `uv sync` 装完还是 `ModuleNotFoundError` | 没 `[build-system]`,被当成虚拟项目 | 加 `[build-system]` + `packages` |
| 顶层包 `tools` 和别的库冲突 | flat 布局把包名原样放进 site-packages | 换 `src/` 布局 |
| `import` 一下就把服务起起来了 | 模块级调了 `mcp.run()` | 收进 `main()` |
| `python -m pkg.server` 平白多建一个实例 | 包 `__init__` 导入一遍,runpy 再执行一遍 | 加 `__main__.py`,用 `python -m pkg` |
| 客户端干等,进度最后一次性到 100% | 阻塞调用卡住事件循环,通知发不出去 | `asyncio.to_thread()` 包起来 |
| 并发几个工具就全卡住 | 默认 executor worker 太少 | lifespan 里 `set_default_executor` 调大 |
| 后台任务一执行就抛异常 | worker 里没有 HTTP request,`get_http_request()` 抛 `RuntimeError` | catch 后返回 `"unknown"` |
| 测试报 `Client failed to connect` | server 没起 | 先 `make server` |
| `curl` POST `/mcp` 返回 400 | Streamable HTTP 要求特定 `Accept` 头 | 用 MCP 客户端或 Inspector,别用裸 curl |
| 模型从来不调你的工具 | 描述没写"什么时候该调" | 加触发示例 |
| 偶发卡在 `PASSED` 之前不动 | client 关闭 session 时 transport 偶尔挂住 | fixture 收尾加超时兜底 |
| 容器/局域网里连不上 | `host` 写的 `127.0.0.1` | 改 `0.0.0.0` |

---

## 附:新建一个工具的完整清单

- [ ] 建 `src/<pkg>/tools/<name>.py`
- [ ] 参数用 `Annotated[..., Field(description="...")]`,范围用 `ge`/`le`
- [ ] 描述写成 `*_DESCRIPTION` 常量,**包含触发示例**
- [ ] 阻塞调用包 `asyncio.to_thread()`
- [ ] 超过几秒就 `await ctx.report_progress(...)`
- [ ] 写 `register(mcp)`,需要后台执行就加 `task=TaskConfig(mode="required")`
- [ ] 在 `tools/__init__.py` 的 `_MODULES` 里加一行
- [ ] 在 `tests/` 补测试(返回值 + 参数校验 + 进度/任务生命周期)
- [ ] 在客户端的 `--description` 里把新工具补上

"""支持 `python -m cortex_magma` 启动 server。

不要写 `python -m cortex_magma.server`:那样 server.py 会被执行两次
(先作为 cortex_magma.server 被包 __init__ 导入,再作为 __main__ 执行一遍),
平白多建一个 FastMCP 实例。
"""

from .server import main

main()

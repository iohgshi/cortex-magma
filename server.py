import logging

import tools  # noqa: F401  导入即注册所有工具

from app import mcp


def main():
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

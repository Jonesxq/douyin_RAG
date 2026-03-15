from __future__ import annotations

"""日志初始化模块。"""

import logging


def configure_logging() -> None:
    """
    功能：执行 configure_logging 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

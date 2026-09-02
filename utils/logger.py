"""
utils/logger.py - 结构化日志模块
统一日志格式，输出到文件和终端
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 全局 logger 实例
_logger: Optional[logging.Logger] = None
_log_file_path: Optional[Path] = None


def setup_logger(
    name: str = "bilibili_bot",
    log_dir: str = "storage/logs",
    level: int = logging.INFO
) -> logging.Logger:
    """
    初始化结构化日志器

    Args:
        name: logger 名称
        log_dir: 日志目录
        level: 日志级别

    Returns:
        配置好的 logger 实例
    """
    global _logger, _log_file_path

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    # 日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 日志文件名（按日期）
    today = datetime.now().strftime("%Y%m%d")
    log_file = log_path / f"bot_{today}.log"
    _log_file_path = log_file

    # 日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 文件 handler（UTF-8 编码）
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """
    获取已配置的 logger
    如果未初始化，先创建一个默认的
    """
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger


class BotLogger:
    """
    结构化日志封装
    提供统一的日志接口，支持 action/target/result 字段
    """

    def __init__(self, name: str = "bilibili_bot"):
        self._log = get_logger().getChild(name) if _logger else setup_logger().getChild(name)
        self._context: dict = {}

    def set_context(self, **kwargs):
        """设置日志上下文（自动附加到每条日志）"""
        self._context.update(kwargs)

    def clear_context(self):
        """清除日志上下文"""
        self._context = {}

    def _format(self, msg: str) -> str:
        """格式化日志消息，附加上下文"""
        if self._context:
            ctx_str = " | ".join(f"{k}={v}" for k, v in self._context.items())
            return f"{msg} | {ctx_str}"
        return msg

    def debug(self, msg: str, **kwargs):
        self._log.debug(self._format(msg), **kwargs)

    def info(self, msg: str, **kwargs):
        self._log.info(self._format(msg), **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log.warning(self._format(msg), **kwargs)

    def error(self, msg: str, **kwargs):
        self._log.error(self._format(msg), **kwargs)

    # ============ 业务日志快捷方法 ============

    def decision(self, action: str, target: str = "", reason: str = ""):
        """决策日志"""
        self.info(f"[决策] {action} {target or ''} | {reason}")

    def action_start(self, action: str, target: str = ""):
        """动作开始"""
        self.info(f"[开始] {action} {target}")

    def action_success(self, action: str, target: str = "", detail: str = ""):
        """动作成功"""
        self.info(f"[成功] {action} {target} {detail}")

    def action_failed(self, action: str, target: str = "", error: str = ""):
        """动作失败"""
        self.error(f"[失败] {action} {target} | {error}")

    def wait(self, seconds: float, reason: str = ""):
        """等待日志"""
        self.debug(f"[等待] {seconds:.0f}秒 {reason}")

    def stats(self, **kwargs):
        """统计日志"""
        stats_str = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.info(f"[统计] {stats_str}")


# 全局快捷函数
def get_bot_logger() -> BotLogger:
    """获取 BotLogger 实例"""
    return BotLogger()

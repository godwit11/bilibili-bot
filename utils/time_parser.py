"""
utils/time_parser.py - B站时间字符串解析
解析 "刚刚"、"3分钟前"、"昨天 15:30"、"10:30" 等格式
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_bilibili_time(time_str: str) -> Optional[datetime]:
    """
    解析 B站通知/消息的时间字符串

    Args:
        time_str: B站格式的时间字符串，如 "刚刚"、"3分钟前"、"昨天 15:30"、"10:30" 等

    Returns:
        对应的 datetime 对象，解析失败返回 None
    """
    if not time_str:
        return None

    now = datetime.now()
    time_str = time_str.strip()

    # "刚刚"、"刚刚~
    if '刚刚' in time_str:
        return now

    # "X秒前"
    m = re.search(r'(\d+)\s*秒.*前', time_str)
    if m:
        seconds = int(m.group(1))
        return now - timedelta(seconds=seconds)

    # "X分钟前"
    m = re.search(r'(\d+)\s*分.*前', time_str)
    if m:
        minutes = int(m.group(1))
        return now - timedelta(minutes=minutes)

    # "X小时前"
    m = re.search(r'(\d+)\s*小.*前', time_str)
    if m:
        hours = int(m.group(1))
        return now - timedelta(hours=hours)

    # "昨天 XX:XX"
    m = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
    if m:
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)

    # "前天 XX:XX"
    m = re.search(r'前天\s*(\d{1,2}):(\d{2})', time_str)
    if m:
        day_before = now - timedelta(days=2)
        return day_before.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)

    # "今天 HH:MM"（如 "今天 10:08"）
    m = re.search(r'^今天\s*(\d{1,2}):(\d{2})', time_str)
    if m:
        try:
            from datetime import time as datetime_time
            return datetime.combine(now.date(), datetime_time(int(m.group(1)), int(m.group(2))))
        except ValueError:
            return None

    # "XX:XX"（今天的时间）
    m = re.search(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        try:
            from datetime import time as datetime_time
            return datetime.combine(now.date(), datetime_time(int(m.group(1)), int(m.group(2))))
        except ValueError:
            return None

    # "MM-DD HH:MM" 或 "MM/DD HH:MM"
    m = re.search(r'^(\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})', time_str)
    if m:
        try:
            month, day, hour, minute = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            year = now.year
            # 简单处理：如果月份大于当前月份，说明是去年
            if month > now.month:
                year -= 1
            return datetime(year, month, day, hour, minute, 0)
        except ValueError:
            return None

    # "YYYY年MM月DD日 HH:MM"（中文格式，如 "2026年8月24日 12:42"）
    m = re.search(r'^(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})', time_str)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), 0
            )
        except ValueError:
            return None

    # "YYYY-MM-DD HH:MM" 或 "YYYY/MM/DD HH:MM"
    m = re.search(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})', time_str)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), 0
            )
        except ValueError:
            return None

    return None


def is_within_seconds(time_str: str, seconds: int) -> bool:
    """
    判断时间字符串表示的时间是否在 N 秒之内（用于 "刚刚" 类判断）

    Args:
        time_str: 时间字符串
        seconds: 秒数

    Returns:
        True 如果时间在 N 秒之内
    """
    parsed = parse_bilibili_time(time_str)
    if parsed is None:
        return False
    return (datetime.now() - parsed).total_seconds() <= seconds

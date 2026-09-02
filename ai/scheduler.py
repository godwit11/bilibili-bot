"""
ai/scheduler.py - 行为节奏调度器
控制 Bot 的行为节奏，避免被检测
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ScheduleStats:
    """调度统计"""
    comments_today: int = 0
    browse_today: int = 0
    search_today: int = 0
    session_start: datetime = None

    def __post_init__(self):
        if self.session_start is None:
            self.session_start = datetime.now()


class BehaviorScheduler:
    """
    行为调度器
    控制动作节奏，避免触发反作弊
    """

    def __init__(self):
        # 时间配置（秒）
        self.min_action_gap = 8      # 最小动作间隔
        self.max_action_gap = 45      # 最大动作间隔

        # 评论限制（基础值，会根据时段动态调整）
        self.max_comments_per_hour = 10   # 每小时最多评论数
        self.base_max_comments_per_day = 50  # 基础每天限额
        self.comment_cooldown = 30       # 同一视频评论冷却（秒）

        # 浏览限制
        self.max_browse_per_hour = 30    # 每小时最多浏览数

        # 统计
        self.stats = ScheduleStats()
        self._comment_timestamps = []     # 评论时间戳列表
        self._browse_timestamps = []      # 浏览时间戳列表

    def _get_time_based_multiplier(self) -> float:
        """
        根据当前时段返回活跃度乘数
        模拟真实用户的活动曲线：
        - 凌晨(0-6点)：极低活跃 0.2
        - 早上(6-9点)：低活跃 0.5
        - 上午(9-12点)：中等 0.8
        - 中午(12-14点)：较低 0.6
        - 下午(14-18点)：中等 0.8
        - 傍晚(18-21点)：高活跃 1.2
        - 晚上(21-24点)：最高 1.5
        """
        hour = datetime.now().hour

        if 0 <= hour < 6:
            return 0.2
        elif 6 <= hour < 9:
            return 0.5
        elif 9 <= hour < 12:
            return 0.8
        elif 12 <= hour < 14:
            return 0.6
        elif 14 <= hour < 18:
            return 0.8
        elif 18 <= hour < 21:
            return 1.2
        else:  # 21-24
            return 1.5

    def get_max_comments_today(self) -> int:
        """
        获取今日评论上限
        - 周末比工作日略高
        - 根据时段动态调整（傍晚/晚上可多评论）
        """
        now = datetime.now()
        # 周末上限略高
        is_weekend = now.weekday() >= 5
        base = self.base_max_comments_per_day * 1.2 if is_weekend else self.base_max_comments_per_day

        # 时段乘数（但总上限不超过基础值的 1.5 倍）
        time_multiplier = self._get_time_based_multiplier()
        final = int(base * time_multiplier)

        return max(10, min(final, int(self.base_max_comments_per_day * 1.5)))

    def should_take_break(self) -> bool:
        """
        决定是否应该休息一下
        - 根据时段动态调整休息概率
        - 凌晨和早上更容易休息
        """
        now = datetime.now()
        hour = now.hour

        # 凌晨强制休息概率高
        if 0 <= hour < 6:
            return random.random() < 0.6
        # 早上
        elif 6 <= hour < 9:
            return random.random() < 0.3
        # 上午/下午正常工作
        elif 9 <= hour < 18:
            return random.random() < 0.1
        # 傍晚/晚上不容易休息
        else:
            return random.random() < 0.05

    def get_rest_duration(self) -> float:
        """
        获取休息时长
        - 凌晨休息时间长（30-90分钟）
        - 白天休息短（3-10分钟）
        """
        hour = datetime.now().hour

        if 0 <= hour < 6:
            return random.uniform(1800, 5400)  # 30-90分钟
        elif 6 <= hour < 9:
            return random.uniform(300, 900)  # 5-15分钟
        else:
            return random.uniform(60, 300)  # 1-5分钟

    async def wait_before_action(self, action_type: str = "general"):
        """
        动作前等待（模拟真人思考/操作时间）
        """
        if action_type == "browse":
            wait_time = random.uniform(1.5, 4.0)
        elif action_type == "comment":
            wait_time = random.uniform(2.0, 5.0)  # 评论前要打字
        elif action_type == "search":
            wait_time = random.uniform(1.0, 3.0)
        elif action_type == "scroll":
            wait_time = random.uniform(0.5, 2.0)
        else:
            wait_time = random.uniform(self.min_action_gap, self.max_action_gap)

        await asyncio.sleep(wait_time)

    async def can_comment(self, bvid: str = None) -> tuple[bool, str]:
        """
        检查是否可以评论
        返回 (是否允许, 原因)
        """
        now = datetime.now()

        # 清理过旧的时间戳（1小时前的）
        self._comment_timestamps = [
            t for t in self._comment_timestamps
            if now - t < timedelta(hours=1)
        ]

        # 检查每小时限制
        if len(self._comment_timestamps) >= self.max_comments_per_hour:
            return False, f"已达每小时评论上限 ({self.max_comments_per_hour})"

        # 检查每天限制（动态，根据时段和周末调整）
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        comments_today = len([
            t for t in self._comment_timestamps
            if t >= today_start
        ])
        max_today = self.get_max_comments_today()
        if comments_today >= max_today:
            return False, f"已达今日评论上限 ({comments_today}/{max_today})"

        return True, "可以评论"

    async def can_browse(self) -> tuple[bool, str]:
        """检查是否可以浏览"""
        now = datetime.now()

        # 清理过旧时间戳
        self._browse_timestamps = [
            t for t in self._browse_timestamps
            if now - t < timedelta(hours=1)
        ]

        if len(self._browse_timestamps) >= self.max_browse_per_hour:
            return False, f"已达每小时浏览上限 ({self.max_browse_per_hour})"

        return True, "可以浏览"

    def record_comment(self):
        """记录一次评论"""
        now = datetime.now()
        self._comment_timestamps.append(now)
        self.stats.comments_today += 1

    def record_browse(self):
        """记录一次浏览"""
        now = datetime.now()
        self._browse_timestamps.append(now)
        self.stats.browse_today += 1

    def get_random_scroll_duration(self) -> float:
        """获取随机滚动时长"""
        return random.uniform(2.0, 5.0)  # 2-5秒

    def get_random_watch_duration(self) -> float:
        """获取随机观看时长（用于纯观看模式）"""
        return random.uniform(5.0, 30.0)  # 5-30秒

    def get_realistic_watch_duration(self, video_duration_seconds: int = 0) -> float:
        """
        根据视频实际时长计算真实感观看时间
        - 短视频（<2min）：看 40-60%
        - 中视频（2-10min）：看 20-35%
        - 长视频（>10min）：看 10-20%（最多看 3 分钟）
        - 最小观看时间 15 秒
        """
        if video_duration_seconds <= 0:
            return random.uniform(15.0, 45.0)

        if video_duration_seconds < 120:  # 短视频 < 2分钟
            ratio = random.uniform(0.40, 0.60)
        elif video_duration_seconds < 600:  # 中视频 2-10分钟
            ratio = random.uniform(0.20, 0.35)
        else:  # 长视频 > 10分钟
            ratio = random.uniform(0.10, 0.20)

        watch_time = video_duration_seconds * ratio
        # 最多看 180 秒（3分钟）
        return max(15.0, min(watch_time, 180.0))

    def should_comment_current_video(self) -> bool:
        """决定是否评论当前视频"""
        # 40% 概率评论
        return random.random() < 0.4

    def get_status(self) -> str:
        """获取当前状态"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        comments_today = len([
            t for t in self._comment_timestamps
            if t >= today_start
        ])

        return (
            f"今日评论: {comments_today}/{self.get_max_comments_today()} | "
            f"本小时浏览: {len(self._browse_timestamps)}/{self.max_browse_per_hour}"
        )

    async def wait_if_needed(self):
        """如果动作太频繁，等待一下"""
        now = datetime.now()

        # 检查最近的间隔
        if self._comment_timestamps:
            last = self._comment_timestamps[-1]
            gap = (now - last).total_seconds()
            if gap < self.min_action_gap:
                wait = self.min_action_gap - gap + random.uniform(0, 5)
                await asyncio.sleep(wait)

        if self._browse_timestamps:
            last = self._browse_timestamps[-1]
            gap = (now - last).total_seconds()
            if gap < 2:  # 最小浏览间隔
                wait = 2 - gap + random.uniform(0, 2)
                await asyncio.sleep(wait)

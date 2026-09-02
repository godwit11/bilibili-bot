"""
ai/decision.py - 决策引擎
AI 决定下一步做什么 action
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class Action(Enum):
    """可能的动作"""
    SEARCH = "search"           # 搜索关键词
    BROWSE_VIDEO = "browse"    # 浏览视频
    POST_COMMENT = "comment"    # 评论视频
    SCROLL_HOMEPAGE = "scroll" # 刷首页
    WATCH_VIDEO = "watch"      # 观看视频
    IDLE = "idle"             # 休息
    RANDOM_BROWSE = "random"  # 随机浏览


@dataclass
class DecisionContext:
    """决策上下文"""
    last_action: Optional[Action] = None
    last_action_time: Optional[datetime] = None
    last_comment_time: Optional[datetime] = None
    recent_bvids: list[str] = None  # 最近浏览的视频
    recent_comments: list[str] = None  # 最近评论的视频
    consecutive_idles: int = 0  # 连续休息次数
    session_start: datetime = None

    def __post_init__(self):
        if self.recent_bvids is None:
            self.recent_bvids = []
        if self.recent_comments is None:
            self.recent_comments = []
        if self.session_start is None:
            self.session_start = datetime.now()


@dataclass
class Decision:
    """决策结果"""
    action: Action
    target: Optional[str] = None  # 目标（如 bvid 或搜索关键词）
    reason: str = ""
    confidence: float = 1.0  # 置信度


class DecisionEngine:
    """
    决策引擎
    根据上下文决定下一步动作
    """

    # 搜索关键词池（运动爱好者人设）
    INTEREST_KEYWORDS = [
        # 核心运动爱好
        "跑步", "马拉松", "夜跑", "长跑", "短跑",
        "排球", "沙滩排球", "室内排球", "排球教学",
        "乒乓球", "乒乓球技巧", "乒乓球正手", "乒乓球反手",
        # 扩展运动兴趣
        "篮球", "足球", "羽毛球", "网球",
        "健身", "体能训练", "拉伸", "热身",
        "运动损伤", "运动恢复", "运动拉伸",
        # 偶尔关注（模拟灵机一动）
        "美食", "旅游", "音乐", "纪录片", "科技"
    ]

    # 运动相关关键词（用于首页识别）
    SPORTS_KEYWORDS = [
        "跑步", "马拉松", "排球", "乒乓球", "篮球", "足球",
        "羽毛球", "网球", "健身", "运动", "体能", "拉伸",
        "体育", "比赛", "锻炼", "训练"
    ]

    def __init__(self, context: DecisionContext = None):
        self.context = context or DecisionContext()
        self.min_action_interval = 8  # 最小动作间隔（秒）
        self.max_action_interval = 30  # 最大动作间隔（秒）

    def decide(self) -> Decision:
        """
        做出决策
        """
        now = datetime.now()

        # 检查动作间隔
        if self.context.last_action_time:
            elapsed = (now - self.context.last_action_time).total_seconds()
            if elapsed < self.min_action_interval:
                return Decision(
                    action=Action.IDLE,
                    reason=f"间隔太短，等待 {(self.min_action_interval - elapsed):.0f} 秒",
                    confidence=1.0
                )

        # 连续 idle 超过 3 次，强制执行浏览
        if self.context.consecutive_idles >= 3:
            return Decision(
                action=Action.RANDOM_BROWSE,
                reason="连续空闲太多，随机浏览",
                confidence=0.9
            )

        # 根据上次动作决定下一步
        if self.context.last_action == Action.POST_COMMENT:
            # 刚评论过，刷首页休息一下
            return self._decide_after_comment()

        elif self.context.last_action == Action.BROWSE_VIDEO:
            # 刚浏览过，考虑是否评论
            return self._decide_after_browse()

        elif self.context.last_action == Action.SCROLL_HOMEPAGE:
            # 刚刷完首页
            return self._decide_after_scroll()

        elif self.context.last_action == Action.IDLE:
            # 刚休息过
            return self._decide_after_idle()

        else:
            # 首次决策或 session 开始
            return self._decide_fresh()

    def _decide_after_comment(self) -> Decision:
        """评论后的决策"""
        # 评论后需要休息一段时间
        idle_chance = random.random()

        if idle_chance < 0.4:
            # 40% 概率休息
            return Decision(
                action=Action.IDLE,
                reason="评论后休息一下",
                confidence=0.8
            )
        elif idle_chance < 0.7:
            # 30% 概率刷首页
            return Decision(
                action=Action.SCROLL_HOMEPAGE,
                reason="刷首页看看其他内容",
                confidence=0.7
            )
        else:
            # 30% 概率继续浏览
            return self._pick_random_browse()

    def _decide_after_browse(self) -> Decision:
        """浏览视频后的决策"""
        # 决定是否评论刚看的视频
        comment_chance = random.random()

        # 刚浏览的视频
        last_bvid = self.context.recent_bvids[-1] if self.context.recent_bvids else None

        if last_bvid and last_bvid not in self.context.recent_comments:
            # 视频还没评论过
            if comment_chance < 0.6:  # 60% 概率评论
                return Decision(
                    action=Action.POST_COMMENT,
                    target=last_bvid,
                    reason="视频值得评论",
                    confidence=0.8
                )

        # 否则继续刷
        return self._decide_continue_scroll()

    def _decide_after_scroll(self) -> Decision:
        """刷首页后的决策"""
        return self._decide_continue_scroll()

    def _decide_after_idle(self) -> Decision:
        """休息后的决策"""
        self.context.consecutive_idles += 1

        if self.context.consecutive_idles >= 2:
            return Decision(
                action=Action.RANDOM_BROWSE,
                reason="休息够了，开始浏览",
                confidence=0.9
            )

        return Decision(
            action=Action.IDLE,
            reason="再休息一下",
            confidence=0.6
        )

    def _decide_fresh(self) -> Decision:
        """Session 开始的决策"""
        return Decision(
            action=Action.SCROLL_HOMEPAGE,
            reason="开始刷首页",
            confidence=1.0
        )

    def _decide_continue_scroll(self) -> Decision:
        """继续浏览/刷内容"""
        roll = random.random()

        if roll < 0.35:
            return Decision(
                action=Action.SEARCH,
                target=random.choice(self.INTEREST_KEYWORDS),
                reason="搜索感兴趣的内容",
                confidence=0.8
            )
        elif roll < 0.65:
            return Decision(
                action=Action.RANDOM_BROWSE,
                reason="随机浏览一个视频",
                confidence=0.7
            )
        else:
            return Decision(
                action=Action.SCROLL_HOMEPAGE,
                reason="继续刷首页",
                confidence=0.6
            )

    def _pick_random_browse(self) -> Decision:
        """随机选择一个视频浏览"""
        if self.context.recent_bvids:
            # 从最近浏览中选择一个没评论过的
            uncommented = [b for b in self.context.recent_bvids
                          if b not in self.context.recent_comments]
            if uncommented:
                return Decision(
                    action=Action.BROWSE_VIDEO,
                    target=random.choice(uncommented),
                    reason="再看一遍之前的视频",
                    confidence=0.7
                )

        return Decision(
            action=Action.RANDOM_BROWSE,
            reason="随机浏览",
            confidence=0.6
        )

    def update_context(self, action: Action, target: str = None):
        """更新上下文"""
        self.context.last_action = action
        self.context.last_action_time = datetime.now()

        if action == Action.POST_COMMENT and target:
            self.context.last_comment_time = datetime.now()
            self.context.recent_comments.append(target)

        if action == Action.BROWSE_VIDEO and target:
            self.context.recent_bvids.append(target)
            # 保持最近 20 条记录
            if len(self.context.recent_bvids) > 20:
                self.context.recent_bvids.pop(0)

        if action == Action.IDLE:
            self.context.consecutive_idles += 1
        else:
            self.context.consecutive_idles = 0

    def get_next_interval(self) -> int:
        """获取下一次动作的随机间隔"""
        return random.randint(self.min_action_interval, self.max_action_interval)

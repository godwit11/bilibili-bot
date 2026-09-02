"""
ai/loop.py - 自主 Bot 主循环
整合 DecisionEngine、BehaviorScheduler、MemoryManager
"""

import asyncio
import random
from datetime import datetime
from typing import Optional

from ai.decision import DecisionEngine, DecisionContext, Action, Decision
from ai.scheduler import BehaviorScheduler
from ai.memory import MemoryManager
from comment.api import BilibiliCommentAPI
from comment.browser import CommentPoster
from utils.logger import BotLogger


class AutonomousBot:
    """
    自主运行的 Bot
    模拟真人在 B站 浏览、评论
    """

    def __init__(
        self,
        video_browser,
        ai_generator,
        comment_api,
        db,
        session_manager=None
    ):
        self.video_browser = video_browser
        self.ai_generator = ai_generator
        self.comment_api = comment_api
        self.db = db
        self.session_manager = session_manager

        # 初始化各组件
        self.decision_engine = DecisionEngine()
        self.scheduler = BehaviorScheduler()
        self.memory = MemoryManager()

        self.running = False
        self.current_video = None

        # 评论降级发布器（API 失败时使用 DOM）
        self._comment_poster: Optional[CommentPoster] = None

        # 结构化日志器
        self._log = BotLogger("autonomous")

    async def start(self, duration_hours: Optional[float] = None):
        """
        启动 Bot

        Args:
            duration_hours: 运行时长（小时），None 表示持续运行
        """
        print("=" * 50)
        print("B站 AI Bot 自主模式启动！")
        print("=" * 50)
        print(f"运行模式: {'持续运行' if duration_hours is None else f'运行 {duration_hours} 小时'}")
        print(f"每日评论上限: {self.scheduler.get_max_comments_today()}（动态）")
        print(f"每次动作间隔: {self.scheduler.min_action_gap}-{self.scheduler.max_action_gap} 秒")
        print("=" * 50)
        self._log.info(f"Bot 启动 | 模式:{'持续' if duration_hours is None else f'{duration_hours}h'} | 日限:{self.scheduler.get_max_comments_today()}")

        self.running = True
        start_time = datetime.now()
        action_count = 0

        try:
            while self.running:
                # 检查运行时间
                if duration_hours:
                    elapsed = (datetime.now() - start_time).total_seconds() / 3600
                    if elapsed >= duration_hours:
                        print(f"\n[INFO] 已运行 {elapsed:.1f} 小时，停止")
                        self._log.info(f"运行时长到达，停止 Bot")
                        break

                # 等待上一个动作完成
                await self.scheduler.wait_if_needed()

                # 做出决策
                decision = self.decision_engine.decide()
                print(f"\n[决策] {decision.action.value} {decision.target or ''} | {decision.reason}")
                self._log.decision(decision.action.value, decision.target or '', decision.reason)

                # 执行决策
                success = await self._execute_decision(decision)

                # 更新记忆
                self.decision_engine.update_context(decision.action, decision.target)

                # 记录行为
                self.memory.add_session_action(
                    decision.action.value,
                    decision.target or "",
                    "成功" if success else "失败"
                )

                if success:
                    action_count += 1

                # 随机等待
                wait_time = self.decision_engine.get_next_interval()
                print(f"[等待] {wait_time:.0f} 秒后继续...")
                self._log.wait(wait_time)
                await asyncio.sleep(wait_time)

        except KeyboardInterrupt:
            print("\n[INFO] 收到停止信号")
            self._log.info("收到停止信号")
        finally:
            self.running = False
            # 本次运行的统计（不取持久化的累计数据）
            run_videos = sum(1 for v in self.memory.video_memory.values()
                           if v.browsed_at and start_time <= datetime.fromisoformat(v.browsed_at))
            run_commented = sum(1 for v in self.memory.video_memory.values()
                              if v.commented and v.browsed_at and start_time <= datetime.fromisoformat(v.browsed_at))
            print("\n" + "=" * 50)
            print("本次运行统计:")
            print(f"  总动作数: {action_count}")
            print(f"  浏览视频: {run_videos}")
            print(f"  评论数: {run_commented}")
            print("=" * 50)
            self._log.stats(
                total_actions=action_count,
                videos_browsed=run_videos,
                comments_posted=run_commented,
                duration_minutes=int((datetime.now() - start_time).total_seconds() / 60)
            )

    async def _execute_decision(self, decision: Decision) -> bool:
        """执行决策"""
        action = decision.action

        if action == Action.IDLE:
            await self.scheduler.wait_before_action("idle")
            return True

        elif action == Action.SCROLL_HOMEPAGE:
            return await self._do_scroll_homepage()

        elif action == Action.SEARCH:
            return await self._do_search(decision.target)

        elif action == Action.RANDOM_BROWSE:
            return await self._do_random_browse()

        elif action == Action.BROWSE_VIDEO:
            return await self._do_browse_video(decision.target)

        elif action == Action.POST_COMMENT:
            return await self._do_post_comment(decision.target)

        elif action == Action.WATCH_VIDEO:
            return await self._do_watch_video(decision.target)

        return False

    async def _do_scroll_homepage(self):
        """刷首页"""
        await self.scheduler.wait_before_action("scroll")

        scroll_count = random.randint(1, 3)
        print(f"  刷首页，滚动 {scroll_count} 次...")

        # 真正浏览首页获取视频列表
        videos = await self.video_browser.browse_homepage(scroll_count)

        if not videos:
            print(f"  首页没有找到视频")
            return True

        print(f"  首页发现 {len(videos)} 个视频")

        # 分离运动相关和非运动相关视频
        sports_videos = []
        other_videos = []
        for v in videos:
            title_lower = v.title.lower()
            up_lower = v.uploader_name.lower()
            combined = title_lower + up_lower
            is_sports = any(kw in combined for kw in self.decision_engine.SPORTS_KEYWORDS)
            if is_sports:
                sports_videos.append(v)
            else:
                other_videos.append(v)

        # 优先选择运动视频（70%概率），偶中选择其他的
        if sports_videos and random.random() < 0.7:
            chosen = random.choice(sports_videos)
            print(f"  选中运动视频: {chosen.title[:30]}...")
        elif other_videos:
            chosen = random.choice(other_videos)
            print(f"  灵机一动选了: {chosen.title[:30]}...")
        elif sports_videos:
            # 没有非运动视频，只好选运动的
            chosen = random.choice(sports_videos)
            print(f"  选中运动视频: {chosen.title[:30]}...")
        else:
            chosen = random.choice(videos)
            print(f"  随机选中: {chosen.title[:30]}...")

        # 浏览选中的视频
        return await self._do_browse_video(chosen.bvid)

    async def _do_search(self, keyword: str):
        """搜索"""
        if not keyword:
            return False

        await self.scheduler.wait_before_action("search")
        print(f"  搜索: {keyword}")

        # 搜索视频
        results = await self.video_browser.search_videos(keyword)

        if results:
            print(f"  找到 {len(results)} 个结果")
            # 随机选择一个浏览
            chosen = random.choice(results)
            await asyncio.sleep(1)
            await self._do_browse_video(chosen.bvid)
            return True

        return False

    async def _do_random_browse(self):
        """随机浏览"""
        # 从记忆中随机选择一个视频
        unreviewed = self.memory.get_recent_uncommented(5)

        if unreviewed:
            chosen = random.choice(unreviewed)
            print(f"  随机选择: {chosen.title[:30]}...")
            return await self._do_browse_video(chosen.bvid)

        # 没有未评论的，搜索新视频
        keyword = random.choice(self.decision_engine.INTEREST_KEYWORDS)
        print(f"  没有未评论视频，搜索: {keyword}")
        return await self._do_search(keyword)

    async def _do_browse_video(self, bvid: str):
        """浏览视频"""
        if not bvid:
            return False

        await self.scheduler.wait_before_action("browse")
        print(f"  浏览视频: {bvid}")

        # 获取视频完整信息（用于计算真实感观看时长和后续 AI 评论）
        video_info = await self.video_browser.get_video_info(bvid)
        if not video_info:
            print(f"  获取视频信息失败")
            return False

        # 根据视频时长计算真实感观看时间
        video_duration = getattr(video_info, 'duration', 0) or 0
        watch_seconds = self.scheduler.get_realistic_watch_duration(video_duration)
        print(f"  视频时长 {video_duration} 秒，计划观看 {watch_seconds:.0f} 秒")

        # 真正播放视频并发送心跳包（让 B站 记录观看历史）
        # 注意：play_video_and_watch 会覆盖 page，所以之后再获取 video_info
        await self.video_browser.play_video_and_watch(bvid, watch_seconds=watch_seconds)

        print(f"  标题: {video_info.title[:40]}...")
        print(f"  UP主: {video_info.uploader_name}")

        # 记录到记忆
        self.memory.remember_video(bvid, video_info.title, video_info.uploader_name)
        self.scheduler.record_browse()
        self.current_video = video_info

        # 观看完成后，立即决定是否评论（不在下一个 cycle 等决策）
        comment_chance = 0.55  # 55% 概率评论
        if not self.memory.has_commented(bvid) and random.random() < comment_chance:
            print(f"  观看完成，决定评论该视频")
            await self._do_post_comment(bvid)
        else:
            if self.memory.has_commented(bvid):
                print(f"  该视频已评论过，跳过")
            else:
                print(f"  这次不评论")

        return True

    async def _do_post_comment(self, bvid: str):
        """评论视频"""
        if not bvid:
            return False

        # 检查是否可以评论
        can_comment, reason = await self.scheduler.can_comment(bvid)
        if not can_comment:
            print(f"  无法评论: {reason}")
            return False

        # 统一使用 db 作为评论状态的权威数据源（同时保留 memory 缓存）
        if self.db and self.db.has_commented(bvid):
            print(f"  已评论过该视频（db记录）")
            return False
        if self.memory.has_commented(bvid):
            print(f"  已评论过该视频（memory缓存）")
            return False

        await self.scheduler.wait_before_action("comment")
        print(f"  生成评论...")

        # 获取视频信息
        if not self.current_video or self.current_video.bvid != bvid:
            video_info = await self.video_browser.get_video_info(bvid)
        else:
            video_info = self.current_video

        if not video_info:
            print(f"  获取视频信息失败")
            return False

        # AI 生成评论
        extra_info = {
            'stat': {
                'view': getattr(video_info, 'view_count', 0),
                'like': getattr(video_info, 'like_count', 0),
                'coin': getattr(video_info, 'coin_count', 0),
                'favorite': getattr(video_info, 'favorite_count', 0),
                'share': getattr(video_info, 'share_count', 0),
            },
            'tags': getattr(video_info, 'tags', []),
            'duration': getattr(video_info, 'duration', 0),
        }
        # 获取弹幕（最直接的视频内容反映）
        danmaku = await self.comment_api.get_danmaku(bvid, max_count=200)
        if danmaku:
            print(f"  获取到 {len(danmaku)} 条弹幕用于分析")
        comment = await self.ai_generator.generate_comment(
            video_title=video_info.title,
            video_description=video_info.description,
            extra_info=extra_info,
            danmaku=danmaku
        )

        # 去掉可能的 <think> 标签
        import re
        comment = re.sub(r'<[^>]+>', '', comment).strip()

        if not comment:
            print(f"  评论生成失败")
            return False

        print(f"  评论内容: {comment[:50]}...")

        # 发布评论（优先 API，失败后降级 DOM）
        success = await self._post_comment_with_fallback(bvid, comment)

        if success:
            # 记录
            self.memory.record_comment(bvid, comment)
            self.scheduler.record_comment()
            print(f"  评论成功！")
            return True
        else:
            print(f"  评论失败")
            return False

    async def _post_comment_with_fallback(self, bvid: str, content: str) -> bool:
        """
        评论发布（带降级机制）
        1. 优先使用 API 方式
        2. API 失败后尝试 DOM 方式
        """
        # 优先尝试 API
        try:
            success = await self.comment_api.post_comment(bvid, content)
            if success:
                print(f"  [API] 评论发布成功")
                return True
            print(f"  [API] 评论失败，尝试 DOM 降级...")
        except Exception as e:
            print(f"  [API] 评论异常: {e}，尝试 DOM 降级...")

        # DOM 降级
        if not self.session_manager:
            print(f"  [DOM] 无法降级：无可用 Session")
            return False

        try:
            # 懒加载 CommentPoster
            if self._comment_poster is None:
                self._comment_poster = CommentPoster(self.session_manager, self.db)

            print(f"  [DOM] 尝试通过浏览器发布评论...")
            success = await self._comment_poster.post_comment(bvid, content)
            if success:
                print(f"  [DOM] 评论发布成功")
                return True
            print(f"  [DOM] 评论也失败了")
            return False
        except Exception as e:
            print(f"  [DOM] 评论降级异常: {e}")
            return False

    async def _do_watch_video(self, bvid: str):
        """观看视频"""
        if not bvid:
            return False

        print(f"  观看视频: {bvid}")
        watch_time = self.scheduler.get_random_watch_duration()
        await asyncio.sleep(watch_time)
        return True

    def stop(self):
        """停止 Bot"""
        print("[INFO] 正在停止...")
        self.running = False

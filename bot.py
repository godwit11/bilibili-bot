#!/usr/bin/env python3
"""
bot.py - B站 AI Bot 主入口
支持 CLI 命令：浏览视频、搜索、AI 评论、登录等
"""

import asyncio
import argparse
import datetime
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from session.manager import SessionManager, SessionExpiredError
from storage.db import Database, VideoRecord
from video.browser import VideoBrowser
from ai.generator import AIGenerator
from comment.browser import CommentPoster
from comment.api import BilibiliCommentAPI
from ai.loop import AutonomousBot


class BilibiliBot:
    """
    B站 AI Bot 主类
    编排各组件，提供统一入口
    """

    def __init__(self):
        self.session: SessionManager = None
        self.db: Database = None
        self.video_browser: VideoBrowser = None
        self.ai_generator: AIGenerator = None
        self.comment_poster: CommentPoster = None
        self._initialized = False

    async def initialize(self):
        """初始化所有组件"""
        print("=" * 50)
        print("B站 AI Bot 启动中...")
        print("=" * 50)

        # 初始化 SessionManager（先于数据库）
        self.session = SessionManager()
        session_info = await self.session.initialize()

        if not session_info.is_login:
            print("[WARN] 未登录或登录已过期")
            print("[INFO] 请运行: python bot.py login")
            return False

        # 等待一下让浏览器稳定
        await asyncio.sleep(3)

        # 初始化数据库（在 session 之后）
        self.db = Database(config.videos_db_path)

        # 初始化各组件
        self.video_browser = VideoBrowser(self.session)
        self.ai_generator = AIGenerator()
        self.comment_poster = CommentPoster(self.session, self.db)

        self._initialized = True
        print("[OK] Bot 初始化完成")
        print("-" * 50)
        return True

    async def close(self):
        """关闭 Bot"""
        if self.session:
            await self.session.close()
        if self.db:
            self.db.close()
        print("[INFO] Bot 已关闭")

    # ============ CLI 命令实现 ============

    async def cmd_browse(self, bvid: str):
        """浏览视频，获取信息和评论"""
        print(f"[INFO] 正在浏览视频: {bvid}")

        # 获取视频信息
        video_info = await self.video_browser.get_video_info(bvid)
        if not video_info:
            print("[ERROR] 获取视频信息失败")
            return

        print("\n" + "=" * 50)
        print(f"标题: {video_info.title}")
        print(f"UP主: {video_info.uploader_name}")
        print(f"播放: {video_info.view_count:,}")
        print(f"点赞: {video_info.like_count:,}")
        print(f"投币: {video_info.coin_count:,}")
        print(f"收藏: {video_info.favorite_count:,}")
        print(f"分享: {video_info.share_count:,}")
        print(f"链接: {video_info.url}")
        print("=" * 50)

        # 存储浏览记录
        self.db.store_video(VideoRecord(
            bvid=video_info.bvid,
            title=video_info.title,
            uploader_name=video_info.uploader_name,
            view_count=video_info.view_count,
            like_count=video_info.like_count,
            publish_time=str(video_info.publish_time) if video_info.publish_time else None,
            browsed_at=datetime.datetime.now().isoformat()
        ))

        # 获取评论
        print("\n[INFO] 正在加载评论...")
        comments = await self.video_browser.get_comments(bvid, max_pages=2)

        if comments:
            print(f"\n评论列表 (共 {len(comments)} 条):")
            print("-" * 50)
            for i, c in enumerate(comments[:10], 1):
                print(f"{i}. [{c.member_uname}] {c.content[:50]}...")
                print(f"   点赞: {c.like_count}")
        else:
            print("[INFO] 暂无评论")

    async def cmd_search(self, keyword: str, page: int = 1):
        """搜索视频"""
        print(f"[INFO] 搜索关键词: {keyword}")

        results = await self.video_browser.search_videos(keyword, page)

        if not results:
            print("[INFO] 未找到结果")
            return

        print(f"\n搜索结果 (共 {len(results)} 条):")
        print("-" * 50)
        for i, v in enumerate(results, 1):
            print(f"{i}. {v.title}")
            print(f"   UP: {v.uploader_name} | 播放: {v.view_count:,} | 时长: {v.duration}")
            print(f"   {v.url}")
            print()

    async def cmd_comments(self, bvid: str, max_pages: int = 3):
        """获取视频评论"""
        print(f"[INFO] 正在加载评论: {bvid}")

        comments = await self.video_browser.get_comments(bvid, max_pages)

        if not comments:
            print("[INFO] 暂无评论")
            return

        print(f"\n评论列表 (共 {len(comments)} 条):")
        print("-" * 50)
        for i, c in enumerate(comments, 1):
            print(f"{i}. [{c.member_uname}] {c.content}")
            print(f"   点赞: {c.like_count} | 回复: {c.reply_count}")
            print()

    async def cmd_generate_comment(self, bvid: str, hint: str = None):
        """AI 生成评论（预览）"""
        print(f"[INFO] 正在生成评论: {bvid}")

        # 获取视频信息
        video_info = await self.video_browser.get_video_info(bvid)
        if not video_info:
            print("[ERROR] 获取视频信息失败")
            return

        # 获取弹幕（最直接的视频内容反映）
        comment_api = BilibiliCommentAPI()
        danmaku = await comment_api.get_danmaku(bvid, max_count=200)
        if danmaku:
            print(f"[INFO] 获取到 {len(danmaku)} 条弹幕用于分析视频内容")

        # 获取热门评论作为参考
        comments = await self.video_browser.get_comments(bvid, max_pages=1)
        top_comments = [c.content for c in comments[:3]] if comments else []

        # 生成评论
        extra_info = {
            'stat': {
                'view': video_info.view_count,
                'like': video_info.like_count,
                'coin': video_info.coin_count,
                'favorite': video_info.favorite_count,
                'share': video_info.share_count,
            },
            'tags': video_info.tags,
            'tname': getattr(video_info, 'tname', ''),
            'duration': video_info.duration,
        }
        comment = await self.ai_generator.generate_comment(
            video_title=video_info.title,
            video_description=video_info.description,
            top_comments=top_comments,
            user_hint=hint,
            extra_info=extra_info,
            danmaku=danmaku
        )

        print("\n" + "=" * 50)
        print("AI 生成的评论:")
        print(f"  {comment}")
        print("=" * 50)
        print("\n如需发布，请使用: python bot.py comment <bvid> --ai")

        return comment

    async def cmd_comment(self, bvid: str, text: str = None, ai: bool = False, hint: str = None):
        """发布评论"""
        # 确定评论内容
        if ai or (not text):
            # AI 生成
            print(f"[INFO] 正在生成评论...")
            comment_text = await self.cmd_generate_comment(bvid, hint)
            if not comment_text:
                print("[ERROR] 评论生成失败")
                return
        else:
            comment_text = text

        print(f"\n[INFO] 正在发布评论...")

        # 使用 API 方式发布评论（更稳定）
        comment_api = BilibiliCommentAPI()
        success = await comment_api.post_comment(bvid, comment_text)

        if success:
            # 保存到数据库
            self.db.store_comment(bvid, comment_text, 'success')
            print("[INFO] 评论已记录到数据库")
            print("[OK] 评论发布成功！")
        else:
            print("[ERROR] 评论发布失败，请查看上方日志")

    async def cmd_login(self):
        """交互式登录"""
        print("[INFO] 启动交互式登录...")
        # 初始化 session（只初始化 session，不初始化其他组件）
        self.session = SessionManager()
        success = await self.session.login_interactive()

        if success:
            print("[OK] 登录成功！")
        else:
            print("[ERROR] 登录失败")

    async def cmd_history(self, limit: int = 10):
        """浏览历史"""
        videos = self.db.get_recent_videos(limit)

        if not videos:
            print("[INFO] 暂无浏览历史")
            return

        print(f"\n最近浏览 (共 {len(videos)} 条):")
        print("-" * 50)
        for i, v in enumerate(videos, 1):
            print(f"{i}. {v.title}")
            print(f"   UP: {v.uploader_name} | 播放: {v.view_count:,} | 浏览时间: {v.browsed_at}")
            print()

    async def cmd_comment_history(self, limit: int = 50):
        """评论历史"""
        comments = self.db.get_recent_comments(limit)

        if not comments:
            print("[INFO] 暂无评论记录")
            return

        print(f"\n评论历史 (共 {len(comments)} 条):")
        print("-" * 50)
        for i, c in enumerate(comments, 1):
            status_icon = "✅" if c.status == "success" else "❌" if c.status == "failed" else "⏳"
            print(f"{i}. [{status_icon}] {c.content[:50]}{'...' if len(c.content) > 50 else ''}")
            print(f"   视频: {c.bvid} | 时间: {c.posted_at}")
            print()

    async def cmd_im(self, interval: int = 60):
        """
        持续监听并回复私信/回复

        Args:
            interval: 检查间隔（秒），默认 60 秒
        """
        from im.handler import IMHandler
        import signal

        handler = IMHandler(self.db, self.session)
        await handler.initialize()

        running = True
        total_replied = 0

        def signal_handler(sig, frame):
            nonlocal running
            print("\n[INFO] 收到停止信号，正在停止...")
            running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        print(f"[INFO] 开始持续监听私信（间隔 {interval} 秒）")
        print("[INFO] 按 Ctrl+C 停止")
        print("-" * 50)

        while running:
            try:
                count = await handler.process_unread_messages()
                total_replied += count
                if count > 0:
                    print(f"[INFO] 本次回复 {count} 条，累计 {total_replied} 条")
                else:
                    print(f"[DEBUG] 检查完毕，暂无新消息 ({total_replied} 条已回复)")

                # 等待下次检查
                for i in range(interval):
                    if not running:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"[ERROR] 处理消息时出错: {e}")
                await asyncio.sleep(10)

        print(f"[INFO] 监听结束，共回复 {total_replied} 条消息")


# ============ CLI 入口 ============

def main():
    parser = argparse.ArgumentParser(description='B站 AI Bot')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # browse 命令
    browse_parser = subparsers.add_parser('browse', help='浏览视频')
    browse_parser.add_argument('bvid', help='视频 BV 号')

    # search 命令
    search_parser = subparsers.add_parser('search', help='搜索视频')
    search_parser.add_argument('keyword', help='搜索关键词')
    search_parser.add_argument('--page', '-p', type=int, default=1, help='页码')

    # comments 命令
    comments_parser = subparsers.add_parser('comments', help='获取评论')
    comments_parser.add_argument('bvid', help='视频 BV 号')
    comments_parser.add_argument('--max-pages', '-m', type=int, default=3, help='最大页数')

    # generate-comment 命令
    gen_parser = subparsers.add_parser('generate-comment', help='AI 生成评论（预览）')
    gen_parser.add_argument('bvid', help='视频 BV 号')
    gen_parser.add_argument('--hint', '-H', help='生成提示')

    # comment 命令
    comment_parser = subparsers.add_parser('comment', help='发布评论')
    comment_parser.add_argument('bvid', help='视频 BV 号')
    comment_parser.add_argument('--text', '-t', help='直接指定评论内容')
    comment_parser.add_argument('--ai', '-a', action='store_true', help='使用 AI 生成评论')
    comment_parser.add_argument('--hint', '-H', help='AI 生成提示')

    # login 命令
    subparsers.add_parser('login', help='交互式登录')

    # history 命令
    history_parser = subparsers.add_parser('history', help='浏览历史')
    history_parser.add_argument('--limit', '-l', type=int, default=10, help='显示数量')

    # comment-history 命令
    comment_history_parser = subparsers.add_parser('comment-history', help='评论历史')
    comment_history_parser.add_argument('--limit', '-l', type=int, default=50, help='显示数量')

    # run 命令
    run_parser = subparsers.add_parser('run', help='启动自主 Bot')
    run_parser.add_argument('--hours', '-t', type=float, help='运行时长（小时），不指定则持续运行')

    # im 命令
    im_parser = subparsers.add_parser('im', help='持续监听并回复私信和评论回复')
    im_parser.add_argument('--interval', '-i', type=int, default=60, help='检查间隔（秒），默认 60')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 初始化结构化日志
    from utils.logger import setup_logger
    log = setup_logger()
    log.info(f"=== B站 Bot 启动 | 命令: {args.command} ===")

    # 创建并运行 Bot
    bot = BilibiliBot()

    async def run():
        try:
            if args.command == 'login':
                await bot.cmd_login()
                return

            # 其他命令需要先初始化
            if not await bot.initialize():
                return

            # 执行命令
            if args.command == 'browse':
                await bot.cmd_browse(args.bvid)
            elif args.command == 'search':
                await bot.cmd_search(args.keyword, args.page)
            elif args.command == 'comments':
                await bot.cmd_comments(args.bvid, args.max_pages)
            elif args.command == 'generate-comment':
                await bot.cmd_generate_comment(args.bvid, args.hint)
            elif args.command == 'comment':
                await bot.cmd_comment(args.bvid, args.text, args.ai, args.hint)
            elif args.command == 'history':
                await bot.cmd_history(args.limit)
            elif args.command == 'comment-history':
                await bot.cmd_comment_history(args.limit)
            elif args.command == 'run':
                # 启动自主 Bot
                auto_bot = AutonomousBot(
                    video_browser=bot.video_browser,
                    ai_generator=bot.ai_generator,
                    comment_api=BilibiliCommentAPI(),
                    db=bot.db,
                    session_manager=bot.session
                )
                # 让 MemoryManager 也写 SQLite（同步到 cmd_comment_history）
                auto_bot.memory.set_database(bot.db)
                await auto_bot.start(duration_hours=args.hours)
            elif args.command == 'im':
                await bot.cmd_im(args.interval)

        finally:
            await bot.close()

    # 运行
    asyncio.run(run())


if __name__ == '__main__':
    main()

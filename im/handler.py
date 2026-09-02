"""
im/handler.py - 私信/回复处理器
"""

import asyncio
import hashlib
from datetime import datetime
from typing import Optional

from storage.db import Database
from im.browser import IMBrowser
from im.reply_generator import IMReplyGenerator
from im.api import BilibiliIMAPI
from session.manager import SessionManager
from config import config
from utils.time_parser import parse_bilibili_time


class IMHandler:
    """
    处理私信和评论回复
    """

    def __init__(self, db: Database, session: SessionManager):
        self.db = db
        self.session = session
        self.generator = IMReplyGenerator()
        self.im_api = BilibiliIMAPI()  # HTTP API（优先使用）
        self._page = None
        self._self_mid: Optional[str] = None
        self._start_time = datetime.now()  # 记录启动时间，用于过滤历史消息

    async def initialize(self):
        """初始化，获取自己的 mid"""
        self._page = await self.session.get_page()

        await self._page.goto(
            'https://api.bilibili.com/x/web-interface/nav',
            timeout=config.browser_timeout
        )
        await self._page.wait_for_load_state('networkidle')

        try:
            nav_data = await self._page.evaluate('JSON.parse(document.body.innerText)')
            self._self_mid = str(nav_data.get('data', {}).get('mid', '')) if nav_data.get('data') else None
        except:
            self._self_mid = None

        if self._self_mid:
            print(f"[INFO] 己方 mid: {self._self_mid}")

    async def process_unread_messages(self) -> int:
        """处理所有未读消息"""
        if not self._page:
            await self.initialize()

        browser = IMBrowser(self._page)
        processed = 0

        # 1. 处理私信
        print("[DEBUG] 检查私信...")
        if await browser.goto_inbox("whisper"):
            sessions = await browser.get_unread_sessions()
            unread_sessions = [s for s in sessions if s.get('unread', 0) > 0]

            if unread_sessions:
                print(f"[INFO] 发现 {len(unread_sessions)} 个未读私信会话")
                for session in unread_sessions:
                    name = session.get('name', '')
                    if await browser.open_whisper_session(name):
                        await asyncio.sleep(config.im_whisper_load_wait)
                        messages = await browser.get_whisper_messages()
                        count = await self._process_whisper_messages(messages, name, browser)
                        processed += count
            else:
                print("[DEBUG] 私信暂无未读")

        # 2. 处理回复通知
        print("[DEBUG] 检查回复通知...")
        notifications = await browser.get_reply_notifications()
        if notifications:
            print(f"[INFO] 发现 {len(notifications)} 条回复通知")
            for notif in notifications:
                user = notif.get('user', '未知用户')
                content = notif.get('content', '')
                action = notif.get('action', '')

                # 时间过滤：只处理启动后的新通知
                notif_time_str = notif.get('time', '')
                skip_reason = None
                if notif_time_str:
                    notif_time = parse_bilibili_time(notif_time_str)
                    if notif_time and notif_time < self._start_time:
                        skip_reason = f"时间早于启动 ({notif_time_str})"
                    elif notif_time is None:
                        skip_reason = f"时间解析失败 ({notif_time_str})"
                if skip_reason:
                    # 旧通知也写入 DB，避免每轮重复检查
                    user_reply = notif.get('user_reply', '')
                    dedup_key_content = user_reply if user_reply else content[:20]
                    notif_key = f"{user}_{action}_{dedup_key_content}"
                    self.db.mark_notification_processed(notif_key)
                    continue

                # 使用 user_reply 作为去重 key（而不是被回复的 content）
                user_reply = notif.get('user_reply', '')
                dedup_key_content = user_reply if user_reply else content[:20]
                notif_key = f"{user}_{action}_{dedup_key_content}"

                if self.db.is_notification_processed(notif_key):
                    print(f"[DEBUG] DB去重跳过: {notif_key[:40]}...")
                    continue

                print(f"[INFO] 处理: {user} | 新回复: {user_reply[:20] if user_reply else '无'}")

                # 重新获取当前通知列表（避免页面结构变化导致索引错位）
                # 用 user_reply + action + user 匹配（不用 content，因为 content 在多次交互中会变）
                current_notifs = await browser.get_reply_notifications()
                notif_idx = None
                for idx, n in enumerate(current_notifs):
                    if (n.get('user') == user
                            and n.get('action') == action
                            and n.get('user_reply') == user_reply):
                        notif_idx = idx
                        break

                if notif_idx is None:
                    print(f"[DEBUG] 该通知已从页面消失，跳过")
                    continue

                # 生成回复内容（AI）
                # 优先使用用户实际写的回复内容（user_reply），fallback 到被回复内容
                reply_content = notif.get('user_reply') or content

                # 获取该用户的历史评论回复（最多20条）作为上下文
                raw_history = self.db.get_comment_history(user, limit=config.im_comment_context_limit)
                # 转换为 generate_reply 期望的 {sender, content} 格式
                # sender='other' = 用户发的，sender='self' = bot发的
                comment_history = []
                for row in raw_history:
                    comment_history.append({'sender': 'other', 'content': row.get('user_reply', '')})
                    comment_history.append({'sender': 'self', 'content': row.get('bot_reply', '')})

                reply = await self.generator.generate_reply(
                    user_message=reply_content,
                    conversation_history=comment_history,
                    user_name=user
                )

                # 点对应索引的回复按钮并发送
                sent = False
                if await browser.click_reply_button(notif_idx):
                    await asyncio.sleep(config.im_comment_click_wait)
                    # 发回复（最多重试 2 次）
                    for retry in range(2):
                        if await browser.send_reply_message(reply):
                            sent = True
                            break
                        print(f"[DEBUG] 发送失败，尝试重试 ({retry + 1}/2)...")
                        await asyncio.sleep(config.im_comment_send_retry_wait)
                        # 重试前重新点击回复按钮
                        if not await browser.click_reply_button(notif_idx):
                            break

                if sent:
                    processed += 1
                    # 标记已处理
                    self.db.mark_notification_processed(notif_key)
                    # 写入评论回复历史
                    self.db.store_comment_reply(user, content, reply_content, reply)
                    print(f"[OK] 回复 {user}: {reply[:30]}...")
                else:
                    print(f"[WARN] 发送失败，下轮重试（不标记）")
                await asyncio.sleep(config.im_comment_process_interval)
        else:
            print("[DEBUG] 回复通知暂无")

        print(f"[INFO] 本次处理了 {processed} 条消息")
        return processed

    async def _process_whisper_messages(self, messages: list[dict], session_name: str, browser: IMBrowser) -> int:
        """处理一个私信会话中的消息"""
        if not messages:
            print(f"[DEBUG] 会话 {session_name} 无消息内容")
            return 0

        # 过滤出对方的未回复消息，只取最近 2 条
        # 避免把历史消息（甚至 bot 自己发的）当新消息处理
        unreplied = []
        for msg in reversed(messages):  # 从最新往旧遍历
            if msg.get('sender') == 'other' and msg.get('content'):
                content = msg.get('content', '')

                # 1. 过滤启动前的历史消息（如果能获取到时间）
                msg_time_str = msg.get('time', '')
                if msg_time_str:
                    msg_time = parse_bilibili_time(msg_time_str)
                    if msg_time and msg_time < self._start_time:
                        continue  # 跳过启动前的历史消息

                # 2. 过滤掉可能是 bot 自己的消息（关键词匹配）
                bot_keywords = ['喵', '喵呜', '喵~', '(≧', 'w/', '主人', '抱歉', '下次', '诶嘿', '嘿嘿']
                if any(kw in content for kw in bot_keywords):
                    continue

                # 3. 检查 DB 中是否已回复过这条消息
                existing = self.db.get_conversation(session_name, limit=config.im_whisper_dedup_check_limit)
                if not any(m.get('content') == msg['content'] and m.get('replied') for m in existing):
                    unreplied.append(msg)
            if len(unreplied) >= config.im_whisper_max_per_session:
                break

        if not unreplied:
            print(f"[DEBUG] 会话 {session_name} 无新增未回复消息")
            return 0

        print(f"[INFO] 会话 {session_name} 有 {len(unreplied)} 条未回复（最多处理 {config.im_whisper_max_per_session} 条）")
        processed = 0

        for msg in unreplied:
            content = msg.get('content', '')
            print(f"[DEBUG] 未回复: {content[:40]}...")

            history = self.db.get_conversation(session_name, limit=config.im_whisper_context_limit)
            reply = await self.generator.generate_reply(
                user_message=content,
                conversation_history=history,
                user_name=session_name
            )

            if await browser.send_whisper_message(reply):
                msg_id = self.db.store_message(session_name, session_name, content, session_name)
                self.db.mark_message_replied(msg_id, reply)
                print(f"[OK] 回复 {session_name}: {reply}")
                processed += 1
            else:
                print(f"[ERROR] 回复失败")

            await asyncio.sleep(config.im_whisper_send_interval)

        return processed

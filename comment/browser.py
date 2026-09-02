"""
comment/browser.py - 评论发布功能
通过 Playwright 在 B站视频页发布评论
"""

import asyncio
import re
import time
from typing import Optional

from playwright.async_api import Page

from config import config
from session.manager import SessionManager
from storage.db import Database


class CommentPoster:
    """
    评论发布器
    支持评论发布、回复、频率限制
    """

    def __init__(self, session: SessionManager, db: Database):
        self.session = session
        self.db = db
        self._last_comment_time: dict[str, float] = {}  # bvid -> timestamp

    def _check_cooldown(self, bvid: str) -> bool:
        """
        检查评论冷却时间
        同一视频需要间隔 comment_cooldown 秒才能再次评论
        """
        if bvid not in self._last_comment_time:
            return True

        elapsed = time.time() - self._last_comment_time[bvid]
        if elapsed < config.comment_cooldown:
            remaining = int(config.comment_cooldown - elapsed)
            print(f"[WARN] 评论冷却中，还需等待 {remaining} 秒")
            return False
        return True

    def _update_cooldown(self, bvid: str):
        """更新评论时间戳"""
        self._last_comment_time[bvid] = time.time()

    async def post_comment(self, bvid: str, content: str, retry_count: int = 0) -> bool:
        """
        发布评论

        Args:
            bvid: 视频 BV 号
            content: 评论内容
            retry_count: 当前重试次数

        Returns:
            是否发布成功
        """
        # 检查冷却
        if not self._check_cooldown(bvid):
            return False

        # 检查是否已评论
        if self.db.has_commented(bvid):
            print(f"[WARN] 已评论过该视频: {bvid}")
            return False

        # 存储为 pending 状态
        comment_id = self.db.store_comment(bvid, content, 'pending')

        page = await self.session.get_page()
        try:
            url = f"https://www.bilibili.com/video/{bvid}"
            await page.goto(url, timeout=config.video_page_load_timeout)
            await page.wait_for_load_state('domcontentloaded')

            # 等待页面加载
            await asyncio.sleep(3)

            # 尝试多种方式找到评论框
            comment_box = None
            selectors = [
                'textarea[name="content"]',
                '.comment-box textarea',
                '.reply-box textarea',
                '#comment_content',
                'textarea[placeholder*="评论"]',
                '[contenteditable="true"]'
            ]

            for selector in selectors:
                try:
                    comment_box = await page.wait_for_selector(selector, timeout=3000)
                    if comment_box:
                        print(f"[INFO] 找到评论框: {selector}")
                        break
                except:
                    continue

            if not comment_box:
                # 通过 JavaScript 查找评论相关的 textarea
                comment_box = await page.evaluate('''
                    () => {
                        const textareas = document.querySelectorAll('textarea');
                        for (const ta of textareas) {
                            if (ta.offsetParent !== null && ta.clientHeight > 20) {
                                return ta;
                            }
                        }
                        return null;
                    }
                ''')
                if comment_box:
                    print("[INFO] 通过 JS 找到评论框")

            if not comment_box:
                print("[ERROR] 未找到评论框")
                self.db.update_comment_status(comment_id, 'failed')
                return False

            # 点击并输入评论
            await comment_box.click()
            await asyncio.sleep(0.3)
            await comment_box.fill(content)
            await asyncio.sleep(0.3)

            # 尝试多种方式找到发布按钮
            submit_btn = None
            submit_selectors = [
                '.comment-submit',
                '.post-comment',
                '.bilibili-btn-primary',
                'button:has-text("发布")',
                'button:has-text("评论")'
            ]

            for selector in submit_selectors:
                try:
                    submit_btn = await page.wait_for_selector(selector, timeout=2000)
                    if submit_btn:
                        print(f"[INFO] 找到发布按钮: {selector}")
                        break
                except:
                    continue

            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)

                # 检查是否发布成功（页面可能有提示）
                # B站通常会在评论框附近显示新评论

                # 更新状态
                self.db.update_comment_status(comment_id, 'success')
                self._update_cooldown(bvid)

                print(f"[OK] 评论发布成功: {content[:30]}...")
                return True
            else:
                print("[ERROR] 未找到发布按钮")
                self.db.update_comment_status(comment_id, 'failed')
                return False

        except Exception as e:
            print(f"[ERROR] 评论发布失败: {e}")

            # 重试逻辑
            if retry_count < config.comment_max_retries:
                print(f"[INFO] 尝试重试 ({retry_count + 1}/{config.comment_max_retries})...")
                await asyncio.sleep(2)
                return await self.post_comment(bvid, content, retry_count + 1)

            self.db.update_comment_status(comment_id, 'failed')
            return False

        finally:
            await page.close()

    async def reply_to_comment(
        self,
        bvid: str,
        parent_rpid: int,
        content: str
    ) -> bool:
        """
        回复评论

        Args:
            bvid: 视频 BV 号
            parent_rpid: 被回复的评论 ID
            content: 回复内容

        Returns:
            是否发布成功
        """
        page = await self.session.get_page()
        try:
            url = f"https://www.bilibili.com/video/{bvid}"
            await page.goto(url, timeout=config.video_page_load_timeout)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(1)

            # 查找并点击回复按钮
            reply_btn_selector = f'.comment-item[data-rpid="{parent_rpid}"] .reply-btn, [data-rpid="{parent_rpid}"] .reply'
            reply_btn = await page.query_selector(reply_btn_selector)

            if reply_btn:
                await reply_btn.click()
                await asyncio.sleep(0.5)

                # 输入回复内容
                reply_input_selector = '.reply-input, textarea[name="content"]'
                reply_input = await page.wait_for_selector(reply_input_selector, timeout=3000)
                if reply_input:
                    await reply_input.fill(content)

                    # 提交
                    submit_btn = await page.query_selector('.reply-submit, button[type="submit"]')
                    if submit_btn:
                        await submit_btn.click()
                        await asyncio.sleep(1)
                        print(f"[OK] 回复发布成功: {content[:30]}...")
                        return True

            print("[WARN] 未找到回复按钮或输入框")
            return False

        except Exception as e:
            print(f"[ERROR] 回复发布失败: {e}")
            return False

        finally:
            await page.close()

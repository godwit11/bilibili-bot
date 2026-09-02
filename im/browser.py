"""
im/browser.py - 私信浏览器自动化
通过 Playwright 控制 B站网页版私信页面
"""

import asyncio
import re
from typing import Optional

from playwright.async_api import Page

from config import config


class IMBrowser:
    """
    通过浏览器自动化处理私信
    通过 URL hash 切换不同 tab
    """

    def __init__(self, page: Page):
        self.page = page

    async def goto_inbox(self, tab: str = "whisper") -> bool:
        """
        跳转到消息页面
        """
        try:
            await self.page.goto(
                f"https://message.bilibili.com/#/{tab}",
                timeout=config.browser_timeout,
                wait_until='domcontentloaded'
            )
            await asyncio.sleep(config.im_page_goto_wait)
            return True
        except Exception as e:
            print(f"[ERROR] 访问消息页面失败: {e}")
            return False

    async def get_unread_sessions(self) -> list[dict]:
        """
        获取私信未读会话列表
        """
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(2)

        sessions = await self.page.evaluate("""
            () => {
                const result = [];
                const listItems = document.querySelectorAll('.message-inner-list__item');
                listItems.forEach(item => {
                    const nameEl = item.querySelector('[class*="session-name"], [class*="name"], .session-item__name');
                    const numEl = item.querySelector('.message-inner-list__item--num');
                    const msgEl = item.querySelector('[class*="msg"], [class*="message"], [class*="content"]');

                    const name = nameEl ? nameEl.innerText.trim() : '';
                    if (!name) return;

                    const unreadText = numEl ? numEl.innerText.trim() : '0';
                    const unread = parseInt(unreadText) || 0;
                    const lastMsg = msgEl ? msgEl.innerText.trim().substring(0, 100) : '';

                    result.push({ name, unread, last_msg: lastMsg });
                });

                if (result.length === 0) {
                    const allItems = document.querySelectorAll('[class*="SessionItem"]');
                    allItems.forEach(item => {
                        const nameEl = item.querySelector('[class*="Name"]');
                        const numEl = item.querySelector('[class*="NotificationNumber"], [class*="num"]');

                        const name = nameEl ? nameEl.innerText.trim() : '';
                        if (!name) return;

                        const unreadText = numEl ? numEl.innerText.trim() : '0';
                        const unread = parseInt(unreadText) || 0;

                        result.push({ name, unread, last_msg: '' });
                    });
                }

                return result;
            }
        """)

        print(f"[DEBUG] 发现 {len(sessions)} 个会话项")
        for s in sessions[:3]:
            print(f"       - {s.get('name', '')} (unread={s.get('unread', 0)})")

        return sessions

    async def open_whisper_session(self, name: str) -> bool:
        """
        打开私信会话（点击会话名进入聊天视图）
        URL 会变成 /whisper/midxxx
        """
        try:
            await asyncio.sleep(1)

            escaped_name = name.replace("'", "\\'")
            result = await self.page.evaluate(f"""
                () => {{
                    try {{
                        const selectors = [
                            '.message-inner-list__item',
                            '[class*="SessionItem"]',
                            '[class*="session-item"]'
                        ];
                        let targetItem = null;

                        for (const sel of selectors) {{
                            const items = document.querySelectorAll(sel);
                            for (const item of items) {{
                                const text = (item.innerText || '').trim();
                                if (text && text.split(/\\n/)[0].trim() === '{escaped_name}') {{
                                    targetItem = item;
                                    break;
                                }}
                            }}
                            if (targetItem) break;
                        }}

                        if (!targetItem) return 'not_found';

                        const nameEl = targetItem.querySelector(
                            '[class*="session-name"], ' +
                            '[class*="name"][class*="session"], ' +
                            '.session-item__name'
                        );
                        if (nameEl) {{
                            nameEl.click();
                        }} else {{
                            targetItem.click();
                        }}
                        return 'ok';
                    }} catch(e) {{
                        return 'error:' + e.message;
                    }}
                }}
            """)

            if result != 'ok':
                print(f"[ERROR] 未找到会话: {name} (result={result!r})")
                return False

            await asyncio.sleep(2)
            print(f"[DEBUG] 打开私信会话: {name}, URL: {self.page.url}")
            return True
        except Exception as e:
            print(f"[ERROR] 打开私信会话失败: {e}")
            return False

    async def get_whisper_messages(self) -> list[dict]:
        """
        获取当前私信会话的消息列表
        chat view 使用 _Msg__Main 类显示消息文本
        """
        messages = await self.page.evaluate("""
            () => {
                const result = [];
                const items = document.querySelectorAll('[class*="_Msg__Main"]');

                items.forEach(item => {
                    const text = item.innerText.trim();
                    if (!text || text.length > 300) return;

                    const uiTexts = ['请输入消息内容', '发送', '消息中心', '我的消息', '回复我的', '@ 我的', '收到的赞', '系统通知', '消息设置', '应援团助手', '最近消息'];
                    if (uiTexts.some(ui => text.includes(ui))) return;

                    const parent = item.parentElement;
                    const cls = parent ? parent.className : '';
                    const isSelf = cls.includes('self') || cls.includes('mine') || cls.includes('My');

                    let time = '';
                    const timeEl = item.closest('.message-item, .chat-item, [class*="msg"]')?.querySelector('.time, [class*="time"]');
                    if (timeEl) {
                        time = timeEl.innerText.trim();
                    }

                    result.push({
                        content: text,
                        sender: isSelf ? 'self' : 'other',
                        sender_name: '',
                        time: time
                    });
                });

                return result;
            }
        """)
        return messages

    async def send_whisper_message(self, text: str) -> bool:
        """在私信聊天视图发送消息（使用 contenteditable 输入框）"""
        try:
            input_area = self.page.locator('[contenteditable="true"]').first
            if await input_area.count() > 0:
                visible = await input_area.is_visible(timeout=3000)
                if visible:
                    await input_area.click()
                    await asyncio.sleep(0.3)

                    await input_area.click(click_count=3)
                    await asyncio.sleep(0.2)

                    await input_area.press_sequentially(text)
                    await asyncio.sleep(0.3)

                    before_send = await input_area.inner_text()
                    if text not in before_send:
                        print(f"[ERROR] 内容未填入 whisper")
                        return False

                    await self.page.keyboard.press('Enter')
                    await asyncio.sleep(1.5)

                    val_after = await self.page.evaluate(
                        "document.querySelector('[contenteditable=\"true\"]')?.innerText || ''"
                    )
                    if val_after == '':
                        print(f"[DEBUG] 私信发送成功: {text[:30]}...")
                        return True
                    else:
                        await asyncio.sleep(2)
                        val_after2 = await self.page.evaluate(
                            "document.querySelector('[contenteditable=\"true\"]')?.innerText || ''"
                        )
                        if val_after2 == '':
                            print(f"[DEBUG] 私信发送成功: {text[:30]}...")
                            return True
                        print(f"[ERROR] 私信发送失败（内容未清空）")
                        return False

            print("[ERROR] 未找到 contenteditable 输入框")
            return False
        except Exception as e:
            print(f"[ERROR] 发送私信失败: {e}")
            return False

    async def get_reply_notifications(self) -> list[dict]:
        """
        获取"回复我的"通知列表
        """
        await self.goto_inbox("reply")
        await asyncio.sleep(config.im_scroll_load_wait)

        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(config.im_scroll_reset_wait)

        last_count = 0
        for _ in range(3):
            await self.page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1)
            current_count = await self.page.evaluate(
                "document.querySelectorAll('.interaction-item').length"
            )
            if current_count == last_count:
                break
            last_count = current_count

        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # 读取 JS 代码文件并注入 botName
        import os
        js_path = os.path.join(os.path.dirname(__file__), 'get_notifications.js')
        with open(js_path, encoding='utf-8') as f:
            js_code = f.read().replace('Nya是妮娅啦', config.bot_name.replace("'", "\\'"))

        notifications = await self.page.evaluate(js_code)

        print(f"[DEBUG] 发现 {len(notifications)} 条回复通知")
        for n in notifications[:3]:
            print(f"       - {n.get('user', '')}: {n.get('action', '')} '{n.get('content', '')[:30]}'")

        return notifications

    async def click_reply_button(self, index: int = 0) -> bool:
        """
        点击第 N 个回复按钮，激活回复输入框
        如果弹出 modal，先关闭它
        """
        try:
            await self._close_modal_if_any()

            btns = self.page.locator(
                '.interaction-item__btn:not(.invisible), '
                '[class*="reply-btn"]:not(.invisible), '
                '[class*="reply_action"]'
            )
            count = await btns.count()
            if count == 0:
                print("[ERROR] 没有找到可点击的回复按钮")
                return False

            if index >= count:
                print(f"[ERROR] 索引 {index} 超出范围（共 {count} 个按钮）")
                return False

            btn = btns.nth(index)
            await btn.scroll_into_view_if_needed()
            await asyncio.sleep(config.im_btn_click_wait)
            await btn.click(timeout=5000)

            textarea = self.page.locator('textarea')
            for _ in range(10):
                try:
                    if await textarea.count() > 0 and await textarea.first.is_visible(timeout=1000):
                        print(f"[DEBUG] 点击回复按钮成功，回复框已出现")
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            print(f"[DEBUG] 点击回复按钮成功，等待回复框中...")
            return True
        except Exception as e:
            print(f"[ERROR] 点击回复按钮失败: {e}")
            return False

    async def _close_modal_if_any(self):
        """
        如果页面有 modal 弹出，尝试关闭它
        """
        try:
            mask = self.page.locator('.b-modal-mask, [class*="modal-mask"], [class*="modal-mask"]')
            if await mask.count() > 0:
                visible = await mask.first.is_visible(timeout=2000)
                if visible:
                    print("[DEBUG] 检测到 modal，尝试关闭...")

                    close_btn = self.page.locator('.b-modal-close, [class*="modal-close"], [class*="close"]')
                    if await close_btn.count() > 0:
                        await close_btn.first.click(timeout=2000)
                        print("[DEBUG] 已关闭 modal")
                        await asyncio.sleep(1)
                        return

                    await self.page.keyboard.press('Escape')
                    await asyncio.sleep(1)

                    mask2 = self.page.locator('.b-modal-mask')
                    if await mask2.count() > 0:
                        visible2 = await mask2.first.is_visible(timeout=1000)
                        if visible2:
                            await self.page.mouse.click(10, 10)
                            await asyncio.sleep(1)
        except Exception as e:
            print(f"[DEBUG] 关闭 modal 出错（忽略）: {e}")

    async def send_reply_message(self, text: str) -> bool:
        """在回复通知页面发送回复"""
        try:
            await self._close_modal_if_any()

            textarea_locator = self.page.locator('textarea').first
            visible = False
            for _ in range(5):
                if await textarea_locator.count() > 0:
                    try:
                        visible = await textarea_locator.is_visible(timeout=2000)
                        if visible:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)

            if not visible:
                print("[ERROR] textarea 等待 5s 后仍不可见")
                return False

            await textarea_locator.click()
            await asyncio.sleep(0.3)

            await textarea_locator.click(click_count=3)
            await asyncio.sleep(0.2)

            await textarea_locator.press_sequentially(text)
            await asyncio.sleep(0.3)

            val_before = await self.page.evaluate(
                "document.querySelector('textarea')?.value || ''"
            )
            print(f"[DEBUG] textarea 填入后值: {val_before!r}")
            if text not in val_before:
                print(f"[ERROR] 内容未填入 reply textarea")
                return False

            await self._close_modal_if_any()

            send_btn = self.page.locator(
                '.message-reply-box__pub, '
                '[class*="reply-box"] [class*="pub"], '
                'button[class*="send"], '
                '[class*="reply"] button[class*="send"]'
            )
            if await send_btn.count() > 0 and await send_btn.first.is_visible(timeout=2000):
                await send_btn.first.click(timeout=5000)
            else:
                await self.page.keyboard.press('Enter')
            await asyncio.sleep(1.5)

            val_after = await self.page.evaluate(
                "document.querySelector('textarea')?.value || ''"
            )
            print(f"[DEBUG] textarea 发送后值: {val_after!r}")

            if val_after == '':
                print(f"[DEBUG] 回复通知发送成功: {text[:30]}...")
                return True
            else:
                await asyncio.sleep(2)
                val_after2 = await self.page.evaluate(
                    "document.querySelector('textarea')?.value || ''"
                )
                if val_after2 == '':
                    print(f"[DEBUG] 回复通知发送成功: {text[:30]}...")
                    return True
                print(f"[ERROR] 回复发送失败（内容未清空）")
                return False
        except Exception as e:
            print(f"[ERROR] 发送回复失败: {e}")
            return False

    async def get_peer_id_from_url(self) -> Optional[str]:
        """从 URL 获取对方 mid"""
        url = self.page.url
        match = re.search(r'/mid(\d+)', url)
        if match:
            return match.group(1)
        return None

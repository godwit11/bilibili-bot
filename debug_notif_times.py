#!/usr/bin/env python3
"""临时脚本：直接检查通知列表中各通知的时间和解析状态"""
import asyncio, sys
sys.path.insert(0, '.')
from session.manager import SessionManager
from utils.time_parser import parse_bilibili_time
from datetime import datetime

async def main():
    session = SessionManager()
    await session.initialize()
    page = await session.get_page()
    await page.goto("https://message.bilibili.com/#/reply", timeout=60000)
    await asyncio.sleep(3)

    # 获取通知原始数据
    from im.browser import IMBrowser
    browser = IMBrowser(page)
    notifications = await browser.get_reply_notifications()

    start_time = datetime.now()
    print(f"Bot启动时间: {start_time}")
    print(f"共 {len(notifications)} 条通知\n")

    for i, n in enumerate(notifications):
        t_str = n.get('time', '')
        parsed = parse_bilibili_time(t_str)
        is_new = "🆕" if parsed and parsed >= start_time else "  "
        is_none = "⚠️ None" if parsed is None else ""
        print(f"{is_new} [{i:2}] time={t_str!r:30} 解析={parsed}  {is_none}")
        print(f"      user_reply={n.get('user_reply', '')!r}")
        print(f"      alreadyReplied={n.get('alreadyReplied')}")
        print(f"      content={n.get('content', '')!r}")
        print()

    await session.close()

asyncio.run(main())

"""
SessionManager - Playwright 浏览器生命周期管理
管理浏览器上下文、Cookie、登录状态验证
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import playwright
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import config


class SessionExpiredError(Exception):
    """Session 过期异常"""
    pass


class BrowserCrashedError(Exception):
    """浏览器崩溃异常"""
    pass


@dataclass
class SessionInfo:
    """会话信息"""
    is_login: bool
    mid: Optional[int] = None
    uname: Optional[str] = None


class SessionManager:
    """
    管理 Playwright 浏览器生命周期

    - 初始化浏览器和上下文
    - 加载/保存 Cookie
    - 验证登录状态
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._cookies_path = config.bilibili_cookies_path
        self._page: Optional[Page] = None  # 复用的 page

    async def initialize(self) -> SessionInfo:
        """
        初始化浏览器和上下文
        返回登录状态信息
        """
        self.playwright = await async_playwright().start()
        # 使用 Playwright 下载的 Chromium
        self.browser = await self.playwright.chromium.launch(
            headless=config.headless,
            args=[
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        # 创建一个不包含任何额外设置的 context
        self.context = await self.browser.new_context()

        # 加载 Cookie
        await self._load_cookies()

        # 验证登录状态
        session_info = await self.validate_session()
        return session_info

    async def _load_cookies(self):
        """从文件加载 Cookie"""
        cookies_file = Path(self._cookies_path)
        if not cookies_file.exists():
            print(f"[WARN] Cookie 文件不存在: {self._cookies_path}")
            print("[INFO] 请先运行 python bot.py login 进行登录")
            return

        with open(cookies_file, 'r', encoding='utf-8') as f:
            cookies_data = json.load(f)

        # 转换为 Playwright 格式
        for cookie in cookies_data:
            # 移除 secure 字段（如果有的话）
            cookie_item = {
                'name': cookie.get('name', ''),
                'value': cookie.get('value', ''),
                'domain': cookie.get('domain', '.bilibili.com'),
                'path': cookie.get('path', '/'),
            }
            if 'expires' in cookie:
                cookie_item['expires'] = cookie['expires']
            if 'httpOnly' in cookie:
                cookie_item['httpOnly'] = cookie['httpOnly']
            if 'secure' in cookie:
                cookie_item['secure'] = cookie['secure']

            try:
                await self.context.add_cookies([cookie_item])
            except Exception as e:
                print(f"[WARN] 添加 Cookie 失败: {cookie.get('name', 'unknown')}: {e}")

    async def save_cookies(self):
        """保存 Cookie 到文件"""
        if not self.context:
            return

        cookies = await self.context.cookies()
        cookies_file = Path(self._cookies_path)
        cookies_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)

        print(f"[INFO] Cookie 已保存到: {self._cookies_path}")

    async def validate_session(self) -> SessionInfo:
        """
        验证登录状态
        访问 B站 API 获取用户信息
        """
        if not self.context:
            return SessionInfo(is_login=False)

        page = await self.context.new_page()
        try:
            await page.goto(
                'https://api.bilibili.com/x/web-interface/nav',
                timeout=config.browser_timeout
            )
            await page.wait_for_load_state('networkidle')

            content = await page.content()
            text = await page.inner_text('body')

            # 尝试解析 JSON 响应
            try:
                data = await page.evaluate('JSON.parse(document.body.innerText)')
                is_login = data.get('data', {}).get('isLogin', False)
                if is_login:
                    mid = data.get('data', {}).get('mid')
                    uname = data.get('data', {}).get('uname')
                    print(f"[INFO] 已登录: {uname} (mid: {mid})")
                    return SessionInfo(is_login=True, mid=mid, uname=uname)
            except:
                pass

            # 检查页面内容中是否包含登录信息
            if 'mid' in text or '"isLogin":true' in content:
                return SessionInfo(is_login=True)

            print("[WARN] 未检测到登录状态，请重新登录")
            return SessionInfo(is_login=False)

        except Exception as e:
            print(f"[ERROR] 验证登录状态失败: {e}")
            return SessionInfo(is_login=False)
        finally:
            await page.close()

    async def get_page(self) -> Page:
        """获取一个新的页面（带自动恢复）"""
        if not self.context:
            raise RuntimeError("SessionManager 未初始化，请先调用 initialize()")

        # 每次创建新 page，并确保 context 是新鲜的
        if hasattr(self, '_page') and self._page:
            try:
                await self._page.close()
            except:
                pass

        try:
            self._page = await self.context.new_page()
            return self._page
        except (playwright.TimeoutError, playwright.Error) as e:
            # Browser 或 context 可能已失效，尝试恢复
            print(f"[WARN] 获取页面失败: {e}，尝试恢复 Session...")
            await self.recover_session()
            self._page = await self.context.new_page()
            return self._page

    async def login_interactive(self) -> bool:
        """
        交互式登录
        打开浏览器让用户手动登录
        """
        if not self.browser:
            self.playwright = await async_playwright().start()
            # 使用系统 Edge 浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=False,  # 必须显示浏览器
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
            )

        page = await self.context.new_page()
        await page.goto('https://www.bilibili.com')
        print("[INFO] 请在浏览器中登录 B站...")
        print("[INFO] 登录完成后按回车继续...")

        # 等待用户按回车
        input()

        # 保存 Cookie
        await self.save_cookies()

        # 验证登录
        session_info = await self.validate_session()
        await page.close()

        return session_info.is_login

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("[INFO] 浏览器已关闭")

    async def recover_session(self) -> SessionInfo:
        """
        自动恢复 Session
        1. 尝试检测登录状态
        2. 如果未登录或浏览器崩溃，自动重新初始化
        """
        print("[INFO] 尝试恢复 Session...")

        # 如果 browser 已崩溃，先清理
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass  # 忽略崩溃错误

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

        self.browser = None
        self.context = None
        self.playwright = None

        # 重新初始化
        session_info = await self.initialize()

        if not session_info.is_login:
            print("[WARN] Session 恢复后仍未登录，需要手动重新登录")
            print("[INFO] 请运行: python bot.py login")

        return session_info

    async def ensure_valid_session(self) -> SessionInfo:
        """
        确保 Session 有效，不有效则尝试恢复
        返回 SessionInfo
        """
        try:
            # 先验证当前 session
            session_info = await self.validate_session()
            if session_info.is_login:
                return session_info

            # 未登录，尝试恢复
            print("[WARN] Session 已过期，尝试自动恢复...")
            return await self.recover_session()

        except (playwright.TimeoutError, playwright.Error, BrowserCrashedError) as e:
            print(f"[WARN] Session 异常: {e}，尝试自动恢复...")
            return await self.recover_session()

"""
im/api.py - B站私信/回复 API
处理私信和评论回复的收发
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import httpx

from config import config


class BilibiliIMAPI:
    """
    B站私信和评论回复 API
    """

    def __init__(self):
        self.base_url = "https://api.bilibili.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com',
        }
        self._cookies_cache: Optional[dict] = None

    def _load_cookies(self, force_reload: bool = False) -> dict:
        """
        加载 Cookie（带缓存）

        Args:
            force_reload: 强制重新加载，忽略缓存
        """
        if self._cookies_cache and not force_reload:
            return self._cookies_cache

        cookies_file = Path(config.bilibili_cookies_path)
        if not cookies_file.exists():
            raise Exception(f"Cookie 文件不存在: {config.bilibili_cookies_path}")
        with open(cookies_file, 'r') as f:
            cookies = json.load(f)
        cookie_dict = {}
        for c in cookies:
            cookie_dict[c['name']] = c['value']
        self._cookies_cache = cookie_dict
        return cookie_dict
        """加载 Cookie"""
        cookies_file = Path(config.bilibili_cookies_path)
        if not cookies_file.exists():
            raise Exception(f"Cookie 文件不存在: {config.bilibili_cookies_path}")
        with open(cookies_file, 'r') as f:
            cookies = json.load(f)
        cookie_dict = {}
        for c in cookies:
            cookie_dict[c['name']] = c['value']
        return cookie_dict

    async def get_session_list(self) -> list[dict]:
        """
        获取私信会话列表
        返回会话信息列表
        """
        cookies = self._load_cookies()
        url = f"{self.base_url}/x/web-im/menuSession/list"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={'page_size': 20, 'build': 0, 'mobi_app': 'web'},
                cookies=cookies,
                headers=self.headers,
                timeout=30
            )
            data = response.json()
            if data.get('code') == 0:
                return data.get('data', {}).get('session_list', [])
            print(f"[ERROR] 获取会话列表失败: {data.get('message', 'Unknown')}")
            return []

    async def get_unread_sessions(self) -> list[dict]:
        """获取有未读消息的会话"""
        all_sessions = await self.get_session_list()
        return [s for s in all_sessions if s.get('unread_count', 0) > 0]

    async def get_session_messages(self, session_key: str, size: int = 20) -> list[dict]:
        """
        获取某个会话的最新消息

        Args:
            session_key: 会话标识（格式：userid_对方mid）
            size: 获取消息数量
        """
        cookies = self._load_cookies()
        url = f"{self.base_url}/x/web-im/menuSession/newBack"

        # 解析 session_key 获取本端和对方信息
        parts = session_key.split('_')
        if len(parts) < 2:
            return []
        my_mid = parts[0]
        peer_mid = parts[1]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={
                    'conversation_type': 1,
                    'peer_id': peer_mid,
                    'size': size,
                },
                cookies=cookies,
                headers=self.headers,
                timeout=30
            )
            data = response.json()
            if data.get('code') == 0:
                return data.get('data', {}).get('messages', [])
            print(f"[ERROR] 获取会话消息失败: {data.get('message', 'Unknown')}")
            return []

    async def send_message(self, receiver_mid: str, content: str) -> bool:
        """
        发送私信

        Args:
            receiver_mid: 接收者 mid
            content: 消息内容

        Returns:
            是否发送成功
        """
        cookies = self._load_cookies()

        if 'SESSDATA' not in cookies or 'bili_jct' not in cookies:
            print("[ERROR] Cookie 缺少必要的 SESSDATA 或 bili_jct")
            return False

        url = f"{self.base_url}/x/web-im/sendmsg.send"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data={
                    'msg[receiver]': receiver_mid,
                    'msg[content]': content,
                    'msg[msg_type]': 1,  # 文本消息
                    'csrf': cookies.get('bili_jct', ''),
                },
                cookies=cookies,
                headers=self.headers,
                timeout=30
            )
            result = response.json()
            if result.get('code') == 0:
                print(f"[OK] 私信发送成功: {content[:30]}...")
                return True
            else:
                print(f"[ERROR] 私信发送失败: {result.get('message', 'Unknown error')}")
                return False

    async def get_self_mid(self) -> Optional[str]:
        """获取自己的 mid"""
        cookies = self._load_cookies()
        url = f"{self.base_url}/x/web-interface/nav"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, cookies=cookies, headers=self.headers, timeout=30)
            data = response.json()
            if data.get('code') == 0:
                return str(data['data']['mid'])
            return None

"""
video/search_api.py - B站 搜索 API
直接调用 B站 搜索 API，更稳定
"""

import httpx
import json
from typing import Optional

from config import config


class BilibiliSearchAPI:
    """
    B站 搜索 API
    通过 HTTP API 搜索视频，更可靠
    """

    def __init__(self):
        self.base_url = "https://api.bilibili.com"
        self.search_url = "https://search.bilibili.com/api/search_search"

    def _load_cookies(self) -> dict:
        """加载 Cookie"""
        from pathlib import Path
        cookies_file = Path(config.bilibili_cookies_path)
        if not cookies_file.exists():
            raise Exception(f"Cookie 文件不存在: {config.bilibili_cookies_path}")

        with open(cookies_file, 'r') as f:
            cookies = json.load(f)

        # 转换为 dict
        cookie_dict = {}
        for c in cookies:
            cookie_dict[c['name']] = c['value']

        return cookie_dict

    def search(self, keyword: str, page: int = 1) -> list[dict]:
        """
        搜索视频

        Returns:
            list of video info dicts with keys: bvid, title, author, duration, play, video_review
        """
        cookies = self._load_cookies()

        params = {
            'keyword': keyword,
            'page': page,
            'pagesize': 20,
            'search_type': 'video',
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://search.bilibili.com/',
        }

        try:
            response = httpx.get(
                self.search_url,
                params=params,
                cookies=cookies,
                headers=headers,
                timeout=30
            )
            data = response.json()

            if data.get('code') == 0:
                result = data.get('result', {})
                videos = result.get('video', [])
                return videos
            else:
                print(f"[ERROR] 搜索失败: {data.get('message', 'Unknown error')}")
                return []

        except Exception as e:
            print(f"[ERROR] 搜索请求失败: {e}")
            return []


# 全局实例
search_api = BilibiliSearchAPI()

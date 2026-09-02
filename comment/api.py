"""
comment/api.py - B站评论 API
直接调用 B站 API 发布评论，更稳定
"""

import asyncio
import json
import re
from typing import Optional

import httpx

from config import config


class BilibiliCommentAPI:
    """
    B站评论 API
    通过 HTTP API 发布评论，不依赖 DOM
    """

    def __init__(self):
        self.base_url = "https://api.bilibili.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com',
        }

    def _load_cookies(self) -> dict:
        """加载 Cookie"""
        import os
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

    async def get_danmaku(self, bvid: str, max_count: int = 200) -> list[str]:
        """
        获取视频弹幕

        Args:
            bvid: 视频 BV 号
            max_count: 最多返回弹幕数（过滤垃圾后）

        Returns:
            弹幕文本列表
        """
        import xml.etree.ElementTree as ET

        # 先获取视频信息（含 cid）
        video_info = await self.get_video_info(bvid)
        if not video_info:
            return []
        cid = video_info.get('cid')
        if not cid:
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/x/v1/dm/list.so?oid={cid}",
                    headers={
                        'Referer': 'https://www.bilibili.com',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    },
                    timeout=15
                )
                if response.status_code != 200:
                    return []

                content = response.text
                # 解析 XML
                try:
                    root = ET.fromstring(content)
                except ET.ParseError:
                    return []

                ns = {'d': 'http://www.bilibili.com/danmaku'}
                danmakus = []
                for d in root.findall('.//d', ns) or root.findall('.//d'):
                    text = d.text or ''
                    if text.strip():
                        danmakus.append(text.strip())

                # 过滤垃圾弹幕
                filtered = self._filter_danmaku(danmakus)
                return filtered[:max_count]

        except Exception as e:
            print(f"[ERROR] 获取弹幕失败: {e}")
            return []

    def _filter_danmaku(self, danmakus: list[str]) -> list[str]:
        """
        过滤垃圾弹幕，保留有价值的内容弹幕
        """
        # 垃圾弹幕特征
        junk_patterns = [
            r'^[​-‏　-〿]',  # 零宽字符开头
            r'(下载|获取|地址|链接|网站|加群|群号|QQ|微信)',
            r'(版权|侵权|删|举报)',
            r'(签到|大会员|抽奖)',
            r'(上\s*网|联\s*系\s*我)',
            r'^(.)\1{5,}$',  # 单字符重复超过5次
            r'^(.{1,3})\1{3,}$',  # 短周期重复
            r'^\s*$',
            r'(bilibili\.com|bili2233)',
            r'(广告|推\s*广)',
        ]
        # 有意义的弹幕特征（保留）
        quality_patterns = [
            r'[一-鿿]',  # 含中文
            r'[a-zA-Z]{3,}',  # 英文单词
            r'[?!?。！？]',  # 含有句末标点
        ]

        def is_junk(d):
            for p in junk_patterns:
                if re.search(p, d, re.IGNORECASE):
                    return True
            # 检查是否是有效内容
            has_content = any(re.search(p, d) for p in quality_patterns)
            if not has_content:
                return True
            # 过滤过长的弹幕（通常是刷屏）
            if len(d) > 50:
                return True
            return False

        return [d for d in danmakus if not is_junk(d)]

    async def get_video_info(self, bvid: str) -> Optional[dict]:
        """
        获取视频完整信息

        Returns:
            dict with keys: aid, title, description, duration, pic, owner (mid, name, face),
                            stat (view, like, coin, favorite, share, danmaku),
                            tags (list of tag names), pubdate, tname (type)
        """
        url = f"{self.base_url}/x/web-interface/view"
        params = {'bvid': bvid}
        cookies = self._load_cookies()

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, cookies=cookies, headers=self.headers)
            data = response.json()

            if data.get('code') == 0:
                d = data['data']
                return {
                    'aid': d.get('aid'),
                    'bvid': d.get('bvid'),
                    'title': d.get('title', ''),
                    'description': d.get('desc', ''),
                    'duration': d.get('duration', 0),
                    'pic': d.get('pic', ''),
                    'owner_mid': d.get('owner', {}).get('mid', 0),
                    'owner_name': d.get('owner', {}).get('name', ''),
                    'stat': d.get('stat', {}),
                    'tags': [t.get('tag_name', '') for t in d.get('tags', []) if t.get('tag_name')],
                    'pubdate': d.get('pubdate', 0),
                    'tname': d.get('tname', ''),  # 视频分区类型名
                    'cid': d.get('cid') or (d.get('pages', [{}])[0].get('cid') if d.get('pages') else None),
                }
            return None

    async def get_video_oid(self, bvid: str) -> Optional[str]:
        """
        获取视频的 oid（aid）
        B站评论需要 oid 参数
        """
        url = f"{self.base_url}/x/web-interface/view"
        params = {'bvid': bvid}

        cookies = self._load_cookies()

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, cookies=cookies, headers=self.headers)
            data = response.json()

            if data.get('code') == 0:
                return str(data['data']['aid'])
            return None

    async def post_comment(self, bvid: str, content: str) -> bool:
        """
        发布评论

        Args:
            bvid: 视频 BV 号
            content: 评论内容

        Returns:
            是否发布成功
        """
        cookies = self._load_cookies()

        # 检查必要的 cookie
        if 'SESSDATA' not in cookies or 'bili_jct' not in cookies:
            print("[ERROR] Cookie 缺少必要的 SESSDATA 或 bili_jct")
            return False

        # 获取视频 oid
        oid = await self.get_video_oid(bvid)
        if not oid:
            print("[ERROR] 获取视频 ID 失败")
            return False

        # 调用评论 API
        url = f"{self.base_url}/x/v2/reply/add"
        data = {
            'oid': oid,
            'type': 1,  # 视频
            'message': content,
            'plat': 1,  # Web
            'csrf': cookies.get('bili_jct', ''),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data=data,
                cookies=cookies,
                headers=self.headers,
                timeout=30
            )
            result = response.json()

            if result.get('code') == 0:
                print(f"[OK] 评论发布成功: {content[:30]}...")
                return True
            else:
                print(f"[ERROR] 评论发布失败: {result.get('message', 'Unknown error')}")
                return False


# 全局实例
comment_api = BilibiliCommentAPI()

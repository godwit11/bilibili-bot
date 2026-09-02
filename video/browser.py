"""
video/browser.py - 视频浏览功能
通过 Playwright 获取视频信息、评论、搜索结果
"""

import asyncio
import re
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

from config import config
from session.manager import SessionManager
from video.models import VideoInfo, CommentInfo, VideoSearchResult


class VideoBrowser:
    """
    视频浏览类
    通过 Playwright 从 B站网页提取数据
    """

    def __init__(self, session: SessionManager):
        self.session = session

    async def get_video_info(self, bvid: str) -> Optional[VideoInfo]:
        """
        获取视频详情信息（通过 B站 API，不依赖 DOM 解析）
        """
        try:
            from comment.api import BilibiliCommentAPI
            api = BilibiliCommentAPI()
            info = await api.get_video_info(bvid)
            if not info:
                return None

            stat = info.get('stat', {})
            return VideoInfo(
                bvid=bvid,
                title=info.get('title', ''),
                description=info.get('description', ''),
                uploader_mid=info.get('owner_mid', 0),
                uploader_name=info.get('owner_name', ''),
                publish_time=datetime.fromtimestamp(info.get('pubdate', 0)) if info.get('pubdate') else None,
                view_count=stat.get('view', 0),
                like_count=stat.get('like', 0),
                coin_count=stat.get('coin', 0),
                favorite_count=stat.get('favorite', 0),
                share_count=stat.get('share', 0),
                duration=info.get('duration', 0),
                tags=info.get('tags', []),
                url=f"https://www.bilibili.com/video/{bvid}",
                aid=info.get('aid')
            )

        except Exception as e:
            print(f"[ERROR] 获取视频信息失败: {e}")
            return None

    async def play_video_and_watch(self, bvid: str, watch_seconds: float = None) -> Optional[VideoInfo]:
        """
        真正播放视频并发送心跳包，B站才能记录观看历史

        Args:
            bvid: 视频 BV 号
            watch_seconds: 观看时长（秒），None 则使用随机时长

        Returns:
            VideoInfo if successful
        """
        import random
        page = await self.session.get_page()
        try:
            url = f"https://www.bilibili.com/video/{bvid}"
            await page.goto(url, timeout=config.video_page_load_timeout)
            await page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(2)

            # 获取基本信息（Playwright Python 没有 .catch()，用 try/except）
            try:
                title = await page.inner_text('h1.video-title, h1.title')
            except Exception:
                title = "未知标题"
            try:
                duration_text = await page.inner_text('.video-duration, .duration')
            except Exception:
                duration_text = "0:00"
            uploader_name = ""
            uploader_elem = await page.query_selector('.up-name, a[href*="/space/"]')
            if uploader_elem:
                try:
                    uploader_name = await uploader_elem.inner_text()
                except Exception:
                    uploader_name = ""

            # ========== 第一步：启动播放 ==========
            # 尝试多种方式启动播放
            started = False
            for attempt in range(3):
                # 方式1：直接操作 video 元素
                started = await page.evaluate('''
                    () => {
                        const video = document.querySelector('video');
                        if (!video) return false;
                        video.muted = false;
                        const promise = video.play();
                        if (promise !== undefined) {
                            promise.catch(() => {});
                        }
                        return true;
                    }
                ''')
                if started:
                    print(f"[DEBUG] video.play() 启动成功")
                    break

                # 方式2：点击播放器中央播放按钮
                for btn_sel in [
                    '.bilibili-player-video-btn-big',      # 大播放按钮
                    '.bilibili-player-video-wrap',          # 播放器区域
                    '.player-wrap',                          # 播放器容器
                    '.video-player',                         # 视频播放器
                ]:
                    try:
                        btn = await page.wait_for_selector(btn_sel, timeout=2000)
                        if btn:
                            await btn.click()
                            await asyncio.sleep(1)
                            started = await page.evaluate('() => document.querySelector("video")?.paused === false');
                            if started:
                                print(f"[DEBUG] 点击 {btn_sel} 启动播放成功")
                                break
                    except:
                        continue
                if started:
                    break

                # 方式3：按 K 键
                await page.keyboard.press('k')
                await asyncio.sleep(1)
                started = await page.evaluate('() => document.querySelector("video")?.paused === false');
                if started:
                    print(f"[DEBUG] K 键启动播放成功")
                    break

                await asyncio.sleep(1)

            if not started:
                print(f"[WARN] 无法启动播放，尝试继续...")

            await asyncio.sleep(2)  # 等待播放稳定

            # ========== 第二步：提取 aid（需要播放后才能从 __playinfo__ 获取）==========
            aid = await page.evaluate('''
                () => {
                    // 方式1：从 window.__playinfo__ 获取
                    try {
                        if (window.__playinfo__ && window.__playinfo__.data) {
                            return window.__playinfo__.data.aid || 0;
                        }
                    } catch(e) {}

                    // 方式2：从页面埋ime-ima获取
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.includes('"aid"') || text.includes("'aid'")) {
                            const m = text.match(/["']aid["']\\s*:\\s*(\\d+)/);
                            if (m) return parseInt(m[1]);
                        }
                    }

                    // 方式3：从 bvid 通过 API 换算（备用）
                    return 0;
                }
            ''')

            if aid == 0:
                # 备用：从 bvid 通过 API 获取 aid
                print(f"[DEBUG] 未能从页面获取 aid，尝试通过 bvid 查询")
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            'https://api.bilibili.com/x/web-interface/view',
                            params={'bvid': bvid},
                            timeout=10
                        )
                        data = resp.json()
                        if data.get('code') == 0:
                            aid = data['data']['aid']
                            print(f"[DEBUG] 通过 API 获取到 aid: {aid}")
                except Exception as e:
                    print(f"[DEBUG] API 获取 aid 失败: {e}")

            print(f"[DEBUG] 使用 aid: {aid}")

            # ========== 第三步：发送心跳 + 计时观看 ==========
            total_watch = watch_seconds if watch_seconds else random.uniform(20.0, 60.0)
            print(f"[DEBUG] 计划观看 {total_watch:.0f} 秒")

            last_heartbeat_at = -1
            async def send_hb(elapsed: int):
                await self._send_heartbeat(page, bvid, aid, elapsed)

            start_time = asyncio.get_event_loop().time()
            await send_hb(0)  # 初始心跳

            while True:
                await asyncio.sleep(3)
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= total_watch:
                    break

                # 每 15 秒发一次心跳（确保每次只发一次）
                heartbeat_mark = int(elapsed) // 15
                if heartbeat_mark > last_heartbeat_at:
                    last_heartbeat_at = heartbeat_mark
                    await send_hb(int(elapsed))
                    print(f"[DEBUG] 观看 {int(elapsed)}s，已发送心跳")

            video_info = VideoInfo(
                bvid=bvid,
                title=title.strip() if title else "未知标题",
                description="",
                uploader_mid=0,
                uploader_name=uploader_name.strip() if uploader_name else "未知UP主",
                publish_time=None,
                view_count=0,
                like_count=0,
                coin_count=0,
                favorite_count=0,
                share_count=0,
                duration=self._parse_duration_to_seconds(duration_text),
                tags=[],
                url=url
            )
            return video_info

        except Exception as e:
            print(f"[ERROR] 播放视频失败: {e}")
            return None
        finally:
            await page.close()

    async def _send_heartbeat(self, page: Page, bvid: str, aid, elapsed: int = 0):
        """发送 B站 心跳包"""
        if not aid or aid == 0:
            return
        try:
            await page.evaluate('''
                async (aid, elapsed) => {
                    try {
                        await fetch('https://api.bilibili.com/x/report/web/heartbeat', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Referer': window.location.href
                            },
                            body: `aid=${aid}&cid=0&mid=0&dt=2&${Date.now()}&played_time=${elapsed}&real_played_time=${elapsed}&referfrom=0`
                        });
                    } catch(e) {
                        console.error('heartbeat error', e);
                    }
                }
            ''', aid, elapsed)
        except Exception as e:
            print(f"[DEBUG] 心跳包发送失败: {e}")

    async def get_comments(self, bvid: str, max_pages: int = 5) -> list[CommentInfo]:
        """
        获取视频评论
        """
        page = await self.session.get_page()
        comments = []

        try:
            url = f"https://www.bilibili.com/video/{bvid}?p=1"
            await page.goto(url, timeout=config.comment_load_timeout, wait_until='domcontentloaded')
            await asyncio.sleep(3)

            # 滚动加载评论
            for _ in range(max_pages):
                # 点击加载更多按钮（如果存在）
                more_btn = await page.query_selector('.comment-more, .load-more, [class*="more"]')
                if more_btn:
                    try:
                        await more_btn.click()
                        await asyncio.sleep(0.5)
                    except:
                        pass

                # 滚动页面触发懒加载
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)

            # 提取评论数据 - 用 JavaScript 直接获取
            comment_items = await page.evaluate('''
                () => {
                    // B站评论列表的多种可能选择器
                    const selectors = [
                        '.comment-item',
                        '.list-item',
                        '[class*="comment"]',
                        '[class*="reply"]'
                    ];
                    let items = [];
                    for (const sel of selectors) {
                        items = document.querySelectorAll(sel);
                        if (items.length > 0) break;
                    }

                    const results = [];
                    for (const item of items) {
                        const unameEl = item.querySelector('.uname, .user-name, [class*="name"], [class*="user"]');
                        const contentEl = item.querySelector('.text, .content, [class*="text"], [class*="content"]');
                        const likeEl = item.querySelector('.like, .like-num, [class*="like"]');

                        if (contentEl) {
                            results.push({
                                uname: unameEl ? unameEl.innerText.trim() : '匿名用户',
                                content: contentEl.innerText.trim(),
                                like: likeEl ? likeEl.innerText.trim() : '0'
                            });
                        }
                    }
                    return results;
                }
            ''')

            for item in comment_items[:100]:  # 最多取100条
                try:
                    like_str = re.sub(r'[^0-9]', '', item.get('like', '0'))
                    like_count = int(like_str) if like_str else 0

                    comments.append(CommentInfo(
                        rpid=0,
                        oid=bvid,
                        parent_rpid=0,
                        member_uname=item.get('uname', '匿名用户').strip(),
                        member_face="",
                        content=item.get('content', '').strip(),
                        like_count=like_count,
                        reply_count=0,
                        timestamp=datetime.now(),
                        location=""
                    ))
                except Exception:
                    continue

        except Exception as e:
            print(f"[ERROR] 获取评论失败: {e}")
        finally:
            await page.close()

        return comments

    async def search_videos(self, keyword: str, page_num: int = 1, retries: int = 3) -> list[VideoSearchResult]:
        """
        搜索视频

        Args:
            keyword: 搜索关键词
            page_num: 页码
            retries: 失败重试次数
        """
        page = await self.session.get_page()
        results = []

        try:
            # 检查 cookies
            cookies = await page.context.cookies(['https://bilibili.com'])
            print(f"[DEBUG] bilibili.com cookies 数量: {len(cookies)}")
            for c in cookies[:3]:
                print(f"[DEBUG]   {c['name']}: {c['value'][:20]}...")

            # 直接访问搜索页
            # 注意：B站搜索页第一页不需要 page 参数，page=1 会导致返回 0 结果
            if page_num == 1:
                search_url = f"https://search.bilibili.com/all?keyword={keyword}"
            else:
                search_url = f"https://search.bilibili.com/all?keyword={keyword}&page={page_num}"
            print(f"[DEBUG] 访问: {search_url}")

            # goto + networkidle 是最容易超时的两步，加重试
            last_err = None
            for attempt in range(retries):
                try:
                    await page.goto(search_url, timeout=config.browser_timeout, wait_until='domcontentloaded')
                    # 等动态内容渲染
                    await asyncio.sleep(2)
                    # 滚动触发懒加载
                    await page.evaluate('window.scrollBy(0, 300)')
                    await asyncio.sleep(1)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"[DEBUG] 第 {attempt+1} 次访问失败: {e}，重试中...")
                    await asyncio.sleep(2)

            if last_err:
                print(f"[ERROR] 搜索失败: {last_err}")
                return results

            print(f"[DEBUG] 视频卡片已加载")
            await asyncio.sleep(1)

            # 使用 JavaScript 直接提取数据
            js_results = await page.evaluate('''
                () => {
                    const cards = document.querySelectorAll('.bili-video-card:not(.bili-video-card__skeleton)');
                    const results = [];
                    for (const card of cards) {
                        const link = card.querySelector('a[href*="/video/"]');
                        if (!link) continue;
                        const href = link.getAttribute('href') || '';
                        let bvid = '';
                        const match = href.match(/\\/video\\/(BV\\w+)/);
                        if (match) bvid = match[1];
                        if (!bvid) {
                            const bvMatch = href.match(/BV\\w+/);
                            if (bvMatch) bvid = bvMatch[0];
                        }
                        if (!bvid) continue;
                        // 从 DOM 元素获取标题和 UP 主
                        const titleElem = card.querySelector('.bili-video-card__info--title, .video-title, [class*="title"]');
                        const upElem = card.querySelector('.bili-video-card__info--author, .up-name, [class*="up"]');
                        const durElem = card.querySelector('.bili-video-card__duration, .duration, [class*="duration"]');
                        results.push({
                            bvid: bvid,
                            title: titleElem ? titleElem.innerText.trim() : '',
                            up: upElem ? upElem.innerText.trim() : '',
                            duration: durElem ? durElem.innerText.trim() : ''
                        });
                    }
                    return results;
                }
            ''')

            print(f"[DEBUG] JS 提取到 {len(js_results)} 个视频")

            for item in js_results[:20]:
                bvid = item.get('bvid', '')
                title = item.get('title', '')
                up_name = item.get('up', '')
                duration = item.get('duration', '')

                if title and bvid:
                    results.append(VideoSearchResult(
                        bvid=bvid,
                        title=title.strip(),
                        uploader_name=up_name.strip() if up_name else "未知UP",
                        duration=duration.strip() if duration else "",
                        publish_time="",
                        view_count=0,
                        description="",
                        url=f"https://www.bilibili.com/video/{bvid}"
                    ))

        except Exception as e:
            print(f"[ERROR] 搜索失败: {e}")
        finally:
            await page.close()

        return results

    async def browse_homepage(self, scroll_count: int = 1, retries: int = 3) -> list[VideoSearchResult]:
        """
        浏览首页，滚动页面并收集视频信息

        Args:
            scroll_count: 滚动次数
            retries: 失败重试次数

        Returns:
            视频列表
        """
        page = await self.session.get_page()
        results = []

        try:
            # 访问首页（加重试）
            last_err = None
            for attempt in range(retries):
                try:
                    await page.goto("https://www.bilibili.com/", timeout=config.browser_timeout, wait_until='domcontentloaded')
                    # 等动态内容渲染
                    await asyncio.sleep(2)
                    # 滚动触发懒加载
                    await page.evaluate('window.scrollBy(0, 300)')
                    await asyncio.sleep(1)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"[DEBUG] 第 {attempt+1} 次访问首页失败: {e}，重试中...")
                    await asyncio.sleep(2)

            if last_err:
                print(f"[ERROR] 浏览首页失败: {last_err}")
                return results

            await page.set_viewport_size({'width': 1280, 'height': 720})
            await asyncio.sleep(3)

            # 滚动页面触发加载
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(2)

            # 提取当前可见的视频
            videos = await page.evaluate('''
                () => {
                    const cards = document.querySelectorAll('.bili-video-card a[href*="/video/"]');
                    const results = [];
                    const seen = new Set();
                    for (const link of cards) {
                        const href = link.getAttribute('href') || '';
                        let bvid = '';
                        const match = href.match(/\\/video\\/(BV\\w+)/);
                        if (match) bvid = match[1];
                        if (!bvid) {
                            const bvMatch = href.match(/BV\\w+/);
                            if (bvMatch) bvid = bvMatch[0];
                        }
                        if (!bvid || seen.has(bvid)) continue;
                        seen.add(bvid);
                        results.push({
                            bvid: bvid,
                            href: href
                        });
                    }
                    return results;
                }
            ''')

            for v in videos:
                results.append(VideoSearchResult(
                    bvid=v['bvid'],
                    title="",  # 首页卡片标题提取复杂，留空
                    uploader_name="",
                    duration="",
                    publish_time="",
                    view_count=0,
                    description="",
                    url=f"https://www.bilibili.com/video/{v['bvid']}"
                ))

        except Exception as e:
            print(f"[ERROR] 浏览首页失败: {e}")
        finally:
            await page.close()

        return results

    def _parse_duration_to_seconds(self, duration_text: str) -> int:
        """将 "3:45" 格式的时长转换为秒"""
        if not duration_text:
            return 0
        try:
            parts = duration_text.strip().split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return int(parts[0])
        except Exception:
            return 0

    def _parse_number(self, text: str) -> int:
        """解析数字文本（如 1.2万）"""
        text = text.strip()
        if not text:
            return 0
        # 移除万、亿等单位
        if '万' in text:
            return int(float(text.replace('万', '')) * 10000)
        if '亿' in text:
            return int(float(text.replace('亿', '')) * 100000000)
        return int(re.sub(r'[^0-9]', '', text)) if text else 0

    def _extract_bvid(self, href: str) -> str:
        """从URL中提取BV号"""
        if not href:
            return ""
        match = re.search(r'BV[\w]+', href)
        return match.group(0) if match else ""

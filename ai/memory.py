"""
ai/memory.py - 记忆管理器
记录 Bot 的浏览历史、评论历史、兴趣偏好
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class VideoMemory:
    """视频记忆"""
    bvid: str
    title: str
    uploader: str
    browsed_at: str
    commented: bool = False
    comment_content: str = ""
    watch_duration: float = 0  # 秒


@dataclass
class InterestProfile:
    """兴趣画像"""
    keywords: list[str] = field(default_factory=list)  # 感兴趣的关键词
    favorite_uploaders: list[str] = field(default_factory=list)  # 常看的UP主
    disliked_keywords: list[str] = field(default_factory=list)  # 不感兴趣的关键词

    def add_keyword(self, keyword: str):
        if keyword not in self.keywords:
            self.keywords.append(keyword)
            # 保持最多 50 个关键词
            if len(self.keywords) > 50:
                self.keywords.pop(0)

    def add_favorite_uploader(self, uploader: str):
        if uploader not in self.favorite_uploaders:
            self.favorite_uploaders.append(uploader)
            if len(self.favorite_uploaders) > 20:
                self.favorite_uploaders.pop(0)


class MemoryManager:
    """
    记忆管理器
    管理 Bot 的长期记忆和短期记忆
    """

    def __init__(self, memory_dir: str = "storage/memory", db=None):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.videos_file = self.memory_dir / "videos.json"
        self.interests_file = self.memory_dir / "interests.json"
        self.session_file = self.memory_dir / "session.json"

        # 加载记忆
        self.video_memory: dict[str, VideoMemory] = {}
        self.interests = InterestProfile()
        self.session_history: list[dict] = []
        self._db = db  # SQLite Database instance (optional)

        self._load()

    def set_database(self, db):
        """设置 SQLite 数据库实例，用于同步写评论记录"""
        self._db = db

    def _load(self):
        """加载记忆"""
        # 加载视频记忆
        if self.videos_file.exists():
            try:
                with open(self.videos_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for v in data.values():
                        self.video_memory[v['bvid']] = VideoMemory(**v)
            except Exception as e:
                print(f"[WARN] 加载视频记忆失败: {e}")

        # 加载兴趣
        if self.interests_file.exists():
            try:
                with open(self.interests_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.interests = InterestProfile(**data)
            except Exception as e:
                print(f"[WARN] 加载兴趣记忆失败: {e}")

    def _save(self):
        """保存记忆"""
        # 保存视频记忆
        try:
            data = {bvid: vars(mem) for bvid, mem in self.video_memory.items()}
            with open(self.videos_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 保存视频记忆失败: {e}")

        # 保存兴趣
        try:
            with open(self.interests_file, 'w', encoding='utf-8') as f:
                json.dump(vars(self.interests), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 保存兴趣记忆失败: {e}")

    def remember_video(self, bvid: str, title: str, uploader: str):
        """记录浏览过的视频"""
        if bvid in self.video_memory:
            # 更新时间
            self.video_memory[bvid].browsed_at = datetime.now().isoformat()
        else:
            self.video_memory[bvid] = VideoMemory(
                bvid=bvid,
                title=title,
                uploader=uploader,
                browsed_at=datetime.now().isoformat()
            )

        # 更新兴趣
        self.interests.add_favorite_uploader(uploader)
        self._save()

    def record_comment(self, bvid: str, content: str):
        """
        记录评论
        db 是权威数据源，memory 是缓存
        """
        # 优先写 db（权威数据源）
        if self._db:
            self._db.store_comment(bvid, content, 'success')
        # 再更新 memory 缓存
        if bvid in self.video_memory:
            self.video_memory[bvid].commented = True
            self.video_memory[bvid].comment_content = content
        self._save()

    def has_commented(self, bvid: str) -> bool:
        """
        检查是否评论过
        优先查 db（权威数据源），如果 db 无记录则查 memory 缓存
        """
        # db 是权威数据源
        if self._db:
            db_result = self._db.has_commented(bvid)
            if db_result:
                return True
            # db 没有，再看 memory（避免 memory 和 db 不一致）
        return self.video_memory.get(bvid, VideoMemory(bvid="", title="", uploader="", browsed_at="")).commented

    def get_recent_uncommented(self, limit: int = 10) -> list[VideoMemory]:
        """
        获取最近未评论的视频
        以 db 为准，排除已评论的视频
        """
        videos = []
        for v in self.video_memory.values():
            # 用 db 判断是否已评论（权威数据源）
            if self._db and self._db.has_commented(v.bvid):
                continue
            # memory 中标记已评论的也跳过
            if v.commented:
                continue
            videos.append(v)
        videos.sort(key=lambda x: x.browsed_at, reverse=True)
        return videos[:limit]

    def add_interest_keyword(self, keyword: str):
        """添加兴趣关键词"""
        self.interests.add_keyword(keyword)
        self._save()

    def add_session_action(self, action: str, target: str, result: str):
        """记录一次会话行为"""
        self.session_history.append({
            'time': datetime.now().isoformat(),
            'action': action,
            'target': target,
            'result': result
        })
        # 保持最近 100 条会话记录
        if len(self.session_history) > 100:
            self.session_history = self.session_history[-100:]

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = len(self.video_memory)
        commented = sum(1 for v in self.video_memory.values() if v.commented)

        return {
            'total_videos': total,
            'commented': commented,
            'uncommented': total - commented,
            'interest_keywords': len(self.interests.keywords),
            'favorite_uploaders': len(self.interests.favorite_uploaders),
            'session_actions': len(self.session_history)
        }

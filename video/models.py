"""
video/models.py - 视频数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VideoInfo:
    """视频信息"""
    bvid: str
    title: str
    description: str
    uploader_mid: int
    uploader_name: str
    publish_time: Optional[datetime]
    view_count: int
    like_count: int
    coin_count: int  # 投币数
    favorite_count: int  # 收藏数
    share_count: int  # 分享数
    duration: int  # 秒
    tags: list[str]
    url: str
    aid: Optional[int] = None  # av号

    @property
    def b23_url(self) -> str:
        """B站短链"""
        return f"https://b23.tv/{self.bvid}"


@dataclass
class CommentInfo:
    """评论信息"""
    rpid: int  # 评论 ID
    oid: str  # 目标ID（视频 bvid）
    parent_rpid: int  # 父评论ID（0为根评论）
    member_uname: str  # 用户名
    member_face: str  # 用户头像
    content: str  # 评论内容
    like_count: int  # 点赞数
    reply_count: int  # 回复数
    timestamp: datetime
    location: str  # IP属地


@dataclass
class VideoSearchResult:
    """视频搜索结果"""
    bvid: str
    title: str
    uploader_name: str
    duration: str  # 格式化时长
    publish_time: str
    view_count: int
    description: str
    url: str

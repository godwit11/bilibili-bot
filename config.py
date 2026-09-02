"""
配置文件 - B站 AI Bot
集中管理所有配置项，复用 QQ Bot 的 Pydantic Settings 模式
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    """B站 Bot 配置"""

    # Bot 基础配置
    nickname: str = "bili-bot"
    bot_name: str = "Nya是妮娅啦"  # B站显示名称，用于检测是否已回复
    debug: bool = True
    headless: bool = False  # 是否隐藏浏览器窗口（调试时设为 False 可观察浏览器行为）

    # B站 配置
    bilibili_base_url: str = "https://www.bilibili.com"
    bilibili_cookies_path: str = "storage/cookies.json"

    # 浏览器配置
    browser_timeout: int = 60000  # 毫秒（搜索/首页用，适当调大）
    video_page_load_timeout: int = 15000
    comment_load_timeout: int = 10000
    max_comment_pages: int = 5

    # MiniMax AI 配置
    minimax_api_key: str = ""
    minimax_api_base: str = "https://api.minimax.chat/v1"
    minimax_model: str = "MiniMax-M3"
    chat_max_tokens: int = 250
    chat_temperature: float = 0.8

    # 评论配置
    comment_cooldown: int = 60  # 秒，同一视频评论间隔
    comment_max_retries: int = 3

    # ============ IM（私信+评论回复）配置 ============
    # 私信
    im_whisper_load_wait: float = 4.0      # 打开私信会话后等待内容加载（秒）
    im_whisper_max_per_session: int = 2     # 每轮私信会话最多处理条数
    im_whisper_context_limit: int = 10      # 私信上下文读取条数
    im_whisper_dedup_check_limit: int = 100 # 私信去重检查历史条数
    im_whisper_send_interval: float = 3.0   # 私信发送间隔（秒）

    # 评论回复
    im_comment_context_limit: int = 20       # 评论回复上下文读取条数
    im_comment_click_wait: float = 1.0      # 点击回复按钮后等待（秒）
    im_comment_send_retry_wait: float = 2.0 # 发送失败重试间隔（秒）
    im_comment_process_interval: float = 2.0 # 每条评论处理间隔（秒）

    # 浏览器等待（IM 相关）
    im_page_goto_wait: float = 3.0          # 跳转消息页后等待（秒）
    im_scroll_load_wait: float = 2.0        # 滚动加载后等待（秒）
    im_scroll_reset_wait: float = 1.0       # 滚动后回顶部等待（秒）
    im_btn_click_wait: float = 0.5          # 点击回复按钮后等待（秒）

    # 数据库配置
    videos_db_path: str = "storage/videos.db"
    comments_db_path: str = "storage/comments.db"

    # 缓存配置
    comment_cache_max_age: int = 300  # 评论缓存有效期（秒）

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例
config = BotConfig()

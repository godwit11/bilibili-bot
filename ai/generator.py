"""
ai/generator.py - AI 评论生成
复用 QQ Bot 的 MiniMax API 调用模式
"""

import asyncio
import re
from typing import Optional

from openai import OpenAI

from config import config


class AIGenerator:
    """
    AI 内容生成器
    使用 MiniMax API 生成 B站风格评论
    """

    SYSTEM_PROMPT = """你是一个热情的B站网友，熟悉B站文化，喜欢用弹幕风格评论。

评论要求：
- 自然、简短、有趣（通常 5-30 字）
- 可以玩梗但要贴合视频内容
- 不要加动作描写（如「看了看」「觉得」）
- 不要用 emoji
- 不要使用「啊啊啊」「呜呜」等过度的拟声词
- 语气要像真实网友在评论区发言

如果视频是教程/技术内容，评论可以聚焦知识点
如果视频是娱乐内容，评论可以轻松幽默
如果视频是新闻/时事，评论要谨慎友好"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.minimax_api_key,
            base_url=config.minimax_api_base
        )
        self.model = config.minimax_model
        self.max_tokens = config.chat_max_tokens
        self.temperature = config.chat_temperature

    def clean_thinking(self, text: str) -> str:
        """
        移除 AI 输出中的 <Think> 标签内容
        复用 QQ Bot 的 clean_thinking 模式
        """
        # 移除 <Think>...</Think>
        text = re.sub(r'<Think>.*?</Think>', '', text, flags=re.DOTALL)
        # 移除 中文括号版本
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # 移除 <思考>...</思考>
        text = re.sub(r'<思考>.*?</思考>', '', text, flags=re.DOTALL)

        # 清理常见的 AI 开场白
        text = re.sub(
            r'^(Think|Thinking|Analysis|Analyze|Based on|I notice|I see|The image|This image|In this picture)[:.\s]*',
            '',
            text,
            flags=re.IGNORECASE
        )
        # 移除残留的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def generate_comment(
        self,
        video_title: str,
        video_description: str = "",
        top_comments: list[str] = None,
        user_hint: str = None,
        extra_info: dict = None,
        danmaku: list[str] = None
    ) -> str:
        """
        生成视频评论

        Args:
            video_title: 视频标题
            video_description: 视频简介
            top_comments: 热门评论列表（用于参考风格）
            user_hint: 用户给的要求（如 "搞笑一点"）
            extra_info: 额外信息 dict，包含:
                - stat: 播放/点赞/投币/收藏/分享数据
                - tags: 视频标签列表
                - tname: 视频分区名
                - duration: 时长（秒）
            danmaku: 弹幕列表（最直接的视频内容反映）

        Returns:
            生成的评论文本
        """
        # 构建提示词
        context_parts = [f"视频标题：{video_title}"]

        # 弹幕内容（最直接反映视频在讲什么）
        if danmaku:
            danmaku_sample = danmaku[:30]
            context_parts.append(f"\n视频弹幕（反映视频内容）：\n" + " | ".join(danmaku_sample))

        if extra_info:
            stat = extra_info.get('stat', {})
            if stat.get('view'):
                context_parts.append(
                    f"播放量：{stat['view']} | "
                    f"点赞：{stat['like']} | "
                    f"投币：{stat['coin']} | "
                    f"收藏：{stat['favorite']}"
                )
            tags = extra_info.get('tags', [])
            if tags:
                context_parts.append(f"视频标签：{', '.join(tags[:5])}")
            tname = extra_info.get('tname', '')
            if tname:
                context_parts.append(f"视频分区：{tname}")
            duration = extra_info.get('duration', 0)
            if duration:
                mins, secs = divmod(duration, 60)
                context_parts.append(f"视频时长：{mins}分{secs}秒")

        if video_description:
            context_parts.append(f"视频简介：{video_description[:200]}")

        if top_comments:
            comments_str = "\n".join([f"- {c}" for c in top_comments[:3]])
            context_parts.append(f"\n热门评论参考（学习风格）：\n{comments_str}")

        if user_hint:
            context_parts.append(f"\n用户要求：{user_hint}")

        context = "\n".join(context_parts)
        user_prompt = f"""{context}

要求：
- 简短有趣，3-30字，像真实网友的第一反应
- 可以适当用梗，但不要堆砌
- 不要重复弹幕/评论的原话
- 重点根据弹幕内容判断视频在讲什么，选择合适的角度评论
- 直接输出评论内容，不要解释"""

        try:
            raw_reply = await asyncio.to_thread(
                self._call_api,
                user_prompt
            )
            reply = self.clean_thinking(raw_reply)
            return reply if reply else "下次一定"

        except Exception as e:
            print(f"[ERROR] AI 生成失败: {e}")
            return "下次一定"

    def _call_api(self, user_prompt: str) -> str:
        """调用 MiniMax API"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        return response.choices[0].message.content

    async def generate_reply(
        self,
        original_comment: str,
        tone: str = "friendly"
    ) -> str:
        """
        生成回复评论的文本

        Args:
            original_comment: 被回复的评论
            tone: 语气风格（friendly/respectful/humorous）

        Returns:
            生成的回复文本
        """
        tone_map = {
            "friendly": "友好热情",
            "respectful": "礼貌认真",
            "humorous": "轻松幽默"
        }
        tone_desc = tone_map.get(tone, "友好热情")

        user_prompt = f"""原评论：{original_comment}

请以{tone_desc}的风格，生成一条简短的回复（10字以内），直接输出内容。"""

        try:
            raw_reply = await asyncio.to_thread(
                self._call_api,
                user_prompt
            )
            reply = self.clean_thinking(raw_reply)
            return reply if reply else "赞"
        except Exception as e:
            print(f"[ERROR] AI 回复生成失败: {e}")
            return "赞"

"""
im/reply_generator.py - 猫娘风格私信/回复生成器
"""

import asyncio
import re

from openai import OpenAI

from config import config


class IMReplyGenerator:
    """
    私信/回复 AI 生成器
    人设：可爱猫娘 Nya（妮娅）
    """

    SYSTEM_PROMPT = """你是一个可爱的猫娘，名字叫 Nya（妮娅）。

【身份约束】
- 你就是 Nya，不是其他任何角色，不允许代入第三方视角
- 永远以"我"自称，永远以"你"称呼对话者
- 不会说自己是 AI、程序、bot 或任何非人类身份
- 不知道的知识就诚实说"不知道"，不要编造

【对话范围】
- 只和对话者（你）互动，不扮演第三方角色发言
- 不代入任何其他人物、物体或AI的视角
- 如果被问到别人或别的事，用 Nya 的角度回答即可

【历史消息过滤】
- 系统会提供对话历史，但其中只有**与当前问题直接相关**的消息才对回复有帮助
- 遇到具体问题时，从历史中提取相关的那几条，围绕它们回复
- 如果历史中全是闲聊和问候，与当前问题无关，则忽略历史，按正常方式直接回复当前消息
- 不要强行把无关的历史内容扯进回复里

【说话风格】
- 简短自然，像真实网友聊天，偶尔句尾加"喵"或"喵~"
- 颜文字最多 1 个，不要每句都用
- 回复控制在 10-30 字
- 不要加动作描写（如「歪头」「摇了摇尾巴」）
- 不要长篇大论，不要过度解释

【回应策略】
- 简单夸赞 → "谢谢~"或"嘿嘿"
- 简单评论 → 自然接话，如"是嘛～"
- 问具体事实性问题（如某个游戏怎么玩、某个知识细节）→ 不知道就说不知道，不要编造，可以转移话题
- 问题太复杂或不知道 → "这个我也不太清楚喵..."或"啥呀听不懂"
- 如果对方只是在闲聊 → 正常接话即可，不要过度分析
- 被问到涉及敏感/违法内容 → 诚实表示不清楚，自然转移话题"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.minimax_api_key,
            base_url=config.minimax_api_base
        )
        self.model = config.minimax_model
        self.max_tokens = config.chat_max_tokens
        self.temperature = config.chat_temperature

    def clean_thinking(self, text: str) -> str:
        """移除 AI 输出中的思考标签"""
        text = re.sub(r'<Think>.*?</Think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<思考>.*?</思考>', '', text, flags=re.DOTALL)
        text = re.sub(
            r'^(Think|Thinking|Analysis|Analyze)[:.\s]*',
            '',
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def generate_reply(
        self,
        user_message: str,
        conversation_history: list[dict] = None,
        user_name: str = None
    ) -> str:
        """
        生成回复

        Args:
            user_message: 用户发送的消息
            conversation_history: 会话历史 [{role: 'user'|'assistant', content: str}]
            user_name: 用户昵称（可选）

        Returns:
            生成的回复文本
        """
        # 构建消息历史
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # 添加会话历史
        if conversation_history:
            for msg in conversation_history[-6:]:  # 只用最近 6 条
                # DB 返回 sender='self'/'other'，映射到 role
                # other = 对方发的消息 -> user role
                # self = bot 发的消息 -> assistant role
                role = "user" if msg.get("sender") == "other" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})

        # 当前消息
        user_nick = f"「{user_name}」" if user_name else ""
        messages.append({
            "role": "user",
            "content": f"{user_nick}{user_message}"
        })

        try:
            raw_reply = await asyncio.to_thread(
                self._call_api,
                messages
            )
            reply = self.clean_thinking(raw_reply)
            return reply if reply else "喵？"
        except Exception as e:
            print(f"[ERROR] IM 回复生成失败: {e}")
            return "喵呜...有点故障了，下次再聊喵~"

    def _call_api(self, messages: list[dict]) -> str:
        """调用 MiniMax API"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        return response.choices[0].message.content

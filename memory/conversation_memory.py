"""对话历史记忆 + 持久化。

做得简单但够用: 滚动窗口保留近 N 条原始消息, 旧的做摘要压缩, 整体落到
results/ 下的 jsonl, 下次同数据集可续聊。这部分坐实简历"记忆管理"。
"""
import json
import os
from datetime import datetime


class ConversationMemory:
    def __init__(self, keep_recent: int = 6, store_path: str | None = None):
        self.keep_recent = keep_recent
        self.store_path = store_path
        self._messages: list[dict] = []
        self._summary: str = ""

    @staticmethod
    def _to_text(content) -> str:
        """AutoGen 的 message.content 有时是 str, 有时是 list (工具调用结果/事件流)。
        统一拍平成 str 再压缩/持久化, 避免类型不齐炸掉。"""
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False, default=str)
        except Exception:
            return str(content)

    def add(self, role: str, content, usage: dict | None = None) -> None:
        """记录一条消息。

        Args:
            role: 发言者 (Analyst/Coder/Reviewer/Reporter/user)
            content: 消息内容, 可能是 str 或 list (AutoGen 的工具调用事件流)
            usage: 该消息的 token 消耗 {prompt_tokens, completion_tokens}, 可选
        """
        text = self._to_text(content)
        self._messages.append({"role": role, "content": text,
                               "ts": datetime.now().isoformat(),
                               "usage": usage})
        self._maybe_compress()

    def _maybe_compress(self) -> None:
        if len(self._messages) <= self.keep_recent * 2:
            return
        dropped = self._messages[: -self.keep_recent]
        compact = " ".join(m["content"][:160] for m in dropped)
        self._summary = (self._summary + " | " + compact).strip(" |")
        self._messages = self._messages[-self.keep_recent:]

    def context(self) -> str:
        head = f"[历史摘要] {self._summary}\n" if self._summary else ""
        return head + "\n".join(f"{m['role']}: {m['content']}" for m in self._messages)

    def save(self) -> None:
        if not self.store_path:
            return
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"summary": self._summary,
                                "messages": self._messages}, ensure_ascii=False) + "\n")

    def load(self) -> str:
        """读取上次会话的摘要, 用于续聊注入。

        save() 是 append 模式 (每次会话 = 1 行 jsonl), 所以读最后一行即可。
        返回上次会话的 summary 字符串; 没有历史则返回空串。
        """
        if not self.store_path or not os.path.exists(self.store_path):
            return ""
        with open(self.store_path, encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            return ""
        last = json.loads(lines[-1])
        return last.get("summary", "")

    def context_for_continuation(self) -> str:
        """返回可拼到 task 前面的续聊上下文。

        如果有历史摘要, 返回 "[上次分析摘要] {summary}";
        没有则返回空串 (首次分析, 不注入)。
        """
        summary = self.load()
        if not summary:
            return ""
        # 截断, 避免历史摘要太长反而吃 token
        return f"[上次分析摘要] {summary[:600]}\n"
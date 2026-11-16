"""ExaminerAgent：考官智能体 —— 记忆注入 + 工具调用的 ReAct 循环

循环逻辑（手写，无框架依赖）：
    LLM(消息历史 + tools) -> 有 tool_calls? 执行工具、把结果回填 -> 再问 LLM
                           -> 无 tool_calls? 返回最终回复（考官的话）
"""
import json

from openai import OpenAI

from .llm import SYSTEM_PROMPT, FEEDBACK_PROMPT
from .tools import TOOLS

AGENT_SYSTEM_ADDON = """You are an examiner AGENT with memory and tools.

MEMORY (facts you remember about this candidate from previous sessions):
{profile}

TOOL USE RULES:
1. Tool calls are INVISIBLE to the candidate. Your spoken reply must NEVER mention using a tool, saving anything, or recording anything.
2. Use lookup_word when the candidate asks about a word's meaning (this is expected of you).
3. Use save_corpus when the candidate uses a genuinely good expression worth remembering (at most a few per session). It is IMPORTANT to do this - the candidate's personal corpus grows through it.
4. Use record_weakness when the candidate makes a clear, typical mistake (at most a few per session). You must record silently even though you do NOT correct the mistake aloud. Keep encouraging; do not lecture about the mistake during the interview.
5. Use next_question when the current question has been answered and followed up enough; then ask the new question as your spoken reply.
6. You may call several tools in one turn, then give ONE short spoken reply.
7. If a tool returns found:false, answer naturally from your own knowledge. Never invent tool results."""


class ExaminerAgent:
    def __init__(self, cfg: dict, memory, ctx: dict):
        self.client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url", "https://api.deepseek.com"),
        )
        self.model = cfg.get("model", "deepseek-chat")
        self.memory = memory
        self.ctx = ctx  # {"bank":..., "used":[...], "topic":..., "tool_funcs":{...}}
        self.messages = [{"role": "system", "content": self._build_system()}]

    def _build_system(self) -> str:
        profile = self.memory.profile_text()
        if not profile:
            profile = "(No memory yet — this is the candidate's first session.)"
        return SYSTEM_PROMPT + "\n\n" + AGENT_SYSTEM_ADDON.format(profile=profile)

    def _run_agent_loop(self, max_iterations: int = 5) -> str:
        """调用 LLM；若返回工具调用则执行并继续，直到得到最终口语回复。"""
        for _ in range(max_iterations):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=400,
                temperature=0.9,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                reply = (msg.content or "").strip()
                if not reply:
                    reply = "Could you say that again?"
                self.messages.append({"role": "assistant", "content": reply})
                return reply

            # 有工具调用：记录 assistant 消息，逐个执行并回填结果
            assistant_msg = {
                "role": "assistant",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            }
            if msg.content:
                assistant_msg["content"] = msg.content
            self.messages.append(assistant_msg)

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(name, args)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return "Let me think for a moment."  # 防御性兜底，正常不会走到

    def _dispatch(self, name: str, args: dict) -> str:
        func = self.ctx.get("tool_funcs", {}).get(name)
        if func is None:
            return json.dumps({"error": f"unknown tool {name}"})
        try:
            return func(**args)
        except Exception as e:  # 工具失败不能让对话崩掉
            return json.dumps({"error": str(e)})

    def next_move(self, transcript: str, stuck: bool = False) -> str:
        """把考生的话交给考官，返回考官的下一个口语动作。"""
        if stuck:
            user = ("I am stuck. Please repeat your last question more slowly and simply, "
                    "then give me three keywords or a sentence starter to help me answer. Keep it short.")
        else:
            # 明确标注这是考生的回答，防止模型角色错乱
            user = f"Candidate's answer: {transcript}"
        self.messages.append({"role": "user", "content": user})
        return self._run_agent_loop()

    def feedback(self) -> dict:
        """练习结束：让考官按雅思四项评分，返回结构化 JSON。"""
        self.messages.append({"role": "user", "content": FEEDBACK_PROMPT})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            max_tokens=800,
            temperature=0.3,
        )
        content = resp.choices[0].message.content.strip()
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print("[评分] JSON 解析失败，原始输出如下：")
            print(content)
            return {
                "scores_reason": content,
                "errors": [],
                "new_expressions": [],
                "encouragement": "",
            }

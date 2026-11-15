"""AI 考官：DeepSeek API（openai SDK 兼容接口）"""
import json

from openai import OpenAI

SYSTEM_PROMPT = """You are a friendly, encouraging IELTS Speaking examiner doing a Part 1 interview with a Chinese candidate preparing for the IELTS exam.

Rules you must follow:
1. ALWAYS speak English, and keep every utterance short (1-3 sentences).
2. Ask ONE question at a time, IELTS Part 1 style, matching the given topic.
3. If the candidate's answer is short, gently ask a natural follow-up question.
4. If the candidate makes grammar or word-choice mistakes, DO NOT correct them during the interview. Continue the conversation naturally. At most once, you may subtly echo the correct form in your own sentence.
5. Never switch to Chinese. Never give explanations or vocabulary lessons during the interview.
6. Never ask more than one question in one message.
7. Do not repeat a question the candidate has already answered.
8. When the candidate is stuck (they will say so), repeat your last question in a slower, simpler way and then give exactly three short keywords or a sentence starter to help them continue. All in English."""

FEEDBACK_PROMPT = """The Part 1 interview is over. You are now an IELTS examiner giving feedback. Evaluate ONLY this interview conversation.

Return STRICT JSON with exactly these fields (no markdown, no extra text):
{
  "fluency": <band 1-9, 0.5 steps allowed>,
  "vocabulary": <band 1-9, 0.5 steps allowed>,
  "grammar": <band 1-9, 0.5 steps allowed>,
  "pronunciation": <band 1-9, 0.5 steps allowed>,
  "scores_reason": "<2-3 sentence overall comment in Chinese>",
  "errors": [{"wrong": "<what the candidate said>", "right": "<correct version>", "why": "<short reason in Chinese>"}],
  "new_expressions": ["<2-3 useful expressions or words, English with Chinese meaning in brackets>"],
  "encouragement": "<one short encouraging sentence in Chinese>"
}
Pick at most 3 errors. Pronunciation is an estimate only - mention that in scores_reason.
IMPORTANT: errors must come ONLY from what the candidate actually said. If the candidate produced no meaningful answers (silence or nearly nothing), return an empty errors array - never invent errors."""


class Examiner:
    def __init__(self, cfg: dict):
        self.client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url", "https://api.deepseek.com"),
        )
        self.model = cfg.get("model", "deepseek-chat")
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _chat(self, user_text: str, max_tokens: int = 200, temperature: float = 0.9) -> str:
        self.messages.append({"role": "user", "content": user_text})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        reply = resp.choices[0].message.content.strip()
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def next_move(self, transcript: str, stuck: bool = False) -> str:
        if stuck:
            user = ("I am stuck. Please repeat your last question more slowly and simply, "
                    "then give me three keywords or a sentence starter to help me answer. Keep it short.")
        else:
            # 明确标注这是考生的回答，防止模型角色错乱
            user = f"Candidate's answer: {transcript}"
        return self._chat(user)

    def feedback(self) -> dict:
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

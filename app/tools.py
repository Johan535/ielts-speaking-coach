"""考官的工具箱：DeepSeek function-calling 的工具定义与实现

工具对考生完全隐形：考官静默调用、回复中绝不提及。
"""
import json
import urllib.parse
import urllib.request

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_word",
            "description": "Look up an English word or phrase the candidate asked about. "
                           "Returns definition, phonetic and an example. "
                           "Call ONLY when the candidate explicitly asks what a word means.",
            "parameters": {
                "type": "object",
                "properties": {
                    "word": {"type": "string",
                             "description": "The word or phrase to look up (base form)"},
                },
                "required": ["word"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_corpus",
            "description": "Silently save a good expression the candidate just used into their "
                           "personal corpus for later review. Do NOT mention this in your spoken reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string",
                                   "description": "The exact expression, at most 6 words"},
                    "translation": {"type": "string",
                                    "description": "Short Chinese meaning"},
                },
                "required": ["expression", "translation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_weakness",
            "description": "Silently record a clear mistake the candidate made, as "
                           "'wrong form -> correct form'. Do NOT mention this in your spoken reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string",
                             "description": "Mistake summary, e.g. 'I very like -> I really like'"},
                    "category": {"type": "string",
                                 "enum": ["grammar", "vocabulary", "fluency", "pronunciation"]},
                },
                "required": ["text", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "next_question",
            "description": "Fetch the next interview question from the local question bank "
                           "for the current topic. Call this when the current question has been "
                           "answered and followed up enough, then ask the new question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The current topic name"},
                },
                "required": ["topic"],
            },
        },
    },
]


def _lookup_word(word: str) -> str:
    """dictionaryapi.dev 免费词典；失败时返回 found:false，让模型自己解释。"""
    url = "https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return json.dumps({"found": False})
    try:
        entry = data[0]
        meaning = entry["meanings"][0]
        return json.dumps({
            "found": True,
            "word": entry.get("word", word),
            "phonetic": entry.get("phonetic", ""),
            "pos": meaning.get("partOfSpeech", ""),
            "definition": meaning["definitions"][0].get("definition", ""),
            "example": meaning["definitions"][0].get("example", ""),
        })
    except (KeyError, IndexError):
        return json.dumps({"found": False})


def build_tool_funcs(ctx: dict) -> dict:
    """把工具实现绑定到共享上下文（记忆、题库、当前话题、已用题目）。

    ctx 需要：memory(AgentMemory), bank(QuestionBank), used(list), topic(str)
    """
    memory = ctx["memory"]
    bank = ctx["bank"]

    def lookup_word(word: str) -> str:
        return _lookup_word(word.strip().lower())

    def save_corpus(expression: str, translation: str) -> str:
        memory.save_corpus(expression.strip(), translation.strip(), source="dialogue")
        return json.dumps({"saved": True})

    def record_weakness(text: str, category: str) -> str:
        memory.record_weakness(text.strip(), category, ctx.get("topic", ""))
        return json.dumps({"recorded": True})

    def next_question(topic: str) -> str:
        q = bank.next_question(topic, exclude=ctx.get("used", []))
        if q is None:
            return json.dumps({"error": f"topic '{topic}' not found"})
        ctx["used"].append(q)
        return json.dumps({"question": q})

    return {
        "lookup_word": lookup_word,
        "save_corpus": save_corpus,
        "record_weakness": record_weakness,
        "next_question": next_question,
    }

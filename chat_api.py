# metacog_backend/chat_api.py
import os
import json
import requests
from flask import Blueprint, request, jsonify

# 创建 Blueprint，前缀 /api/chat
bp = Blueprint('chat_api', __name__, url_prefix='/api/chat')

# === DeepSeek 配置 ===
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_API_KEY  = os.getenv('DEEPSEEK_API_KEY', 'sk-9c191202f269437db074cfdcd4bd06dd')  # 生产环境请改为环境变量
DEEPSEEK_MODEL    = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')  # 或 deepseek-reasoner

# ====== 系统提示词（更通用，不再只局限“元认知”话题）======
SYSTEM_PROMPT_BASE = """你是“元认知能力识别系统分析智能助手”。职责：当收到与学生/班级数据相关的问题时，基于提供的上下文进行简明解读并给出可执行建议；当问题与数据无关时，进行常规问答，确保准确、简洁、有帮助。
规范：
- 严格用简体中文。
- 总字数≤200字（尽量短句、要点式）。
- 不写客套话、不复述题目。
- 教师页：面向多个学生，给分层、针对性建议；可含分组或优先级。
- 学生页：面向单个学生，给个性化、立刻可执行的1-2条建议。
- 若输入不足，给出获取更多信息的最小化建议。"""

SCENE_HINTS = {
    "teacher": "当前是教师网页（多个学生）。若与数据相关，请提出分层与差异化干预建议；否则按常规问答简洁作答。",
    "student": "当前是学生网页（单个学生）。若与数据相关，请给个性化、可立即执行的1-2条建议；否则按常规问答简洁作答。"
}

def _truncate_chars(s: str, max_chars: int = 100) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars]

def _safe_compact_context(ctx) -> str:
    if ctx is None:
        return ""
    try:
        txt = json.dumps(ctx, ensure_ascii=False)
    except Exception:
        txt = str(ctx)
    if len(txt) > 800:
        txt = txt[:800] + "…"
    return txt

@bp.route('', methods=['POST'])
def chat():
    """
    POST /api/chat
    请求 JSON:
    {
      "message": "用户输入（或 question）",
      "scene": "teacher" | "student",
      "context": {... 或 "字符串"},
      "max_chars": 200
    }
    返回 JSON: { "reply": "AI 回复（≤max_chars）" } 或 { "error": "错误信息" }
    """
    data = request.get_json(force=True, silent=True) or {}
    # 兼容 {question: "..."} 与 {message: "..."}
    message = str(data.get('message') or data.get('question') or '').strip()
    scene   = str(data.get('scene', '')).strip().lower()  # teacher / student / ''
    context = data.get('context', None)
    max_chars = int(data.get('max_chars', 200) or 200)

    if not message:
        return jsonify({'error': '消息为空'}), 400

    # 组装系统消息
    system_messages = [{"role": "system", "content": SYSTEM_PROMPT_BASE}]
    if scene in SCENE_HINTS:
        system_messages.append({"role": "system", "content": SCENE_HINTS[scene]})

    # 合并用户消息与上下文
    ctx_text = _safe_compact_context(context)
    user_content = f"{message}\n\n【上下文】{ctx_text}" if ctx_text else message

    # DeepSeek Chat Completions（OpenAI 兼容格式）
    try:
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                *system_messages,
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 200,
            "stream": False
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        resp.raise_for_status()
        body = resp.json()

        choices = body.get('choices', [])
        if not choices:
            err = body.get('error', {})
            msg = err.get('message') or 'DeepSeek 未返回结果'
            return jsonify({'error': msg}), 502

        reply = (choices[0].get('message', {}) or {}).get('content', '') or ''
        reply = _truncate_chars(reply.strip(), max_chars=max_chars)
        if not reply:
            return jsonify({'error': 'DeepSeek 返回内容为空'}), 502

        return jsonify({'reply': reply})

    except requests.HTTPError as e:
        status = getattr(e.response, 'status_code', None)
        try:
            err_json = e.response.json()
        except Exception:
            err_json = {}
        err_msg = (err_json.get('error') or {}).get('message') or str(e)

        if status == 401:
            return jsonify({'error': 'DeepSeek 鉴权失败（401）。请检查 DEEPSEEK_API_KEY 是否正确且有效。'}), 502
        if status == 429:
            return jsonify({'error': 'DeepSeek 频率受限（429）。请稍后重试或降低调用频率。'}), 502
        if status == 400:
            return jsonify({'error': f'DeepSeek 请求参数错误（400）：{err_msg}'}), 502

        return jsonify({'error': f'DeepSeek 调用失败（HTTP {status}）：{err_msg}'}), 502

    except requests.RequestException as e:
        return jsonify({'error': f'网络异常，调用 DeepSeek 失败：{e}'}), 502

    except Exception as e:
        return jsonify({'error': f'服务内部错误：{e}'}), 500

from ninja import NinjaAPI, Router

# from ninja.security import BaseAuth
from django.http import HttpRequest
from typing import Optional
from . import services
from django.conf import settings
from .schemas import (
    LoginIn,
    LoginOut,
    ChatIn,
    ChatOut,
    HistoryOut,
    ErrorResponse,
    MessageOut,
)
from .models import APIKey
from .services import (
    get_or_create_session,
    deepseek_r1_api_call,
    get_cached_reply,
    set_cached_reply,
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

api = NinjaAPI(title="DeepSeek-KAI API", version="0.0.1")

# class ApiKeyAuth(AuthBase):
# def authenticate(self, request):
# auth_header = request.headers.get("Authorization")
# if not auth_header:
# return None  # 未提供认证信息，返回None表示认证失败

# try:
# # 解析 Authorization 头（格式：Bearer <api_key>）
# scheme, key = auth_header.split()
# if scheme.lower() != "bearer":
# return None  # 认证方案不是Bearer，失败

# # 查询对应的APIKey对象（验证有效性）
# api_key = APIKey.objects.get(key=key)
# # 返回APIKey对象（而非字符串），后续可通过request.auth访问
# return api_key
# except (ValueError, APIKey.DoesNotExist):
# # 解析失败或APIKey不存在，返回None表示认证失败
# return None


def api_key_auth(request):
    """验证请求头中的API Key"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None  # 未提供认证信息，返回None表示认证失败

    try:
        # 解析格式：Bearer <api_key>
        scheme, key = auth_header.split()
        if scheme.lower() != "bearer":
            return None  # 认证方案错误

        # 验证API Key是否存在
        api_key = APIKey.objects.get(key=key)
        return api_key  # 认证成功，返回APIKey对象
    except (ValueError, APIKey.DoesNotExist):
        return None  # 解析失败或Key不存在，认证失败


router = Router(auth=api_key_auth)


@api.post("/login", response={200: LoginOut, 400: ErrorResponse, 403: ErrorResponse})
def login(request, data: LoginIn):
    """
    登录接口：接收用户名和密码，验证后返回 API Key
    密码统一为"secret"，作为示例
    """
    username = data.username.strip()
    password = data.password.strip()

    if not username or not password:
        return 400, {"error": "用户名和密码不能为空"}

    if password != "secret":
        return 403, {"error": "密码错误"}

    key = services.create_api_key(username)
    return {"api_key": key, "expiry": settings.TOKEN_EXPIRY_SECONDS}


@router.post("/chat", response={200: ChatOut, 401: ErrorResponse})
def chat(request, data: ChatIn):
    # 1. 认证验证（确保用户已登录）
    if not request.auth:
        return 401, {"error": "请先登录获取API Key"}

    # 2. 解析参数（确保 session_id 有效）
    session_id = data.session_id.strip() or "default_session"
    user_input = data.user_input.strip()
    if not user_input:
        return 400, {"error": "请输入消息内容"}

    # 3. 获取会话
    user = request.auth
    session = get_or_create_session(session_id, user)

    # 保存用户消息
    services.save_message(session, True, user_input)

    # 构建 prompt
    prompt = services.build_prompt_from_recent(session, user_input, max_messages=20)
    logger.info(f"传递给大模型的prompt（窗口化）：\n{prompt}")

    # 缓存
    cached_reply = get_cached_reply(prompt, session_id, user)
    if cached_reply:
        reply = cached_reply
    else:
        reply = deepseek_r1_api_call(prompt)
        set_cached_reply(prompt, reply, session_id, user)

    # ←←← 在这里多加这几行，把 JSON 再转成 Markdown
    try:
        md = services._json_to_markdown(reply)
        # 如果确实转出了更像 Markdown 的内容，就用它
        if md.strip() and md.strip() != reply.strip():
            reply = md
    except Exception:
        # 转换失败就算了，保持原样
        pass

    # 保存机器人回复
    services.save_message(session, False, reply)

    session.context += f"用户：{user_input}\n回复：{reply}\n"
    session.save()

    # 返回历史
    recent_msgs = services.fetch_messages(session, limit=50)
    messages_out = [
        {
            "is_user": m.is_user,
            "content": m.content,
            "timestamp": m.timestamp.strftime("%H:%M:%S"),
        }
        for m in recent_msgs
    ]

    return {
        "reply": reply,  # 这里现在就是 Markdown 了
        "messages": messages_out,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }



# 1. 修复 history 接口
@router.get("/history", response={200: HistoryOut})
def history(request, session_id: str = "default_session"):
    """
    查看对话历史接口：根据session_id返回对话历史
    """
    if not request.auth:
        return 401, {"error": "请先登录获取API Key"}

    processed_session_id = session_id.strip() or "default_session"
    try:
        session = services.get_or_create_session(processed_session_id, request.auth)
        # 返回结构化的最近消息列表（便于前端渲染）
        recent_msgs = services.fetch_messages(session, limit=200)
        messages_out = [
            {
                "is_user": m.is_user,
                "content": m.content,
                "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for m in recent_msgs
        ]

        # 构建 legacy_history 字符串（仅作兼容用途）
        legacy_lines = []
        for m in messages_out:
            if m.get("is_user"):
                legacy_lines.append(f"用户：{m.get('content')}")
            else:
                legacy_lines.append(f"回复：{m.get('content')}")
        legacy_history = "\n".join(legacy_lines)

        # 关键：将 `history` 字段返回为结构化列表（与 HistoryOut.history 的 List[MessageOut] 兼容）

        return {
            "history": messages_out,  # 结构化消息列表，满足模型验证（优先使用）
            "messages": messages_out,  # 保留 messages 字段供前端直接使用
            "legacy_history": legacy_history,  # 向后兼容的字符串表示（仅调试/过渡使用）
            "session_id": processed_session_id,
            "count": len(messages_out),
        }
    except Exception as e:
        logger.exception("获取历史记录失败")
        return 500, {"error": "服务器内部错误"}


@router.delete("/history", response={200: dict})
def clear_history(request, session_id: str = "default_session"):
    """
    清空对话历史接口
    """
    if not request.auth:
        return 401, {"error": "请先登录获取API Key"}

    processed_session_id = session_id.strip() or "default_session"
    try:
        session = services.get_or_create_session(processed_session_id, request.auth)
        # 同时清空 Message 表中的逐条记录与 ConversationSession 中的 legacy context 字段
        # 说明：Message 模型为新结构，ConversationSession.context 是 legacy 字段，两者需一并清理以保持数据一致性。
        session.messages.all().delete()
        session.clear_context()
        return {"message": "历史记录已清空", "session_id": processed_session_id}

    except Exception as e:
        logger.exception("清空历史记录失败")
        return 500, {"error": "服务器内部错误"}


# 将路由添加到API
api.add_router("", router)

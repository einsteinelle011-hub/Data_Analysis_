from ninja import Schema
from typing import Optional, List


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    api_key: str
    expiry: int


class ChatIn(Schema):
    session_id: str = "default_session"
    user_input: str


class ChatOut(Schema):
    reply: str
    # 使用结构化MessageOut列表返回给前端recent Message
    messages: Optional[List["MessageOut"]] = None


class MessageOut(Schema):
    is_user: bool
    content: str
    timestamp: str


class HistoryOut(Schema):
    # 后端会同时兼容两种历史格式：
    # messages: 结构化的 MessageOut 列表（推荐，新格式）
    # history: 兼容 legacy 的字符串（按行解析，旧格式）
    messages: Optional[List[MessageOut]] = None
    # 现在后端会把 `history` 用作结构化消息列表
    history: Optional[List[MessageOut]] = None
    # legacy_history 保留老的按行字符串格式，便于旧客户端或调试使用
    legacy_history: Optional[str] = None
    session_id: Optional[str] = None
    count: Optional[int] = None


class ErrorResponse(Schema):
    error: str

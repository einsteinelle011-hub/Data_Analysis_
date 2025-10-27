import time
import threading
from typing import Dict, Any, Optional, List
from django.core.cache import cache
import hashlib
from .models import APIKey, RateLimit, ConversationSession, Message
from django.conf import settings
from .prompt_engineering import generate_analysis_prompt


# 全局配置
# API_KEY_LENGTH = 32
# TOKEN_EXPIRY_SECONDS = 3600
# RATE_LIMIT_MAX = 5  # 每分钟最大请求数
# RATE_LIMIT_INTERVAL = 60

# 线程锁用于速率限制
rate_lock = threading.Lock()


# def deepseek_r1_api_call(prompt: str) -> str:
#     """模拟 DeepSeek-R1 API 调用函数"""
#     from topklogsystem import TopKLogSystem

#     system = TopKLogSystem(
#         log_path="./data/log", llm="deepseek-r1:7b", embedding_model="bge-large:latest"
#     )

#     query = prompt
#     result = system.query(query)
#     time.sleep(0.5)

#     print(result["response"])
#     return result["response"]

def deepseek_r1_api_call(prompt: str) -> str:
    """
    改进版：调用 DeepSeek 模型执行高智能数据分析。
    增加科学、精准的 Prompt 设计来引导模型分析。
    """
    from topklogsystem import TopKLogSystem
    import time

    # 1. 包装用户输入为科学分析 Prompt
    enriched_prompt = generate_analysis_prompt(prompt)

    # 2. 初始化大模型系统（DeepSeek）
    system = TopKLogSystem(
        log_path="./data/log", 
        llm="deepseek-r1:7b", 
        embedding_model="bge-large:latest"
    )

    # 3. 执行分析
    result = system.query(enriched_prompt)
    time.sleep(0.5)

    # 4. 打印和返回结果（结构化 JSON）
    print(" 模型分析输出：")
    print(result["response"])
    return result["response"]



def create_api_key(user: str) -> str:
    """创建 API Key 并保存到数据库"""
    key = APIKey.generate_key()
    expiry = time.time() + settings.TOKEN_EXPIRY_SECONDS

    api_key = APIKey.objects.create(key=key, user=user, expiry_time=expiry)

    # 创建对应的速率限制记录
    RateLimit.objects.create(
        api_key=api_key, reset_time=time.time() + settings.RATE_LIMIT_INTERVAL
    )

    return key


def validate_api_key(key_str: str) -> bool:
    """验证 API Key 是否存在且未过期"""
    try:
        api_key = APIKey.objects.get(key=key_str)
        if api_key.is_valid():
            return True
        else:
            api_key.delete()  # 删除过期key
            return False
    except APIKey.DoesNotExist:
        return False


def check_rate_limit(key_str: str) -> bool:
    """检查 API Key 的请求频率是否超过限制"""
    with rate_lock:
        try:
            # api_key = APIKey.objects.get(key=key_str)
            # rate_limit = RateLimit.objects.get(api_key=api_key)
            rate_limit = RateLimit.objects.select_related("api_key").get(
                api_key__key=key_str
            )

            current_time = time.time()
            if current_time > rate_limit.reset_time:
                rate_limit.count = 1
                rate_limit.reset_time = current_time + settings.RATE_LIMIT_INTERVAL
                rate_limit.save()
                return True
            elif rate_limit.count < settings.RATE_LIMIT_MAX:
                rate_limit.count += 1
                rate_limit.save()
                return True
            else:
                return False
        except RateLimit.DoesNotExist:
            # 如果速率限制记录不存在，创建一个新的
            try:
                current_time = time.time()
                api_key = APIKey.objects.get(key=key_str)
                RateLimit.objects.create(
                    api_key=api_key,
                    count=1,
                    reset_time=current_time + settings.RATE_LIMIT_INTERVAL,
                )
                return True
            except APIKey.DoesNotExist:
                return False


# def get_or_create_session(session_id: str, user: APIKey) -> ConversationSession:
# """获取或创建会话，关联当前用户（通过API Key）"""
# session, created = ConversationSession.objects.get_or_create(
# session_id=session_id,
# user=user,  # 绑定用户
# defaults={'context': ''}
# )
# return session


def get_or_create_session(session_id: str, user: APIKey) -> ConversationSession:
    """
    获取或创建用户的专属会话：
    - 若用户+session_id已存在 → 加载旧会话（保留历史）
    - 若不存在 → 创建新会话（空历史）
    """
    session, created = ConversationSession.objects.get_or_create(
        session_id=session_id,  # 匹配会话ID
        user=user,  # 匹配当前用户（关键！避免跨用户会话冲突）
        defaults={"context": ""},
    )
    # 调试日志：确认是否创建新会话（created=True 表示新会话）
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"会话 {session_id}（用户：{user.user}）{'创建新会话' if created else '加载旧会话'}"
    )
    return session


# 新增消息存储与上下文窗口化函数
# 为了支持多轮对话，我们存储每条消息到 Message 表，并提供fetch_messages/save_message/build_prompt_from_recent等辅助函数
# 这些函数被 API 层用于构建带有限窗口的 prompt，从而实现多轮上下文。


def save_message(session: ConversationSession, is_user: bool, content: str) -> None:
    """保存一条消息到 Message 表"""
    Message.objects.create(session=session, is_user=is_user, content=content)


def fetch_messages(session: ConversationSession, limit: int = 50) -> List[Message]:
    """按时间顺序获取最近的 N 条消息（旧到新）"""
    return list(session.messages.order_by("timestamp")[:limit])


def build_prompt_from_recent(
    session: ConversationSession, user_input: str, max_messages: int = 20
) -> str:
    """
    根据会话中最近的消息构建 prompt。
    - 取最近的 max_messages 条消息（按时间升序），然后追加当前用户输入。
    - 返回字符串形式的 prompt，可直接传给 deepseek_r1_api_call()
    """
    # 获取所有消息的倒序，然后取最后 max_messages 条，再逆序回去
    recent = list(session.messages.order_by("-timestamp")[:max_messages])[::-1]
    parts = []
    for m in recent:
        role = "用户" if m.is_user else "回复"
        parts.append(f"{role}：{m.content}")
    # 追加当前输入
    parts.append(f"用户：{user_input}")
    parts.append("回复：")
    prompt = "\n".join(parts)
    return prompt


def get_cached_reply(prompt: str, session_id: str, user: APIKey) -> str | None:
    """缓存键包含 session_id 和 user，避免跨会话冲突"""
    cache_key = f"reply:{user.user}:{session_id}:{hash(prompt)}"
    return cache.get(cache_key)


def set_cached_reply(
    prompt: str, reply: str, session_id: str, user: APIKey, timeout=3600
):
    cache_key = f"reply:{user.user}:{session_id}:{hash(prompt)}"
    cache.set(cache_key, reply, timeout)


def generate_cache_key(original_key: str) -> str:
    """
    生成安全的缓存键。
    对原始字符串进行哈希处理，确保键长度固定且仅包含安全字符。
    """
    # 使用SHA256哈希函数生成固定长度的键（64位十六进制字符串）
    hash_obj = hashlib.sha256(original_key.encode("utf-8"))
    return hash_obj.hexdigest()

import time
import threading
from typing import Dict, Any, Optional, List
from django.core.cache import cache
import hashlib
from .models import APIKey, RateLimit, ConversationSession, Message
from django.conf import settings
from .prompt_engineering import generate_analysis_prompt
from .rag import SimpleRAG
from pathlib import Path
import json
from .web_retriever import web_retrieve

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


# 懒加载 RAG（首次查询时才构建/加载索引）
def _extract_last_user_question(text: str) -> str:
    """从可能包含历史对话的 prompt 中抽取【最后一条用户问题】。"""
    t = (text or "").strip()
    if not t:
        return t
    # 常见标签（中英混用都兜一下）
    starts = ["用户：", "User:", "Human:", "Q:"]
    ends   = ["回复：", "Assistant:", "AI:", "A:"]
    # 优先按“用户：”反向切
    for s in starts:
        if s in t:
            tail = t.rsplit(s, 1)[-1]
            for e in ends:
                if e in tail:
                    tail = tail.split(e, 1)[0]
            return tail.strip()
    return t



_rag_instance: SimpleRAG | None = None

def _get_rag():
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = SimpleRAG(Path(settings.KB_DIR), Path(settings.INDEX_DIR))
        # 不在这里 build；由 .search 内部按需加载/构建
    return _rag_instance

def retrieve_contexts(query: str, topk: int | None = None) -> list[dict]:
    """从本地知识库检索片段；失败时返回空列表"""
    try:
        rag = _get_rag()
        k = topk or getattr(settings, "RAG_TOPK", 5)
        return rag.search(query, topk=k)
    except Exception as e:
        # 打印一下错误，但不阻塞主流程
        import logging
        logging.getLogger(__name__).warning(f"RAG 检索失败：{e}")
        return []



def deepseek_r1_api_call(prompt: str) -> str:
    """
    改进版：调用 DeepSeek 模型执行高智能数据分析。
    增加科学、精准的 Prompt 设计来引导模型分析。
    """
    from topklogsystem import TopKLogSystem
    import time
    q = _extract_last_user_question(prompt)
    # 1) 包装 Prompt
    enriched_prompt = generate_analysis_prompt(q)

     # 2) 参考资料块（本地 + 在线，均为可选）
    # ------------------------------------------------
    def _shorten(text: str, limit: int = 180) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def _clean_web_title(t: str) -> str:
        t = (t or "").strip()
        if t.startswith("#"):
            t = t.lstrip("#").strip()
        return t

    ctx_lines: list[str] = []

    # 本地 RAG
    # 本地 RAG
    if getattr(settings, "RAG_TOPK", 0) > 0:
        contexts = retrieve_contexts(q, topk=getattr(settings, "RAG_TOPK", 5))
        for i, c in enumerate(contexts, 1):
            title = c.get("title") or f"本地资料 {i}"
            content = c.get("text") or c.get("content") or ""
            source = c.get("path") or ""
            ctx_lines.append(
                # 本地
                f"- [L{i}] {title}：{_shorten(content, 50)}（来源：{_shorten(source, 80)}）"

            )



    # 在线检索（serpapi）
    if getattr(settings, "ENABLE_WEB_RAG", False):
        try:
            web_hits = web_retrieve(q, topk=getattr(settings, "WEB_RAG_TOPK", 5))
            for j, h in enumerate(web_hits, 1):
                title = _clean_web_title(h.get("title") or f"在线资料 {j}")
                snippet = _shorten(h.get("snippet") or "", 90)
                # 不展示链接，避免一长串蓝色超链接
                ctx_lines.append(
                    f"- [W{j}] {title}：{snippet}（来源：网络检索）"
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"WEB_RAG 调用失败：{e}")



    ctx_block = ""
    if ctx_lines:
        # 注意：这里不再输出“若出现以下条目，请…”
        ctx_block = "【参考资料】\n" + "\n---\n".join(ctx_lines)


    # —— 规范输出风格（ChatGPT风格 Markdown）——
    has_refs = bool(ctx_block)
    answer_style = f"""
    请严格按以下格式与要求输出（不要输出JSON或代码块，直接Markdown）：

    - 标题层级：不要使用一级标题；从 `###` 开始。
    - 各模块之间用一行横线 `---` 分隔。
    - 关键术语/参数名/结论用 **加粗**。
    - 列表尽量“短句 + 具体动作/参数区间/命令示例/注意事项”。

    ### 问题概述
    （用1~2句概括问题与影响）

    ---
    ### 详细分析
    - 从 **资源** / **JVM** / **并发** / **连接池** / **索引** / **网络** / **配置** / **代码** 等角度逐条分析（每点独立一行）。
    - 每条尽量给 **判据**（看什么指标/日志）与 **可能后果**（为什么会慢/报错）。

    ---
    ### 根因推断
    - 给出最可能的 2~4 条根因，**每条一句话 + 触发条件**。

    ---
    ### 快速缓解
    - 3~5 条可立刻执行的步骤（示例：提高连接池上限到 **N~M**；临时关闭某开销大的特性；回滚到稳定版本等）。

    ---
    ### 永久修复
    - 3~6 条长期措施（示例：**连接池** 参数基线、**JVM** 配置、**SQL/索引** 优化、**限流/熔断** 策略等）。

    ---
    ### 监控与可视化建议
    - 列出需要长期监控的指标（如：**活跃连接**、**等待队列长度**、**95/99 延迟**、**GC 周期** 等）及图表类型。

    {(
    """
    ---
    ### 参考资料
    
    """
    ) if has_refs else """
    > 未提供外部资料：请不要编造“参考资料”或使用 [1][2] 之类的编号。
    """}
    """

    final_prompt = f"{enriched_prompt}\n\n{ctx_block}\n\n{answer_style}"




    # 3) 初始化并调用大模型（沿用现有 TopKLogSystem 流程）
    system = TopKLogSystem(
        log_path="./data/log",
        llm="deepseek-r1:7b",
        embedding_model="bge-large:latest"
    )

    if getattr(settings, "ENABLE_WORKFLOW", False):
        # 计划-行动-观察-总结（会在内部按需调用 web_search/kb_search）
        answer_md = run_workflow(system.llm, q)
    else:
        # 单轮：用我们刚拼好的 final_prompt 直接出最终答案
        resp = system.llm.invoke(final_prompt)
        answer_md = resp.content if hasattr(resp, "content") else str(resp)
    # —— 主题一致性守门：若答案与当前问题明显不相干，则强制重答一次 —— #
    import re
    def _key_terms(q: str, topn: int = 4) -> list[str]:
        # 粗取关键词（中英数字），去掉过短项
        toks = re.findall(r"[\\u4e00-\\u9fa5A-Za-z0-9]+", q)
        # 按出现位置选前几个明显词
        uniq = []
        for t in toks:
            if len(t) >= 2 and t not in uniq:
                uniq.append(t)
        return uniq[:topn]

    def _off_topic(q: str, text: str) -> bool:
        ks = _key_terms(q)
        hit = sum(1 for k in ks if k in (text or ""))
        return hit == 0  # 一个都没覆盖，基本就跑题/复读

    if _off_topic(q, answer_md):
        ks = ", ".join(_key_terms(prompt))
        retry_prompt = (
            f"{final_prompt}\n\n"
            f"【重要】上一次回答未覆盖你的问题关键词（{ks}）。"
            f"请严格围绕本次用户问题重写，并在开头用一句话点名主题。"
        )
        resp2 = system.llm.invoke(retry_prompt)
        answer_md = resp2.content if hasattr(resp2, "content") else str(resp2)


    def _strip_fences(s: str) -> str:
        s = s.strip()
        if s.startswith("```") and s.endswith("```"):
            lines = s.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[1:-1]).strip()
        return s
    
    answer_md = _strip_fences(answer_md)

    raw = answer_md.strip()

    # 先假设不需要转
    should_try_json = False
    json_candidate = ""

    # 找到文本里最大的一段 {...}
    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        json_candidate = raw[start:end + 1]

    # 这里是关键：只有看起来“像那种大分析 JSON”的时候才转
        if (
            len(json_candidate) > 200  # 足够长
            or "problem_analysis" in json_candidate
            or "optimization_suggestion" in json_candidate
        ):
            should_try_json = True

    if should_try_json:
        converted = _json_to_markdown(json_candidate)
        if converted.strip() and converted.strip() != json_candidate.strip():
        # 截真正的尾巴，用最后一个 } 的位置
            tail = raw[end + 1 :] if end != -1 else ""
            answer_md = converted + tail




    
    # 再拼参考资料（workflow 场景下合并本地/在线的条目）
    if getattr(settings, "ENABLE_WORKFLOW", False):
        if ctx_block:
            # 1) 先收集答案里已有的编号，比如 [L1] / [W2]
            existing_tags = set()
            if "### 参考资料" in answer_md:
                tail_part = answer_md.split("### 参考资料", 1)[1]
                for ln in tail_part.splitlines():
                    ln = ln.strip()
                    if ln.startswith("- [") and "]" in ln:
                        tag = ln.split("]", 1)[0] + "]"   # 形如 "- [L1]"
                        existing_tags.add(tag)

            # 2) 再从我们拼出来的 ctx_block 里找需要补的
            to_append = []
            for ln in ctx_block.splitlines():
                ln = ln.strip()
                if ln.startswith("- [") and "]" in ln:
                    tag = ln.split("]", 1)[0] + "]"
                    if tag in existing_tags:
                        continue
                    existing_tags.add(tag)
                    to_append.append(ln)

            # 3) 真的有要补的，就补上；没有就算了
            if to_append:
                if "### 参考资料" in answer_md:
                    answer_md = answer_md.rstrip() + "\n" + "\n".join(to_append)
                else:
                    answer_md = f"{answer_md}\n\n### 参考资料\n" + "\n".join(to_append)

            # 4) 可选：限制一下最多展示条数，别让它一页全是参考资料
            max_refs = 10
            if "### 参考资料" in answer_md:
                before, after = answer_md.split("### 参考资料", 1)
                ref_lines = [ln for ln in after.splitlines() if ln.strip()]
                head = []
                count = 0
                
                for ln in ref_lines:
                    head.append(ln)
                    if ln.lstrip().startswith("- "):
                        count += 1
                    if count >= max_refs:
                        break
                answer_md = before.rstrip() + "\n### 参考资料\n" + "\n".join(head)

        else:
            # 没有 ctx_block 的兜底
            answer_md = (
                f"{answer_md}\n\n---\n### 参考资料\n"
                f"> 本次未检索到本地/在线资料，请确认 data/kb 是否有文件，或检查网络后再试。"
            )



    if not any(tok in answer_md for tok in ("### ", "**", "- ")):
        answer_md = "### 回答\n" + answer_md
    return answer_md

                 

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

def _json_to_markdown(maybe_json: str) -> str:
    """
    如果是结构化 JSON，就转成内容更饱满的 Markdown；
    否则原样返回。
    """
    import json
    try:
        data = json.loads(maybe_json)
    except Exception:
        return maybe_json if maybe_json.strip() else "> 本次未生成可读内容。"

    lines: list[str] = []

    # 1. 问题概述
    pa = data.get("problem_analysis")
    if pa:
        lines.append("### 问题概述")
        lines.append(pa.strip())
        lines.append("")

    # 2. 关键日志与指标（多拼一些字段）
    log_feats = data.get("log_features")
    if isinstance(log_feats, list) and log_feats:
        lines.append("### 关键日志与指标")
        for item in log_feats:
            if not isinstance(item, dict):
                lines.append(f"- {str(item)}")
                continue
            name = item.get("name") or item.get("resource") or "相关指标"
            desc = item.get("description") or item.get("anomaly") or ""
            status = item.get("status") or ""
            expected = item.get("expected") or ""
            abnormal = item.get("abnormal") or item.get("possible_consequence") or ""
            parts = [f"**{name}**"]
            if status:
                parts.append(f"状态：{status}")
            if desc:
                parts.append(desc)
            if expected:
                parts.append(f"正常情况应为：{expected}")
            if abnormal:
                parts.append(f"可能影响：{abnormal}")
            lines.append("- " + "；".join(p for p in parts if p))
        lines.append("")

    # 小工具：把 list/dict/str 展开成句子
    def _listify(val):
        if not val:
            return []
        if isinstance(val, list):
            out = []
            for item in val:
                if isinstance(item, dict):
                    out.append(item)
                else:
                    out.append(str(item))
            return out
        if isinstance(val, dict):
            return [val]
        return [str(val)]

    # 3. 异常模式（把 causes 也写出来）
    aps = _listify(data.get("anomaly_pattern"))
    if aps:
        lines.append("### 异常模式")
        for ap in aps:
            if isinstance(ap, dict):
                pat = ap.get("pattern") or ap.get("anomaly") or ""
                desc = ap.get("description") or ""
                causes = ap.get("causes") or ap.get("cause") or ""
                segs = []
                if pat:
                    segs.append(pat)
                if desc:
                    segs.append(desc)
                if causes:
                    if isinstance(causes, list):
                        segs.append("可能原因：" + "；".join(str(c) for c in causes))
                    else:
                        segs.append(f"可能原因：{causes}")
                lines.append("- " + "；".join(segs))
            else:
                lines.append(f"- {ap}")
        lines.append("")

    # 4. 根因推断（cause + trigger + impact 多写点）
    rcs = _listify(data.get("root_cause_inference"))
    if rcs:
        lines.append("### 根因推断")
        for i, rc in enumerate(rcs, 1):
            if isinstance(rc, dict):
                cause = rc.get("cause") or ""
                trigger = rc.get("trigger") or ""
                impact = rc.get("impact") or rc.get("description") or ""
                parts = []
                if cause:
                    parts.append(f"原因：{cause}")
                if trigger:
                    parts.append(f"触发场景：{trigger}")
                if impact:
                    parts.append(f"影响：{impact}")
                lines.append(f"{i}. " + "；".join(parts))
            else:
                lines.append(f"{i}. {rc}")
        lines.append("")

    # 5. 优化与处理建议（把 parameter / example / improve 都带上）
    opts = _listify(data.get("optimization_suggestion"))
    if opts:
        lines.append("### 优化与处理建议")
        for i, op in enumerate(opts, 1):
            if isinstance(op, dict):
                action = op.get("action") or "优化措施"
                param = op.get("parameter") or ""
                example = op.get("example") or ""
                improve = op.get("improve") or op.get("note") or ""
                segs = [action]
                if param:
                    segs.append(f"参数/做法：{param}")
                if example:
                    segs.append(f"示例：{example}")
                if improve:
                    segs.append(f"说明：{improve}")
                lines.append(f"{i}. " + "；".join(segs))
            else:
                lines.append(f"{i}. {op}")
        lines.append("")

    # 6. 监控与可视化建议
    vis = _listify(data.get("visualization_suggestion"))
    if vis:
        lines.append("### 监控与可视化建议")
        for i, v in enumerate(vis, 1):
            if isinstance(v, dict):
                chart = v.get("chart_type") or "图表"
                metrics = v.get("metrics") or v.get("data_points") or []
                desc = v.get("description") or ""
                segs = [f"推荐图表：{chart}"]
                if metrics:
                    if isinstance(metrics, list):
                        segs.append("关注指标：" + "，".join(str(m) for m in metrics))
                    else:
                        segs.append(f"关注指标：{metrics}")
                if desc:
                    segs.append(desc)
                lines.append(f"{i}. " + "；".join(segs))
            else:
                lines.append(f"{i}. {v}")
        lines.append("")

    # 7. 参考资料（你前面已经做了合并逻辑，这里照旧，兼容 str 和 dict）
    refs = data.get("references")
    if isinstance(refs, list) and refs:
        lines.append("### 参考资料")
        for r in refs:
            if isinstance(r, dict):
                src = r.get("source") or ""
                title = r.get("title") or ""
                desc = r.get("description") or r.get("content") or ""
                txt = " - ".join(x for x in [title, desc, src] if x)
                lines.append(f"- {txt}")
            else:
                lines.append(f"- {str(r)}")
        lines.append("")

    md = "\n".join(lines).strip()
    return md if md else (maybe_json if maybe_json.strip() else "> 本次未生成可读内容。")




import json, re

TOOLS = {
    "web_search": lambda q: web_retrieve(q, topk=getattr(settings, "WEB_RAG_TOPK", 5)),
    "kb_search": lambda q: retrieve_contexts(q, topk=getattr(settings, "RAG_TOPK", 5)) if getattr(settings, "RAG_TOPK", 0) > 0 else [],
    # 未来可以加：log_stats / sql_explain / shell_safe 等等……
}

ACTION_GUIDE = """
你是一个“计划-行动-观察-总结”的编排器。只返回 JSON，不要解释。

你可以选择以下工具之一执行一步动作：
- {"action":{"tool":"web_search","args":{"query":"..."}}, "reason":"..."}    # 在线检索
- {"action":{"tool":"kb_search","args":{"query":"..."}},  "reason":"..."}    # 本地检索（若不可用会返回空）

当你已经能写出最终答案时，返回（注意：必须是完整 Markdown，禁止示例/占位/省略号）：
- {"final_markdown":"### 问题概述\\n...\\n---\\n### 详细分析\\n...（这里是你写的完整 Markdown 文本）"}

严格要求：
- 只能返回一个 JSON 对象。
- final_markdown 必须是真实内容，**不要**包含“示例/占位/你的Markdown答案草稿/...” 等字样。
- 如果不确定就先用 action 检索一次。
"""


def run_workflow(llm, user_query: str) -> str:
    """简单的计划-行动-观察-总结循环；返回最终Markdown。"""
    import json, re
    scratch = []
    max_steps = int(getattr(settings, "WORKFLOW_MAX_STEPS", 2))
    for step in range(max_steps):
        plan_prompt = (
            f"用户问题：{user_query}\n"
            f"已掌握信息（可为空）：\n{chr(10).join(scratch)}\n\n"
            f"{ACTION_GUIDE}\n"
            "只输出JSON，不要任何解释。"
        )
        resp = llm.invoke(plan_prompt)
        txt = resp.content if hasattr(resp, "content") else str(resp)

        # —— 稳健 JSON 解析 —— #
        obj = {}
        try:
            m = re.search(r"\{.*\}", txt, flags=re.S)
            if m:
                obj = json.loads(m.group(0))
        except Exception as e:
            scratch.append(f"OBSERVATION(parse_error@step{step+1}): {str(e)[:200]}")

        # 兼容两种键名，并拦截“抄占位”
        final_txt = obj.get("final_markdown") or obj.get("final")
        if isinstance(final_txt, str):
            bad_signals = ["你的Markdown答案草稿", "占位", "示例", "placeholder", "…", "..."]
            if len(final_txt.strip()) >= 80 and not any(s in final_txt for s in bad_signals):
               return final_txt
            else:
                scratch.append(f"OBSERVATION(step{step+1}): model returned placeholder-like final, ignoring")
            
        if "final" in obj and obj["final"]:
            return obj["final"]

        act = (obj.get("action") or {})
        tool = act.get("tool")
        args = act.get("args") or {}
        if tool not in TOOLS:
            # 工具无效，继续下一步，让模型再想一次
            scratch.append(f"OBSERVATION(step{step+1}): tool invalid → {tool}")
            continue

        query = args.get("query", "") or user_query
        result = TOOLS[tool](query)

        if tool == "web_search":
            rows = []
            for k, h in enumerate(result[:5]):
                title = (h.get("title") or "").replace("#", "").strip()
                snippet = (h.get("snippet") or "").strip()
                if len(snippet) > 80:
                    snippet = snippet[:80].rstrip() + "..."
                # 只留一个编号，别把长网址塞给模型
                rows.append(f"[W{k+1}] {title}\n{snippet}")
            # 用 --- 分开几条，模型好读
            obs = "\n---\n".join(rows)
        elif tool == "kb_search":
            rows = []
            for k, r in enumerate(result[:5]):
                text = (r.get("text") or "")[:120].rstrip()
                path = r.get("path") or ""
                rows.append(f"[L{k+1}] {text}\n（来源：{path}）")
            obs = "\n---\n".join(rows)
        else:
            obs = str(result)


        scratch.append(f"OBSERVATION(step={step+1}, tool={tool}):\n{obs}")

    # —— 兜底最终成稿 —— #
    final_prompt = (
        f"用户问题：{user_query}\n"
        f"已掌握信息：\n{chr(10).join(scratch)}\n\n"
        "请按下面结构写最终 Markdown（不要写 JSON）：\n"
        "### 问题概述\n"
        "- 用1~2句话说问题是什么、影响是什么。\n"
        "---\n"
        "### 详细分析\n"
        "- 从资源/JVM/连接池/网络/配置/代码等角度列点分析；每条给判据和可能后果。\n"
        "---\n"
        "### 根因推断\n"
        "- 给出最可能的2~4条根因，每条一句话 + 触发场景。\n"
        "---\n"
        "### 快速缓解\n"
        "- 列3~5条现在就能做的动作，写清参数范围或命令示例。\n"
        "---\n"
        "### 永久修复\n"
        "- 列3~6条长期方案，比如参数基线、限流、代码优化、监控补充。\n"
        "---\n"
        "### 监控与可视化建议\n"
        "- 写要看的指标和图表类型。\n"
        "如果上面观察信息里出现了 [L1]/[W2] 这种编号，请在正文里引用它们。"
    )
    final_resp = llm.invoke(final_prompt)
    final_txt = final_resp.content if hasattr(final_resp, "content") else str(final_resp)
    return final_txt



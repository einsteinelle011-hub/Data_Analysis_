# web_retriever.py
# -*- coding: utf-8 -*-
from typing import List, Dict
from django.conf import settings
import os
import requests


def web_retrieve(query: str, topk: int = None) -> List[Dict]:
    """
    只使用 SerpAPI 的在线检索。
    返回格式统一为:
    [
      {"title": "...", "snippet": "...", "link": "...", "source": "serpapi/google"},
      ...
    ]
    """
    topk = topk or getattr(settings, "WEB_RAG_TOPK", 5)

    # 从 settings 或环境变量里拿 key
    api_key = getattr(settings, "SERPAPI_API_KEY", "") or os.getenv("SERPAPI_API_KEY", "")
    if not api_key:
        # 没 key 就直接返回空，让上层去显示“本次未检索到…”
        return []

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "num": topk,
                "hl": getattr(settings, "WEB_RAG_LANG", "zh-cn"),
            },
            timeout=10,
        )
        data = resp.json()
    except Exception:
        # 网络问题/解析问题都返回空
        return []

    results: List[Dict] = []
    for item in data.get("organic_results", [])[:topk]:
        results.append(
            {
                "title": item.get("title") or "",
                "snippet": item.get("snippet") or "",
                "link": item.get("link") or "",
                "source": "serpapi/google",
            }
        )

    return results

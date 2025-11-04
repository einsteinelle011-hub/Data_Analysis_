import os, re, json, pickle
from pathlib import Path
from typing import List, Dict
from django.conf import settings

# 轻量 BM25
try:
    from rank_bm25 import BM25Okapi
except Exception as e:
    BM25Okapi = None

# 可选 PDF
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


def _read_text_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def _read_json_file(p: Path) -> str:
    try:
        return json.dumps(json.loads(p.read_text(encoding="utf-8", errors="ignore")), ensure_ascii=False, indent=2)
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")

def _read_pdf_file(p: Path) -> str:
    if PdfReader is None:
        return ""
    text = []
    try:
        reader = PdfReader(str(p))
        for page in reader.pages:
            text.append(page.extract_text() or "")
    except Exception:
        pass
    return "\n".join(text)

def _load_doc_text(p: Path) -> str:
    suf = p.suffix.lower()
    if suf in [".txt", ".md", ".log", ".py", ".csv", ".yml", ".yaml"]:
        return _read_text_file(p)
    if suf in [".json"]:
        return _read_json_file(p)
    if suf in [".pdf"]:
        return _read_pdf_file(p)
    return ""


def _split_chunks(text: str, size: int, overlap: int) -> List[str]:
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+size])
        i += max(1, size - overlap)
    return [c.strip() for c in chunks if c.strip()]


class SimpleRAG:
    """最小可用：基于 BM25 的本地检索；无索引时自动构建。"""
    def __init__(self, kb_dir: Path, index_dir: Path):
        self.kb_dir = Path(kb_dir)
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.idx_path = self.index_dir / "bm25.pkl"
        self.meta_path = self.index_dir / "bm25_meta.pkl"
        self.bm25 = None
        self.chunks: List[str] = []
        self.metadatas: List[Dict] = []

    def _build(self):
        if BM25Okapi is None:
            raise RuntimeError("缺少依赖：rank-bm25，请先 `pip install rank-bm25`")
        files = []
        for suf in (".txt",".md",".log",".py",".json",".pdf",".csv",".yml",".yaml"):
            files.extend(self.kb_dir.rglob(f"*{suf}"))

        chunks, metas = [], []
        for fp in files:
            text = _load_doc_text(fp)
            if not text:
                continue
            for i, ck in enumerate(_split_chunks(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)):
                chunks.append(ck)
                metas.append({"path": str(fp), "chunk_id": i})

        tokenized = [c.split() for c in chunks]
        bm25 = BM25Okapi(tokenized)

        with open(self.idx_path, "wb") as f:
            pickle.dump(bm25, f)
        with open(self.meta_path, "wb") as f:
            pickle.dump({"chunks": chunks, "metas": metas}, f)

        self.bm25, self.chunks, self.metadatas = bm25, chunks, metas

    def _load(self):
        if self.idx_path.exists() and self.meta_path.exists():
            with open(self.idx_path, "rb") as f:
                self.bm25 = pickle.load(f)
            with open(self.meta_path, "rb") as f:
                meta = pickle.load(f)
            self.chunks, self.metadatas = meta["chunks"], meta["metas"]
        else:
            self._build()

    def ensure_ready(self):
        if self.bm25 is None:
            self._load()

    def search(self, query: str, topk: int = 5) -> List[Dict]:
        self.ensure_ready()
        scores = self.bm25.get_scores(query.split())
        # 取 topk
        idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:topk]
        out = []
        for i in idxs:
            out.append({
                "text": self.chunks[i],
                "score": float(scores[i]),
                "path": self.metadatas[i]["path"],
                "chunk_id": self.metadatas[i]["chunk_id"],
            })
        return out

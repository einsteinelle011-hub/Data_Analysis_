import os
import django
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deepseek_project.settings")
django.setup()

from django.conf import settings
from deepseek_api.rag import SimpleRAG

def main():
    kb = Path(settings.KB_DIR); idx = Path(settings.INDEX_DIR)
    kb.mkdir(parents=True, exist_ok=True)
    idx.mkdir(parents=True, exist_ok=True)
    rag = SimpleRAG(kb, idx)
    rag._build()
    print(f"索引构建完成。KB={kb}  INDEX={idx}")

if __name__ == "__main__":
    main()

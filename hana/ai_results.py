"""
Leitura opcional de resultados de IA gerados pela MIA.

Os resultados são gravados em arquivos JSON por SKU, em um diretório irmão
do catalog_root, tipicamente:

  data/catalog/<SKU>/manifest.json
  data/ai-results/<SKU>.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AiContent:
    product_name: str | None
    short_description: str | None
    technical_description_html: str | None
    key_features: list[str]


def _results_dir(catalog_root: Path) -> Path:
    return catalog_root.parent / "ai-results"


def _result_path(catalog_root: Path, sku: str) -> Path:
    return _results_dir(catalog_root) / f"{sku}.json"


def load_ai_content(catalog_root: Path, sku: str) -> AiContent | None:
    """
    Tenta ler o arquivo ai-results/<SKU>.json e extrair o conteúdo relevante.

    Se o arquivo não existir ou estiver inválido, retorna None.
    """
    path = _result_path(catalog_root, sku)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    content: dict[str, Any] = raw.get("content") if isinstance(raw, dict) else {}
    if not isinstance(content, dict):
        return None

    product_name = content.get("product_name")
    short = content.get("short_description")
    technical = content.get("technical_description_html")
    key_features_raw = content.get("key_features") or []
    key_features = [str(item) for item in key_features_raw if isinstance(item, str)]

    return AiContent(
        product_name=str(product_name) if isinstance(product_name, str) else None,
        short_description=str(short) if isinstance(short, str) else None,
        technical_description_html=str(technical) if isinstance(technical, str) else None,
        key_features=key_features,
    )


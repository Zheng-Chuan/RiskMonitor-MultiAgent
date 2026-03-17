"""提示词管理模块.

提供提示词外部化和加载功能。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PromptLoader:
    """提示词加载器."""

    def __init__(self, prompts_dir: Optional[str] = None) -> None:
        """
        初始化提示词加载器.

        Args:
            prompts_dir: 提示词目录路径，默认从项目根目录的 prompts/ 加载
        """
        if prompts_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            self._prompts_dir = repo_root / "prompts"
        else:
            self._prompts_dir = Path(prompts_dir)

    def load(self, name: str) -> Optional[str]:
        """
        加载提示词.

        Args:
            name: 提示词名称（不含扩展名）

        Returns:
            提示词内容，找不到返回 None
        """
        # 尝试多种扩展名
        for ext in [".txt", ".md", ".json"]:
            path = self._prompts_dir / f"{name}{ext}"
            if path.is_file():
                logger.debug(f"Loaded prompt: {name} from {path}")
                return path.read_text(encoding="utf-8")
        logger.warning(f"Prompt not found: {name}")
        return None

    def load_json(self, name: str) -> Optional[dict[str, Any]]:
        """
        加载 JSON 格式的提示词.

        Args:
            name: 提示词名称（不含扩展名）

        Returns:
            提示词 dict，找不到返回 None
        """
        content = self.load(name)
        if content:
            try:
                return json.loads(content)
            except Exception as e:
                logger.warning(f"Failed to parse JSON prompt {name}: {e}")
        return None


# 全局提示词加载器
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """获取全局提示词加载器."""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader

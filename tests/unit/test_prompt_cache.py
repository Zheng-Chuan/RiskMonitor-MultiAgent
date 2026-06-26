"""PromptCacheManager 单元测试.

测试场景:
1. get 未命中 → None, miss_count 增加
2. get 命中 → 返回内容, hit_count 增加
3. invalidate by version → 只失效匹配的
4. invalidate by date → 只失效匹配的
5. get_stats → hit_rate 计算正确
6. clear → 清空所有
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.prompts.prompt_cache import PromptCacheManager


# ---------------------------------------------------------------------------
# 1. get 未命中
# ---------------------------------------------------------------------------


class TestGetMiss:
    """测试 get 未命中."""

    def test_miss_returns_none(self):
        """未命中返回 None."""
        cache = PromptCacheManager()
        assert cache.get("nonexistent_key") is None

    def test_miss_increments_miss_count(self):
        """未命中时 miss_count += 1."""
        cache = PromptCacheManager()
        cache.get("nonexistent_key")
        stats = cache.get_stats()
        assert stats["miss_count"] == 1
        assert stats["hit_count"] == 0

    def test_multiple_misses(self):
        """多次未命中, miss_count 累加."""
        cache = PromptCacheManager()
        cache.get("key1")
        cache.get("key2")
        cache.get("key3")
        stats = cache.get_stats()
        assert stats["miss_count"] == 3


# ---------------------------------------------------------------------------
# 2. get 命中
# ---------------------------------------------------------------------------


class TestGetHit:
    """测试 get 命中."""

    def test_hit_returns_content(self):
        """命中返回缓存内容."""
        cache = PromptCacheManager()
        cache.set("key1", "cached content", "v1")
        result = cache.get("key1")
        assert result is not None
        assert result["content"] == "cached content"
        assert result["version"] == "v1"

    def test_hit_increments_hit_count(self):
        """命中时 hit_count += 1."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.get("key1")
        stats = cache.get_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 0

    def test_hit_returns_created_at(self):
        """命中返回 created_at 时间戳."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        result = cache.get("key1")
        assert result is not None
        assert "created_at" in result
        assert isinstance(result["created_at"], float)

    def test_hit_after_miss(self):
        """先未命中再命中."""
        cache = PromptCacheManager()
        cache.get("key1")  # miss
        cache.set("key1", "content", "v1")
        cache.get("key1")  # hit
        stats = cache.get_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1

    def test_multiple_hits(self):
        """多次命中, hit_count 累加."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.get("key1")
        cache.get("key1")
        cache.get("key1")
        stats = cache.get_stats()
        assert stats["hit_count"] == 3


# ---------------------------------------------------------------------------
# 3. invalidate by version
# ---------------------------------------------------------------------------


class TestInvalidateByVersion:
    """测试按 version 失效缓存."""

    def test_invalidate_by_version_removes_matching(self):
        """按 version 失效匹配的缓存."""
        cache = PromptCacheManager()
        # cache_key 格式: "stable_version:context_date"
        cache.set("v1:2025-01-15", "content1", "v1")
        cache.set("v2:2025-01-15", "content2", "v2")
        count = cache.invalidate(version="v1")
        assert count == 1
        assert cache.get("v1:2025-01-15") is None  # miss after invalidation
        # v2 仍然存在
        result = cache.get("v2:2025-01-15")
        assert result is not None
        assert result["content"] == "content2"

    def test_invalidate_by_version_multiple_keys(self):
        """按 version 失效多个匹配的缓存."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content1", "v1")
        cache.set("v1:2025-01-16", "content2", "v1")
        cache.set("v2:2025-01-15", "content3", "v2")
        count = cache.invalidate(version="v1")
        assert count == 2
        assert cache.get("v1:2025-01-15") is None
        assert cache.get("v1:2025-01-16") is None
        assert cache.get("v2:2025-01-15") is not None

    def test_invalidate_by_nonexistent_version(self):
        """按不存在的 version 失效返回 0."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content", "v1")
        count = cache.invalidate(version="v999")
        assert count == 0
        assert cache.get("v1:2025-01-15") is not None


# ---------------------------------------------------------------------------
# 4. invalidate by date
# ---------------------------------------------------------------------------


class TestInvalidateByDate:
    """测试按 date 失效缓存."""

    def test_invalidate_by_date_removes_matching(self):
        """按 date 失效匹配的缓存."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content1", "v1")
        cache.set("v1:2025-01-16", "content2", "v1")
        count = cache.invalidate(date="2025-01-15")
        assert count == 1
        assert cache.get("v1:2025-01-15") is None
        assert cache.get("v1:2025-01-16") is not None

    def test_invalidate_by_date_multiple_keys(self):
        """按 date 失效多个匹配的缓存."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content1", "v1")
        cache.set("v2:2025-01-15", "content2", "v2")
        cache.set("v1:2025-01-16", "content3", "v1")
        count = cache.invalidate(date="2025-01-15")
        assert count == 2
        assert cache.get("v1:2025-01-15") is None
        assert cache.get("v2:2025-01-15") is None
        assert cache.get("v1:2025-01-16") is not None

    def test_invalidate_by_nonexistent_date(self):
        """按不存在的 date 失效返回 0."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content", "v1")
        count = cache.invalidate(date="2099-12-31")
        assert count == 0
        assert cache.get("v1:2025-01-15") is not None


# ---------------------------------------------------------------------------
# 5. get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """测试 get_stats."""

    def test_initial_stats(self):
        """初始状态统计全为 0."""
        cache = PromptCacheManager()
        stats = cache.get_stats()
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["cache_size"] == 0

    def test_hit_rate_calculation(self):
        """hit_rate 计算正确."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        stats = cache.get_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1
        assert stats["hit_rate"] == 0.5

    def test_hit_rate_all_hits(self):
        """全部命中时 hit_rate=1.0."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.set("key2", "content", "v1")
        cache.get("key1")  # hit
        cache.get("key2")  # hit
        stats = cache.get_stats()
        assert stats["hit_rate"] == 1.0

    def test_hit_rate_all_misses(self):
        """全部未命中时 hit_rate=0.0."""
        cache = PromptCacheManager()
        cache.get("key1")  # miss
        cache.get("key2")  # miss
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_cache_size_reflects_entries(self):
        """cache_size 反映当前缓存条目数."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.set("key2", "content", "v1")
        cache.set("key3", "content", "v1")
        stats = cache.get_stats()
        assert stats["cache_size"] == 3


# ---------------------------------------------------------------------------
# 6. clear
# ---------------------------------------------------------------------------


class TestClear:
    """测试 clear."""

    def test_clear_removes_all_entries(self):
        """清空后所有缓存消失."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.set("key2", "content", "v1")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_clear_resets_cache_size(self):
        """清空后 cache_size=0."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.set("key2", "content", "v1")
        cache.clear()
        stats = cache.get_stats()
        assert stats["cache_size"] == 0

    def test_clear_resets_hit_miss_counts(self):
        """清空后 hit_count 和 miss_count 归零."""
        cache = PromptCacheManager()
        cache.set("key1", "content", "v1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        cache.clear()
        stats = cache.get_stats()
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0
        assert stats["hit_rate"] == 0.0


# ---------------------------------------------------------------------------
# 7. 额外测试: invalidate all
# ---------------------------------------------------------------------------


class TestInvalidateAll:
    """测试失效所有缓存."""

    def test_invalidate_all_without_args(self):
        """不提供参数时失效所有缓存."""
        cache = PromptCacheManager()
        cache.set("v1:2025-01-15", "content1", "v1")
        cache.set("v2:2025-01-16", "content2", "v2")
        count = cache.invalidate()
        assert count == 2
        assert cache.get("v1:2025-01-15") is None
        assert cache.get("v2:2025-01-16") is None

    def test_invalidate_all_returns_count(self):
        """失效所有返回失效数量."""
        cache = PromptCacheManager()
        cache.set("k1", "c1", "v1")
        cache.set("k2", "c2", "v1")
        cache.set("k3", "c3", "v1")
        count = cache.invalidate()
        assert count == 3

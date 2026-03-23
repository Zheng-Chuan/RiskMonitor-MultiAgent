#!/usr/bin/env python3
"""
Chroma 知识库初始化脚本.

向 Chroma 向量数据库中插入一些与 Equities desk 相关的知识数据,
用于支持第 4 个和第 8 个测试用例.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent import config

# 与 Equities desk 相关的知识数据
KNOWLEDGE_DOCUMENTS = [
    {
        "id": "kb_equities_001",
        "text": (
            "Equities desk is responsible for trading equity derivatives including options, futures, and swaps. "
            "The delta limit for Equities desk is 800. Breach occurs when absolute delta exceeds this threshold."
        ),
        "metadata": {
            "desk": "Equities",
            "topic": "risk_limit",
            "limit": 800,
        },
    },
    {
        "id": "kb_equities_002",
        "text": (
            "Historical breach patterns for Equities desk show that breaches typically occur around quarterly "
            "expiration dates and during high volatility periods. Previous breaches in March 2025 were resolved "
            "by reducing position sizes in AAPL and TSLA options."
        ),
        "metadata": {
            "desk": "Equities",
            "topic": "historical_breach",
        },
    },
    {
        "id": "kb_equities_003",
        "text": (
            "Market data for Equities desk includes: SPX index, VIX volatility index, interest rates, and "
            "individual stock prices for AAPL, GOOGL, MSFT, TSLA, NVDA, META, AMZN. Delta calculations use "
            "current market prices to compute position Greeks."
        ),
        "metadata": {
            "desk": "Equities",
            "topic": "market_data",
        },
    },
    {
        "id": "kb_equities_004",
        "text": (
            "Risk Analyst playbook for Equities desk breach: 1) Verify delta calculation, 2) Check if breach is "
            "persistent or temporary, 3) Recommend position reduction or hedging strategy, 4) Consult with trader "
            "before taking action."
        ),
        "metadata": {
            "desk": "Equities",
            "topic": "analyst_playbook",
        },
    },
    {
        "id": "kb_equities_005",
        "text": (
            "System Engineer checklist for Equities desk: 1) Check data feed health, 2) Verify calculation engine "
            "is running, 3) Confirm threshold configuration matches approved limit (800), 4) Review recent alert "
            "history for patterns."
        ),
        "metadata": {
            "desk": "Equities",
            "topic": "engineer_checklist",
        },
    },
    {
        "id": "kb_rates_001",
        "text": (
            "Rates desk handles interest rate derivatives including swaps, futures, and options. The delta limit "
            "for Rates desk is 75000. Breach occurs when absolute delta exceeds this threshold."
        ),
        "metadata": {
            "desk": "Rates",
            "topic": "risk_limit",
            "limit": 75000,
        },
    },
    {
        "id": "kb_credit_001",
        "text": (
            "Credit desk trades credit derivatives including CDS and CDX. The delta limit for Credit desk is 70000. "
            "Breach occurs when absolute delta exceeds this threshold."
        ),
        "metadata": {
            "desk": "Credit",
            "topic": "risk_limit",
            "limit": 70000,
        },
    },
]


async def init_knowledge_base() -> None:
    """初始化知识库."""
    print(f"Initializing Chroma knowledge base at: {config.get_chroma_host()}:{config.get_chroma_port()}")

    # 获取 Chroma store
    store = ChromaVectorStore(
        collection=config.get_chroma_collection(),
        dims=256,
    )

    # 插入知识文档
    print(f"Inserting {len(KNOWLEDGE_DOCUMENTS)} knowledge documents...")
    for doc in KNOWLEDGE_DOCUMENTS:
        store.upsert_alert(
            alert_id=doc["id"],
            document=doc["text"],
            metadata=doc["metadata"],
        )
        print(f"  Inserted: {doc['id']}")

    # 验证
    print("\nVerifying knowledge base...")
    results = store.query_alerts(
        query_text="Equities desk delta limit",
        top_k=3,
    )
    print(f"Query returned {len(results)} results")
    for r in results:
        print(f"  - {r.doc_id}: {r.document[:100]}...")

    print("\nKnowledge base initialization complete!")


if __name__ == "__main__":
    # 注意:ChromaVectorStore 是同步的,不需要 asyncio.run
    init_knowledge_base()

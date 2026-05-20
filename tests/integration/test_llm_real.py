"""LLM 和 ChromaDB 真实集成测试.

连接真实火山引擎 LLM 和 ChromaDB，测试：
- LLM chat_completions 真实调用
- ChromaDB upsert + 语义搜索
- 端到端知识库流程
"""

import uuid

import pytest

from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore, SimilarDoc
from riskmonitor_multiagent.llm.llm_client import LlmClient, extract_first_text


# ---------------------------------------------------------------------------
# Real LLM Tests (火山引擎)
# ---------------------------------------------------------------------------


class TestRealLLM:
    """火山引擎LLM真实调用测试."""

    async def test_llm_chat_completion_basic(self, real_llm_client: LlmClient):
        """测试真实LLM调用 - 基本对话."""
        response = await real_llm_client.chat_completions(
            messages=[{"role": "user", "content": "请用一句话解释什么是Delta风险"}],
            temperature=0.2,
            use_cache=False,
        )
        assert response is not None
        assert isinstance(response, dict)
        assert "choices" in response
        assert len(response["choices"]) > 0
        # 提取文本
        text = extract_first_text(response)
        assert len(text) > 0
        # 应包含风险相关内容
        assert any(kw in text for kw in ["Delta", "delta", "风险", "期权", "变化", "价格"])

    async def test_llm_risk_analysis_prompt(self, real_llm_client: LlmClient):
        """测试真实LLM - 风控分析prompt."""
        response = await real_llm_client.chat_completions(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的金融风险分析师，请简洁地回答问题。",
                },
                {
                    "role": "user",
                    "content": (
                        "某交易台的Delta敞口为150万美元，阈值为100万美元。"
                        "请分析这个breach的严重程度并给出建议。限50字以内。"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=200,
            use_cache=False,
        )
        assert response is not None
        text = extract_first_text(response)
        assert len(text) > 0

    async def test_llm_response_format(self, real_llm_client: LlmClient):
        """测试 LLM 响应的标准格式."""
        response = await real_llm_client.chat_completions(
            messages=[{"role": "user", "content": "回答：1+1等于几？只回答数字。"}],
            temperature=0.0,
            max_tokens=10,
            use_cache=False,
        )
        assert "id" in response or "choices" in response
        choices = response.get("choices", [])
        assert len(choices) >= 1
        first_choice = choices[0]
        assert "message" in first_choice
        assert "content" in first_choice["message"]

    async def test_extract_first_text_helper(self, real_llm_client: LlmClient):
        """测试 extract_first_text 辅助函数."""
        response = await real_llm_client.chat_completions(
            messages=[{"role": "user", "content": "Say hello"}],
            temperature=0.2,
            use_cache=False,
        )
        text = extract_first_text(response)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_extract_first_text_empty(self):
        """空响应应返回空字符串."""
        assert extract_first_text({}) == ""
        assert extract_first_text({"choices": []}) == ""
        assert extract_first_text({"choices": [{"message": {}}]}) == ""


# ---------------------------------------------------------------------------
# Real ChromaDB Tests
# ---------------------------------------------------------------------------


class TestChromaIntegration:
    """ChromaDB 真实集成测试."""

    def test_upsert_single_document(self, real_chroma_store: ChromaVectorStore):
        """测试真实插入单个文档."""
        doc_id = f"inttest-doc-{uuid.uuid4().hex[:8]}"
        real_chroma_store.upsert_alert(
            alert_id=doc_id,
            document="Equity Derivatives desk delta breach WARNING severity 1.5M threshold exceeded",
            metadata={"desk": "Equity Derivatives", "severity": "WARNING", "alert_id": doc_id},
        )
        # 验证可以查回
        results = real_chroma_store.query_alerts(query_text="Equity Derivatives delta breach", top_k=5)
        assert isinstance(results, list)
        assert any(r.doc_id == doc_id for r in results)

    def test_upsert_and_semantic_query(self, real_chroma_store: ChromaVectorStore):
        """测试语义搜索 - 查询相关文档."""
        # 插入多个不同主题的文档
        docs = [
            (f"inttest-fx-{uuid.uuid4().hex[:8]}",
             "FX Derivatives USDJPY forward position risk exposure critical",
             {"desk": "FX Derivatives", "severity": "CRITICAL"}),
            (f"inttest-eq-{uuid.uuid4().hex[:8]}",
             "Equity desk AAPL call option delta hedge rebalance needed",
             {"desk": "Equities", "severity": "INFO"}),
            (f"inttest-fi-{uuid.uuid4().hex[:8]}",
             "Fixed Income interest rate swap duration mismatch warning",
             {"desk": "Fixed Income", "severity": "WARNING"}),
        ]
        for doc_id, document, metadata in docs:
            metadata["alert_id"] = doc_id
            real_chroma_store.upsert_alert(alert_id=doc_id, document=document, metadata=metadata)

        # 查询 FX 相关
        fx_results = real_chroma_store.query_alerts(query_text="FX USDJPY forward risk", top_k=3)
        assert len(fx_results) > 0
        assert isinstance(fx_results[0], SimilarDoc)
        # 最相关的应该是 FX 文档
        assert fx_results[0].doc_id == docs[0][0]
        assert fx_results[0].similarity > 0.0

        # 查询 equity 相关
        eq_results = real_chroma_store.query_alerts(query_text="AAPL call option delta", top_k=3)
        assert len(eq_results) > 0
        assert eq_results[0].doc_id == docs[1][0]

    def test_upsert_overwrite(self, real_chroma_store: ChromaVectorStore):
        """测试 upsert 覆盖已有文档."""
        doc_id = f"inttest-overwrite-{uuid.uuid4().hex[:8]}"

        # 第一次写入
        real_chroma_store.upsert_alert(
            alert_id=doc_id,
            document="Original document about credit risk CDS spread widening",
            metadata={"version": "v1", "alert_id": doc_id},
        )

        # 覆盖写入
        real_chroma_store.upsert_alert(
            alert_id=doc_id,
            document="Updated document about commodity futures oil price volatility spike",
            metadata={"version": "v2", "alert_id": doc_id},
        )

        # 查询应返回更新后的内容
        results = real_chroma_store.query_alerts(query_text="commodity oil futures volatility", top_k=3)
        matched = [r for r in results if r.doc_id == doc_id]
        assert len(matched) == 1
        assert "commodity" in matched[0].document.lower() or "oil" in matched[0].document.lower()

    def test_query_empty_text_returns_empty(self, real_chroma_store: ChromaVectorStore):
        """空查询文本应返回空列表."""
        results = real_chroma_store.query_alerts(query_text="", top_k=5)
        assert results == []

    def test_query_top_k_limit(self, real_chroma_store: ChromaVectorStore):
        """验证 top_k 限制返回数量."""
        # 插入足够多的文档
        for i in range(5):
            doc_id = f"inttest-topk-{uuid.uuid4().hex[:8]}"
            real_chroma_store.upsert_alert(
                alert_id=doc_id,
                document=f"Risk alert number {i} for stress testing portfolio VaR breach",
                metadata={"index": str(i), "alert_id": doc_id},
            )

        results = real_chroma_store.query_alerts(query_text="stress test VaR risk alert", top_k=3)
        assert len(results) <= 3

    def test_similarity_scores_valid_range(self, real_chroma_store: ChromaVectorStore):
        """验证相似度分数在合理范围内 [0, 1]."""
        doc_id = f"inttest-sim-{uuid.uuid4().hex[:8]}"
        real_chroma_store.upsert_alert(
            alert_id=doc_id,
            document="Market risk VaR model validation backtesting breach",
            metadata={"alert_id": doc_id},
        )
        results = real_chroma_store.query_alerts(query_text="VaR model validation backtesting", top_k=3)
        for r in results:
            assert 0.0 <= r.similarity <= 1.0


# ---------------------------------------------------------------------------
# ChromaDB + LLM Combined Test
# ---------------------------------------------------------------------------


class TestKnowledgeBasePipeline:
    """知识库端到端流程测试：ChromaDB存储 + LLM分析."""

    async def test_store_alert_then_llm_analyze(self, real_chroma_store: ChromaVectorStore, real_llm_client: LlmClient):
        """存储告警到知识库，检索后用LLM分析."""
        # 1. 存储告警文档
        doc_id = f"inttest-pipeline-{uuid.uuid4().hex[:8]}"
        alert_text = (
            "CRITICAL: Equity Derivatives desk delta breach. "
            "abs_delta=2500000 exceeds threshold=1000000 by 1500000. "
            "Trader TRADER-001 position in AAPL-CALL-175."
        )
        real_chroma_store.upsert_alert(
            alert_id=doc_id,
            document=alert_text,
            metadata={"desk": "Equity Derivatives", "severity": "CRITICAL", "alert_id": doc_id},
        )

        # 2. 从知识库检索
        results = real_chroma_store.query_alerts(
            query_text="Equity Derivatives delta breach CRITICAL",
            top_k=3,
        )
        assert len(results) > 0
        retrieved_doc = results[0].document

        # 3. 用 LLM 分析检索到的告警
        response = await real_llm_client.chat_completions(
            messages=[
                {"role": "system", "content": "你是风险分析师，请简要分析以下告警。限30字。"},
                {"role": "user", "content": f"告警内容：{retrieved_doc}"},
            ],
            temperature=0.1,
            max_tokens=100,
            use_cache=False,
        )
        analysis = extract_first_text(response)
        assert len(analysis) > 0

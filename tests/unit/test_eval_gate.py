"""
质量门禁测试.

验证门禁检查逻辑是否正确.
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from eval.gate import evaluate_quality_gate, evaluate_with_custom_thresholds, GateResult


class TestQualityGate:
    """质量门禁测试."""
    
    def test_pass_all_metrics_good(self):
        """测试：所有指标都达标，应该通过."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.95,
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 1500,
                        "token_count": 4000,
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        result = evaluate_quality_gate(summary)
        
        assert result.passed is True
        assert len(result.reasons) == 0
        assert result.metrics_summary["evidence_support"] == 0.95
    
    def test_fail_evidence_too_low(self):
        """测试：证据支持度太低，应该失败."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.7,  # < 0.9
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 1500,
                        "token_count": 4000,
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        result = evaluate_quality_gate(summary)
        
        assert result.passed is False
        assert len(result.reasons) > 0
        assert any("证据支持度" in r for r in result.reasons)
    
    def test_fail_latency_too_high(self):
        """测试：延迟太高，应该失败."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.95,
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 2500,  # > 2000
                        "token_count": 4000,
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        result = evaluate_quality_gate(summary)
        
        assert result.passed is False
        assert any("延迟" in r or "latency" in r.lower() for r in result.reasons)
    
    def test_fail_token_too_many(self):
        """测试：Token 使用太多，应该失败."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.95,
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 1500,
                        "token_count": 6000,  # > 5000
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        result = evaluate_quality_gate(summary)
        
        assert result.passed is False
        assert any("Token" in r for r in result.reasons)
    
    def test_fail_contract_rate_too_high(self):
        """测试：合约失败率太高，应该失败."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.95,
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 1500,
                        "token_count": 4000,
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.1,  # > 0.05
        }
        
        result = evaluate_quality_gate(summary)
        
        assert result.passed is False
        assert any("合约失败率" in r or "contract" in r.lower() for r in result.reasons)
    
    def test_custom_thresholds(self):
        """测试：使用自定义阈值."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {
                        "evidence_support": 0.85,  # 低于默认 0.9
                        "reasoning_validity": 0.9,
                    },
                    "efficiency": {
                        "latency_ms": 1500,
                        "token_count": 4000,
                        "tool_call_efficiency": 0.95,
                    },
                    "collaboration": {
                        "information_diversity": 0.5,
                        "role_specialization": 0.7,
                    },
                    "task_accuracy": {
                        "execution_success_rate": 0.85,
                    },
                    "comprehension": {
                        "intent_recognition_f1": 0.9,
                    },
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        # 自定义阈值：降低证据支持度要求到 0.8
        thresholds = {
            "thresholds": {
                "evidence_support": {"min": 0.8},
            }
        }
        
        result = evaluate_with_custom_thresholds(summary, thresholds)
        
        # 使用自定义阈值后应该通过
        assert result.passed is True
        
        # 使用默认阈值应该失败
        default_result = evaluate_quality_gate(summary)
        assert default_result.passed is False
    
    def test_empty_summary(self):
        """测试：空摘要，应该使用默认值."""
        summary = {}
        
        result = evaluate_quality_gate(summary)
        
        # 空摘要应该使用默认值 (大部分指标默认为 0 或 1)
        assert isinstance(result, GateResult)
        assert isinstance(result.reasons, list)
    
    def test_metrics_summary_complete(self):
        """测试：返回的指标摘要应该包含所有关键指标."""
        summary = {
            "aggregates": {
                "metrics": {
                    "reasoning": {"evidence_support": 0.95, "reasoning_validity": 0.9},
                    "efficiency": {"latency_ms": 1500, "token_count": 4000, "tool_call_efficiency": 0.95},
                    "collaboration": {"information_diversity": 0.5, "role_specialization": 0.7},
                    "task_accuracy": {"execution_success_rate": 0.85},
                    "comprehension": {"intent_recognition_f1": 0.9},
                }
            },
            "contract_fail_rate": 0.02,
        }
        
        result = evaluate_quality_gate(summary)
        
        expected_keys = [
            "evidence_support",
            "latency_p95",
            "token_count",
            "contract_fail_rate",
            "information_diversity",
            "role_specialization",
            "task_completion",
            "tool_success",
            "reasoning_quality",
            "intent_accuracy",
        ]
        
        for key in expected_keys:
            assert key in result.metrics_summary, f"Missing key: {key}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

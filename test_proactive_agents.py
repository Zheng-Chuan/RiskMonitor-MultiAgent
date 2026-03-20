#!/usr/bin/env python3
"""测试主动 Agent 功能."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from riskmonitor_multiagent.proactive_agents import (
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)

def main():
    print("=" * 60)
    print("测试主动 Agent 创建")
    print("=" * 60)
    
    intent = ProactiveIntentAgent()
    orchestrator = ProactiveOrchestratorAgent()
    critic = ProactiveCriticAgent()
    engineer = ProactiveSystemEngineerAgent()
    analyst = ProactiveRiskAnalystAgent()
    
    print(f"\n✓ Intent agent: {intent.name}")
    print(f"✓ Orchestrator agent: {orchestrator.name}")
    print(f"✓ Critic agent: {critic.name}")
    print(f"✓ Engineer agent: {engineer.name}")
    print(f"✓ Analyst agent: {analyst.name}")
    
    print("\n" + "=" * 60)
    print("测试 BDI 状态")
    print("=" * 60)
    
    print(f"\nIntent BDI: {intent.get_bdi_state()}")
    print(f"\nEngineer BDI: {engineer.get_bdi_state()}")
    
    print("\n" + "=" * 60)
    print("测试添加信念")
    print("=" * 60)
    
    intent.add_belief(
        content={"test": "hello"},
        source="test_script",
        confidence=0.9
    )
    
    beliefs = intent.get_beliefs()
    print(f"\nIntent beliefs: {beliefs}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)

if __name__ == "__main__":
    main()

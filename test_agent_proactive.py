#!/usr/bin/env python3
"""
测试 Agent 主动性功能.

验证后台监控循环是否真正工作.
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from riskmonitor_multiagent.proactive_agents.roles import ProactiveSystemEngineerAgent
from riskmonitor_multiagent.observability.metrics import inc_counter


async def test_agent_proactive():
    """测试 Agent 主动性."""
    print("=" * 60)
    print("测试 Agent 主动性功能")
    print("=" * 60)
    
    # 创建 Agent
    agent = ProactiveSystemEngineerAgent()
    
    print(f"\n1. 启动 Agent 后台监控...")
    await agent.start_background_monitor()
    print(f"   ✅ 后台监控已启动 (interval={agent._monitor_interval}s)")
    
    # 等待监控循环启动
    await asyncio.sleep(2)
    
    print(f"\n2. 模拟系统错误率升高...")
    # 模拟错误指标
    for i in range(15):
        inc_counter("proactive_agent_runs_error")
    for i in range(5):
        inc_counter("proactive_agent_runs_total")
    
    print(f"   ✅ 已添加错误指标 (15 错误 / 5 总计)")
    
    print(f"\n3. 等待监控循环感知和处理...")
    # 等待监控循环执行 (最多等待 2 个周期)
    await asyncio.sleep(agent._monitor_interval * 2 + 2)
    
    print(f"\n4. 检查 Agent 状态...")
    # 检查信念
    beliefs = agent.get_beliefs(source="system_metrics")
    print(f"   信念数量:{len(beliefs)}")
    for belief in beliefs:
        print(f"     - {belief.belief_id}: {belief.content}")
    
    # 检查意图
    intentions = agent.get_pending_intentions()
    print(f"   待处理意图:{len(intentions)}")
    for intention in intentions:
        print(f"     - {intention.intention_id}: {intention.description}")
        print(f"       Target: {intention.target_agent}")
        print(f"       Status: {intention.status}")
    
    # 检查 BDI 状态
    bdi_state = agent.get_bdi_state()
    print(f"\n5. BDI 状态摘要:")
    print(f"   信念:{len(bdi_state['beliefs'])}")
    print(f"   愿望:{len(bdi_state['desires'])}")
    print(f"   意图:{len(bdi_state['intentions'])}")
    
    # 停止监控
    print(f"\n6. 停止 Agent 后台监控...")
    await agent.stop_background_monitor()
    print(f"   ✅ 后台监控已停止")
    
    # 验证结果
    print(f"\n" + "=" * 60)
    print("验证结果:")
    print("=" * 60)
    
    has_belief = len(beliefs) > 0
    has_intention = len(intentions) > 0 or len(bdi_state['intentions']) > 0
    
    if has_belief:
        print("✅ Agent 成功感知到系统异常 (信念已添加)")
    else:
        print("❌ Agent 未感知到系统异常 (无信念)")
    
    if has_intention:
        print("✅ Agent 主动形成告警意图 (意图已创建)")
    else:
        print("❌ Agent 未形成告警意图 (无意图)")
    
    if has_belief and has_intention:
        print("\n🎉 Agent 主动性功能工作正常!")
        print("   - 后台监控循环真正运行")
        print("   - 感知/思考/行动方法不再为空")
        print("   - Agent 能够主动发现异常并发起告警")
    else:
        print("\n⚠️  Agent 主动性功能可能存在问题")
    
    print("=" * 60)
    
    return has_belief and has_intention


if __name__ == "__main__":
    success = asyncio.run(test_agent_proactive())
    sys.exit(0 if success else 1)

-- Phase 6 Checkpoint 14.4.1: 记忆永久化存储层
-- 为 MemoryStore 和 SkillStore 创建 MySQL 持久化表

-- 记忆条目持久化表
CREATE TABLE IF NOT EXISTS memory_store (
    entry_id VARCHAR(128) PRIMARY KEY COMMENT '记忆条目唯一ID',
    ts_ms BIGINT NOT NULL COMMENT '时间戳(毫秒)',
    agent_id VARCHAR(64) NOT NULL COMMENT 'Agent 标识',
    scope VARCHAR(16) NOT NULL COMMENT 'private 或 shared',
    kind VARCHAR(32) NOT NULL COMMENT '条目类型: plan, analysis, lesson 等',
    memory_type VARCHAR(32) NOT NULL COMMENT 'episodic, semantic, procedural',
    content JSON NOT NULL COMMENT '条目内容',
    source VARCHAR(128) COMMENT '来源',
    confidence FLOAT DEFAULT 0.0 COMMENT '置信度 [0, 1]',
    created_by VARCHAR(64) COMMENT '创建者',
    trace_ref JSON COMMENT '链路追踪引用',
    tags JSON COMMENT '标签列表',
    session_id VARCHAR(128) COMMENT '会话ID',
    run_id VARCHAR(128) COMMENT '运行ID',
    ttl_tier VARCHAR(16) DEFAULT 'short_term' COMMENT 'TTL 层级: short_term, long_term',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_agent_kind (agent_id, kind),
    INDEX idx_run_id (run_id),
    INDEX idx_scope_kind (scope, kind),
    INDEX idx_ttl_tier (ttl_tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆条目持久化表';

-- Skill 持久化表
CREATE TABLE IF NOT EXISTS skill_store (
    skill_id VARCHAR(128) PRIMARY KEY COMMENT 'Skill 唯一ID',
    name VARCHAR(256) NOT NULL COMMENT 'Skill 名称',
    tags JSON COMMENT '标签列表',
    applicable_conditions JSON COMMENT '适用条件列表',
    steps JSON COMMENT '执行步骤列表',
    failure_boundary TEXT COMMENT '失败边界描述',
    confidence FLOAT DEFAULT 0.5 COMMENT '置信度 [0, 1]',
    write_origin VARCHAR(16) DEFAULT 'auto' COMMENT '写入来源: auto, manual, revision',
    status VARCHAR(16) DEFAULT 'active' COMMENT '状态: active, deprecated, archived',
    usage_count INT DEFAULT 0 COMMENT '使用次数',
    success_rate FLOAT DEFAULT 0.0 COMMENT '成功率 [0, 1]',
    revision_history JSON COMMENT '修订历史',
    source_run_id VARCHAR(128) COMMENT '来源运行ID',
    source_agent_id VARCHAR(64) COMMENT '来源Agent ID',
    created_at BIGINT COMMENT '创建时间戳(毫秒)',
    updated_at BIGINT COMMENT '更新时间戳(毫秒)',
    INDEX idx_status_confidence (status, confidence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Skill 持久化表';

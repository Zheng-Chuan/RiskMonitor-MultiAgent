"""
集成测试：数据库操作
需要Docker容器运行
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pymysql
from dotenv import load_dotenv
import os

load_dotenv()


@pytest.fixture
def db_connection():
    """数据库连接fixture"""
    conn = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        database=os.getenv('MYSQL_DATABASE', 'riskmonitor'),
        user=os.getenv('MYSQL_USER', 'admin'),
        password=os.getenv('MYSQL_PASSWORD', 'riskmonitor2024'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    yield conn
    conn.close()


def test_database_connection(db_connection):
    """测试数据库连接"""
    cursor = db_connection.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    assert result is not None
    cursor.close()


def test_positions_table_exists(db_connection):
    """测试positions表是否存在"""
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM information_schema.tables 
        WHERE table_schema = 'riskmonitor' AND table_name = 'positions'
    """)
    result = cursor.fetchone()
    assert result['count'] == 1
    cursor.close()


def test_positions_data_exists(db_connection):
    """测试positions表是否有数据"""
    cursor = db_connection.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM positions")
    result = cursor.fetchone()
    assert result['count'] > 0
    print(f"Found {result['count']} positions in database")
    cursor.close()


def test_query_by_trader(db_connection):
    """测试按交易员查询"""
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT * FROM positions 
        WHERE trader_id = 'TRADER-001'
    """)
    positions = cursor.fetchall()
    assert len(positions) > 0
    
    # 验证所有记录都属于TRADER-001
    for pos in positions:
        assert pos['trader_id'] == 'TRADER-001'
    
    cursor.close()


def test_query_by_desk(db_connection):
    """测试按交易台查询"""
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT * FROM positions 
        WHERE desk = 'Equity Derivatives'
    """)
    positions = cursor.fetchall()
    assert len(positions) > 0
    
    # 验证所有记录都属于Equity Derivatives
    for pos in positions:
        assert pos['desk'] == 'Equity Derivatives'
    
    cursor.close()


def test_delta_aggregation(db_connection):
    """测试Delta聚合计算"""
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT SUM(delta) as total_delta 
        FROM positions
    """)
    result = cursor.fetchone()
    assert result['total_delta'] is not None
    print(f"Total Delta: {result['total_delta']}")
    cursor.close()


def test_delta_by_desk(db_connection):
    """测试按交易台分组的Delta"""
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT desk, SUM(delta) as desk_delta, COUNT(*) as position_count
        FROM positions
        GROUP BY desk
    """)
    results = cursor.fetchall()
    assert len(results) > 0
    
    for row in results:
        print(f"Desk: {row['desk']}, Delta: {row['desk_delta']}, Positions: {row['position_count']}")
        assert row['position_count'] > 0
    
    cursor.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

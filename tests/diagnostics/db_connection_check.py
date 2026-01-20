#!/usr/bin/env python3
"""
数据库连接测试脚本
用于验证与 MySQL 数据库的连通性
"""

import os
import sys
from pathlib import Path

# 将项目根目录加入路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pymysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(dotenv_path=project_root / ".env")

def test_connection():
    """测试数据库连接"""
    
    # 从环境变量读取数据库连接信息
    db_config = {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'database': os.getenv('MYSQL_DATABASE', 'riskmonitor'),
        'user': os.getenv('MYSQL_USER', 'admin'),
        'password': os.getenv('MYSQL_PASSWORD'),
        'charset': 'utf8mb4'
    }
    
    if db_config['password'] is None or not str(db_config['password']).strip():
        print("✗ MYSQL_PASSWORD is missing")
        print("  Please set MYSQL_PASSWORD in .env or environment variables")
        return False
    
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)
    print(f"Host: {db_config['host']}")
    print(f"Port: {db_config['port']}")
    print(f"Database: {db_config['database']}")
    print(f"User: {db_config['user']}")
    print("-" * 60)
    
    try:
        # 尝试连接
        print("Connecting to database...")
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        
        # 测试查询
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        print(f"✓ Connection successful!")
        print(f"MySQL version: {version[0]}")
        
        # 检查 positions 表是否存在
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = 'positions';
        """, (db_config['database'],))
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("✓ 'positions' table exists")
            
            # 统计记录数
            cursor.execute("SELECT COUNT(*) FROM positions;")
            count = cursor.fetchone()[0]
            print(f"✓ Found {count} records in positions table")
            
            # 打印样例数据
            if count > 0:
                cursor.execute("SELECT * FROM positions LIMIT 3;")
                records = cursor.fetchall()
                print("\nSample data:")
                for record in records:
                    print(f"  - {record[0]}: {record[1]} | {record[2]} | {record[3]}")
        else:
            print("⚠ 'positions' table does not exist yet")
            print("  Run init_db.sql to create the schema")
        
        # 关闭连接
        cursor.close()
        conn.close()
        
        print("-" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return True
        
    except pymysql.OperationalError as e:
        print(f"✗ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Docker containers are running: docker-compose up -d")
        print("2. Check if MySQL is ready: docker-compose ps")
        print("3. Verify .env file exists and has correct credentials")
        print("=" * 60)
        return False
        
    except Exception as e:
        print(f"✗ Error: {e}")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Database connection test script
Tests the connection to MySQL database
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_connection():
    """Test database connection"""
    
    # Get database credentials from environment
    db_config = {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'database': os.getenv('MYSQL_DATABASE', 'riskmonitor'),
        'user': os.getenv('MYSQL_USER', 'admin'),
        'password': os.getenv('MYSQL_PASSWORD', 'riskmonitor2024'),
        'charset': 'utf8mb4'
    }
    
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)
    print(f"Host: {db_config['host']}")
    print(f"Port: {db_config['port']}")
    print(f"Database: {db_config['database']}")
    print(f"User: {db_config['user']}")
    print("-" * 60)
    
    try:
        # Attempt connection
        print("Connecting to database...")
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        print(f"✓ Connection successful!")
        print(f"MySQL version: {version[0]}")
        
        # Check if positions table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = 'positions';
        """, (db_config['database'],))
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("✓ 'positions' table exists")
            
            # Count records
            cursor.execute("SELECT COUNT(*) FROM positions;")
            count = cursor.fetchone()[0]
            print(f"✓ Found {count} records in positions table")
            
            # Show sample data
            if count > 0:
                cursor.execute("SELECT * FROM positions LIMIT 3;")
                records = cursor.fetchall()
                print("\nSample data:")
                for record in records:
                    print(f"  - {record[0]}: {record[1]} | {record[2]} | {record[3]}")
        else:
            print("⚠ 'positions' table does not exist yet")
            print("  Run init_db.sql to create the schema")
        
        # Close connection
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

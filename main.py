#!/usr/bin/env python3
"""
RiskMonitor-MCP Server
MCP Server for Financial Derivatives Risk Management
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from mcp.server import FastMCP
import pymysql
from typing import Optional

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("RiskMonitor")

# Database connection helper
def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        database=os.getenv('MYSQL_DATABASE', 'riskmonitor'),
        user=os.getenv('MYSQL_USER', 'admin'),
        password=os.getenv('MYSQL_PASSWORD', 'riskmonitor2024'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


@mcp.tool()
def query_all_positions() -> str:
    """查询所有头寸数据
    
    Returns:
        str: 所有头寸的JSON格式数据
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT position_id, trader_id, desk, security_id, 
                   quantity, delta, entry_date, currency
            FROM positions
            ORDER BY entry_date DESC
        """)
        
        positions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not positions:
            return "No positions found."
        
        # Format output
        result = f"Found {len(positions)} positions:\n\n"
        for pos in positions:
            result += f"Position ID: {pos['position_id']}\n"
            result += f"  Trader: {pos['trader_id']}\n"
            result += f"  Desk: {pos['desk']}\n"
            result += f"  Security: {pos['security_id']}\n"
            result += f"  Quantity: {pos['quantity']:,.0f}\n"
            result += f"  Delta: {pos['delta']:,.2f}\n"
            result += f"  Entry Date: {pos['entry_date']}\n"
            result += f"  Currency: {pos['currency']}\n"
            result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error querying positions: {str(e)}"


@mcp.tool()
def query_positions_by_trader(trader_id: str) -> str:
    """查询特定交易员的所有头寸
    
    Args:
        trader_id: 交易员ID，例如 'TRADER-001'
    
    Returns:
        str: 该交易员的所有头寸数据
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT position_id, trader_id, desk, security_id, 
                   quantity, delta, entry_date, currency
            FROM positions
            WHERE trader_id = %s
            ORDER BY entry_date DESC
        """, (trader_id,))
        
        positions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not positions:
            return f"No positions found for trader {trader_id}."
        
        # Calculate totals
        total_delta = sum(float(pos['delta']) for pos in positions)
        
        # Format output
        result = f"Trader {trader_id} - {len(positions)} positions:\n"
        result += f"Total Delta: {total_delta:,.2f}\n\n"
        
        for pos in positions:
            result += f"Position ID: {pos['position_id']}\n"
            result += f"  Desk: {pos['desk']}\n"
            result += f"  Security: {pos['security_id']}\n"
            result += f"  Quantity: {pos['quantity']:,.0f}\n"
            result += f"  Delta: {pos['delta']:,.2f}\n"
            result += f"  Entry Date: {pos['entry_date']}\n"
            result += f"  Currency: {pos['currency']}\n"
            result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error querying positions for trader {trader_id}: {str(e)}"


@mcp.tool()
def query_positions_by_desk(desk_name: str) -> str:
    """查询特定交易台的所有头寸
    
    Args:
        desk_name: 交易台名称，例如 'Equity Derivatives'
    
    Returns:
        str: 该交易台的所有头寸数据
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT position_id, trader_id, desk, security_id, 
                   quantity, delta, entry_date, currency
            FROM positions
            WHERE desk = %s
            ORDER BY entry_date DESC
        """, (desk_name,))
        
        positions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not positions:
            return f"No positions found for desk {desk_name}."
        
        # Calculate totals
        total_delta = sum(float(pos['delta']) for pos in positions)
        traders = set(pos['trader_id'] for pos in positions)
        
        # Format output
        result = f"Desk: {desk_name}\n"
        result += f"Total Positions: {len(positions)}\n"
        result += f"Traders: {len(traders)}\n"
        result += f"Total Delta: {total_delta:,.2f}\n\n"
        
        for pos in positions:
            result += f"Position ID: {pos['position_id']}\n"
            result += f"  Trader: {pos['trader_id']}\n"
            result += f"  Security: {pos['security_id']}\n"
            result += f"  Quantity: {pos['quantity']:,.0f}\n"
            result += f"  Delta: {pos['delta']:,.2f}\n"
            result += f"  Entry Date: {pos['entry_date']}\n"
            result += f"  Currency: {pos['currency']}\n"
            result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error querying positions for desk {desk_name}: {str(e)}"


@mcp.tool()
def calculate_total_delta() -> str:
    """计算所有头寸的总Delta
    
    Returns:
        str: 总Delta及按交易台分组的Delta
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total delta
        cursor.execute("SELECT SUM(delta) as total_delta FROM positions")
        total_result = cursor.fetchone()
        total_delta = float(total_result['total_delta']) if total_result['total_delta'] else 0
        
        # Delta by desk
        cursor.execute("""
            SELECT desk, SUM(delta) as desk_delta, COUNT(*) as position_count
            FROM positions
            GROUP BY desk
            ORDER BY ABS(SUM(delta)) DESC
        """)
        
        desk_deltas = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format output
        result = f"Portfolio Total Delta: {total_delta:,.2f}\n\n"
        result += "Delta by Desk:\n"
        result += "-" * 60 + "\n"
        
        for desk in desk_deltas:
            result += f"{desk['desk']:<30} {desk['desk_delta']:>15,.2f} ({desk['position_count']} positions)\n"
        
        return result
        
    except Exception as e:
        return f"Error calculating total delta: {str(e)}"


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()

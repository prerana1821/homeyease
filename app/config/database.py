"""
PostgreSQL database connection using psycopg2.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from typing import Dict, Any, Optional, List
import json

class DatabaseManager:
    """PostgreSQL database manager with connection pooling."""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        self.pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool."""
        if not self.database_url:
            print("❌ DATABASE_URL not found")
            return
            
        try:
            self.pool = SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.database_url
            )
            print("✅ PostgreSQL connection pool created")
        except Exception as e:
            print(f"❌ Failed to create connection pool: {e}")
    
    @contextmanager
    def get_connection(self):
        """Get database connection from pool."""
        if not self.pool:
            raise Exception("Database pool not initialized")
        
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        finally:
            if conn:
                self.pool.putconn(conn)
    
    async def execute_query(self, query: str, params: Optional[tuple] = None, fetch: bool = True) -> Optional[List[Dict[str, Any]]]:
        """Execute a query and return results."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    
                    if fetch:
                        results = cursor.fetchall()
                        return [dict(row) for row in results]
                    else:
                        conn.commit()
                        return None
        except Exception as e:
            print(f"Database error: {e}")
            return None
    
    async def execute_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Execute a query and return single result."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            print(f"Database error: {e}")
            return None

# Global database manager instance
db_manager = DatabaseManager()
"""
Database wrapper for unified Supabase and SQLAlchemy interface
Handles both cloud (Supabase) and local (PostgreSQL) databases transparently
"""

from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from supabase import Client
from loguru import logger


class QueryBuilder:
    """Query builder for chaining database operations"""
    
    def __init__(self, db_wrapper: 'DatabaseWrapper', table: str):
        self.db_wrapper = db_wrapper
        self.table = table
        self._select_columns = "*"
        self._filters = {}
        self._order_by = None
        self._order_desc = False
        self._limit_count = None
        self._insert_data = None
        
    def select(self, columns: str = "*"):
        self._select_columns = columns
        return self
        
    def insert(self, data: Dict[str, Any]):
        self._insert_data = data
        return self
        
    def eq(self, column: str, value: Any):
        self._filters[column] = value
        return self
        
    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self
        
    def limit(self, count: int):
        self._limit_count = count
        return self
        
    def execute(self):
        if self._insert_data is not None:
            return self.db_wrapper._execute_insert(self.table, self._insert_data)
        else:
            return self.db_wrapper._execute_query(
                table=self.table,
                columns=self._select_columns,
                filters=self._filters,
                order_by=self._order_by,
                order_desc=self._order_desc,
                limit_count=self._limit_count
            )


class DatabaseWrapper:
    """Unified database interface for Supabase and SQLAlchemy"""
    
    def __init__(self, db_client):
        self.client = db_client
        # Detect Supabase client robustly: prefer isinstance check, fall back to duck-typing
        try:
            from supabase import Client as SupabaseClient
        except Exception:
            SupabaseClient = None

        self.is_supabase = False
        if SupabaseClient is not None:
            try:
                self.is_supabase = isinstance(db_client, SupabaseClient)
            except Exception:
                self.is_supabase = False

        # Fallback: duck-type a Supabase-like client by presence of `table` method
        if not self.is_supabase:
            self.is_supabase = hasattr(db_client, "table") and callable(getattr(db_client, "table", None))

        # SQLAlchemy Session detection
        try:
            self.is_sqlalchemy = isinstance(db_client, Session)
        except Exception:
            self.is_sqlalchemy = False
        
    def table(self, table: str) -> QueryBuilder:
        """Start a query on a table"""
        return QueryBuilder(self, table)
        
    def _execute_query(self, table: str, columns: str = "*", filters: Optional[Dict[str, Any]] = None, 
                      order_by: Optional[str] = None, order_desc: bool = False, limit_count: Optional[int] = None) -> List[Dict]:
        """
        Execute a query with the given parameters
        
        Args:
            table: Table name
            columns: Columns to select
            filters: Dictionary of column: value filters
            order_by: Column to order by
            order_desc: Whether to order descending
            limit_count: Maximum number of records to return
            
        Returns:
            List of records as dictionaries
        """
        try:
            if self.is_supabase:
                # Supabase query
                query = self.client.table(table).select(columns)
                
                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)
                        
                if order_by:
                    query = query.order(order_by, desc=order_desc)
                    
                if limit_count:
                    query = query.limit(limit_count)
                
                result = query.execute()
                return result.data if result.data else []
                
            elif self.is_sqlalchemy:
                # SQLAlchemy query - using raw SQL
                from sqlalchemy import text
                
                # Build WHERE clause
                where_clause = ""
                params = {}
                
                if filters:
                    conditions = []
                    for i, (key, value) in enumerate(filters.items()):
                        param_name = f"param_{i}"
                        conditions.append(f"{key} = :{param_name}")
                        params[param_name] = value
                    where_clause = " WHERE " + " AND ".join(conditions)
                
                # Build ORDER BY clause
                order_clause = ""
                if order_by:
                    direction = "DESC" if order_desc else "ASC"
                    order_clause = f" ORDER BY {order_by} {direction}"
                
                # Build LIMIT clause
                limit_clause = ""
                if limit_count:
                    limit_clause = f" LIMIT {limit_count}"
                
                query_str = f"SELECT {columns} FROM {table}{where_clause}{order_clause}{limit_clause}"
                result = self.client.execute(text(query_str), params)
                
                # Convert to list of dicts
                rows = []
                for row in result:
                    rows.append(dict(row._mapping))
                
                return rows
                
            else:
                raise ValueError("Unknown database client type")
                
        except Exception as e:
            logger.error(f"Database query error: {e}")
            raise
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, columns: str = "*", 
               order_by: Optional[str] = None, order_desc: bool = False, limit_count: Optional[int] = None) -> List[Dict]:
        """
        Convenience method for selecting records
        
        Args:
            table: Table name
            filters: Dictionary of column: value filters
            columns: Columns to select
            order_by: Column to order by
            order_desc: Whether to order descending
            limit_count: Maximum number of records to return
            
        Returns:
            List of records as dictionaries
        """
        return self._execute_query(
            table=table,
            columns=columns,
            filters=filters,
            order_by=order_by,
            order_desc=order_desc,
            limit_count=limit_count
        )
    
    def _execute_insert(self, table: str, data: Dict[str, Any]) -> Optional[Dict]:
        """
        Execute an insert query
        
        Args:
            table: Table name
            data: Dictionary of column: value pairs
            
        Returns:
            Inserted record as dictionary or None
        """
        try:
            if self.is_supabase:
                result = self.client.table(table).insert(data).execute()
                return result.data[0] if result.data else None
                
            elif self.is_sqlalchemy:
                from sqlalchemy import text
                
                # Build INSERT query
                columns = ", ".join(data.keys())
                placeholders = ", ".join([f":{key}" for key in data.keys()])
                
                query_str = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
                result = self.client.execute(text(query_str), data)
                self.client.commit()
                
                # Get the inserted row
                row = result.fetchone()
                return dict(row._mapping) if row else None
                
            else:
                raise ValueError("Unknown database client type")
                
        except Exception as e:
            logger.error(f"Database insert error: {e}")
            if self.is_sqlalchemy:
                self.client.rollback()
            raise
    
    def update(self, table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """
        Update records in a table
        
        Args:
            table: Table name
            data: Dictionary of column: value pairs to update
            filters: Dictionary of column: value filters to identify records
            
        Returns:
            True if update was successful
        """
        try:
            if self.is_supabase:
                query = self.client.table(table).update(data)
                for key, value in filters.items():
                    query = query.eq(key, value)
                result = query.execute()
                return len(result.data) > 0
                
            elif self.is_sqlalchemy:
                from sqlalchemy import text
                
                # Build SET clause
                set_clause = ", ".join([f"{key} = :{key}" for key in data.keys()])
                
                # Build WHERE clause
                where_conditions = []
                params = dict(data)  # Copy data for parameters
                
                for i, (key, value) in enumerate(filters.items()):
                    param_name = f"filter_{i}"
                    where_conditions.append(f"{key} = :{param_name}")
                    params[param_name] = value
                
                where_clause = " AND ".join(where_conditions)
                
                query_str = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
                result = self.client.execute(text(query_str), params)
                self.client.commit()
                
                return result.rowcount > 0
                
            else:
                raise ValueError("Unknown database client type")
                
        except Exception as e:
            logger.error(f"Database update error: {e}")
            if self.is_sqlalchemy:
                self.client.rollback()
            raise
    
    def close(self):
        """Close database connection if needed"""
        if self.is_sqlalchemy:
            self.client.close()

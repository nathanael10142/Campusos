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
        self._in_filters = {}  # For IN list filters
        self._comparison_filters = {}  # For gt, lt, gte, lte
        
    def select(self, columns: str = "*", count: str = None):
        self._select_columns = columns
        self._count_mode = count  # 'exact' for row count
        return self
        
    def insert(self, data: Dict[str, Any]):
        self._insert_data = data
        return self
        
    def eq(self, column: str, value: Any):
        self._filters[column] = value
        return self
    
    def neq(self, column: str, value: Any):
        """Not equal filter"""
        self._filters[column] = ('neq', value)
        return self
    
    def in_(self, column: str, values: List[Any]):
        """IN filter - column in list of values"""
        self._in_filters[column] = values
        return self
    
    def gt(self, column: str, value: Any):
        """Greater than filter"""
        self._comparison_filters[column] = ('gt', value)
        return self
    
    def lt(self, column: str, value: Any):
        """Less than filter"""
        self._comparison_filters[column] = ('lt', value)
        return self
    
    def gte(self, column: str, value: Any):
        """Greater than or equal filter"""
        self._comparison_filters[column] = ('gte', value)
        return self
    
    def lte(self, column: str, value: Any):
        """Less than or equal filter"""
        self._comparison_filters[column] = ('lte', value)
        return self
        
    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self
        
    def limit(self, count: int):
        self._limit_count = count
        return self
    
    def execute(self):
        if hasattr(self, '_count_mode') and self._count_mode == 'exact':
            # Count mode is for Render.com compatibility
            if self.db_wrapper.is_supabase:
                try:
                    import json
                    query = self.db_wrapper.client.table(self.table).select(
                        self._select_columns, count=self._count_mode
                    )
                    for col, val in self._filters.items():
                        if isinstance(val, tuple) and val[0] == 'neq':
                            query = query.neq(col, val[1])
                        else:
                            query = query.eq(col, val)
                    
                    for col, values in self._in_filters.items():
                        query = query.in_(col, values)
                    
                    for col, comp in self._comparison_filters.items():
                        op, val = comp
                        if op == 'gt':
                            query = query.gt(col, val)
                        elif op == 'lt':
                            query = query.lt(col, val)
                        elif op == 'gte':
                            query = query.gte(col, val)
                        elif op == 'lte':
                            query = query.lte(col, val)
                    
                    if self._order_by:
                        query = query.order(self._order_by, desc=self._order_desc)
                    
                    if self._limit_count:
                        query = query.limit(self._limit_count)
                    
                    result = query.execute()
                    # Return object with count and data
                    class ResultObj:
                        pass
                    r = ResultObj()
                    r.count = result.count if hasattr(result, 'count') else 0
                    r.data = result.data if hasattr(result, 'data') else (result if isinstance(result, list) else [])
                    return r
                except Exception as e:
                    logger.error(f"Count query error: {e}")
                    class ResultObj:
                        pass
                    r = ResultObj()
                    r.count = 0
                    r.data = []
                    return r
        
        if self._insert_data is not None:
            return self.db_wrapper._execute_insert(self.table, self._insert_data)
        else:
            return self.db_wrapper._execute_query(
                table=self.table,
                columns=self._select_columns,
                filters=self._filters,
                in_filters=self._in_filters,
                comparison_filters=self._comparison_filters,
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
                      in_filters: Optional[Dict[str, List[Any]]] = None,
                      comparison_filters: Optional[Dict[str, tuple]] = None,
                      order_by: Optional[str] = None, order_desc: bool = False, limit_count: Optional[int] = None) -> List[Dict]:
        """
        Execute a query with the given parameters
        
        Args:
            table: Table name
            columns: Columns to select
            filters: Dictionary of column: value filters (eq)
            in_filters: Dictionary of column: [values] for IN filters
            comparison_filters: Dictionary of column: (op, value) for gt, lt, gte, lte
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
                        if isinstance(value, tuple) and len(value) == 2 and value[0] == 'neq':
                            query = query.neq(key, value[1])
                        else:
                            query = query.eq(key, value)
                
                if in_filters:
                    for key, values in in_filters.items():
                        query = query.in_(key, values)
                
                if comparison_filters:
                    for key, (op, value) in comparison_filters.items():
                        if op == 'gt':
                            query = query.gt(key, value)
                        elif op == 'lt':
                            query = query.lt(key, value)
                        elif op == 'gte':
                            query = query.gte(key, value)
                        elif op == 'lte':
                            query = query.lte(key, value)
                        
                if order_by:
                    query = query.order(order_by, desc=order_desc)
                    
                if limit_count:
                    query = query.limit(limit_count)
                
                result = query.execute()
                # supabase client may return a raw list or a response object with `.data`
                if isinstance(result, list):
                    return result
                if hasattr(result, "data"):
                    return result.data or []
                try:
                    return list(result)
                except Exception:
                    return []
                
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
    
    def insert(self, table: str, data: Dict[str, Any]) -> Optional[Dict]:
        """
        Convenience method for inserting a record into a table.

        Args:
            table: Table name
            data: Dictionary of column: value pairs to insert

        Returns:
            Inserted record as a dictionary or None
        """
        return self._execute_insert(table, data)
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

                # Normalize different possible Supabase response shapes
                data_payload = None

                # Preferred: response has `.data` attribute
                if hasattr(result, "data"):
                    data_payload = result.data
                # Sometimes result is a dict-like with a 'data' key
                elif isinstance(result, dict) and "data" in result:
                    data_payload = result.get("data")
                # If it's already a list/tuple, use it directly
                elif isinstance(result, (list, tuple)):
                    data_payload = result
                # If it's a response-like object with `.json()` method
                elif hasattr(result, "json") and callable(getattr(result, "json")):
                    try:
                        parsed = result.json()
                        if isinstance(parsed, dict) and "data" in parsed:
                            data_payload = parsed.get("data")
                        else:
                            data_payload = parsed
                    except Exception:
                        data_payload = result
                else:
                    data_payload = result

                # Interpret payload
                if isinstance(data_payload, list):
                    return data_payload[0] if data_payload else None
                if isinstance(data_payload, dict):
                    return data_payload
                if isinstance(data_payload, str):
                    # Try to parse JSON string
                    try:
                        import json
                        parsed = json.loads(data_payload)
                        if isinstance(parsed, list):
                            return parsed[0] if parsed else None
                        if isinstance(parsed, dict):
                            # If top-level dict contains 'data', return it
                            return parsed.get("data") or parsed
                    except Exception:
                        return None

                try:
                    lst = list(data_payload)
                    return lst[0] if lst else None
                except Exception:
                    return None
                
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
                if isinstance(result, list):
                    return len(result) > 0
                if hasattr(result, "data"):
                    return len(result.data) > 0
                try:
                    return len(list(result)) > 0
                except Exception:
                    return False
                
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

"""
Database module for MOC Bot
Handles user data, search history, interactions, and admin functions
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """Database manager for MOC Bot."""
    
    def __init__(self, db_path: str = "mocbot.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with all required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    is_bot INTEGER DEFAULT 0,
                    is_admin INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_searches INTEGER DEFAULT 0,
                    total_exports INTEGER DEFAULT 0
                )
            """)
            
            # Search history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    search_term TEXT NOT NULL,
                    entity_type TEXT DEFAULT 'Companies',
                    results_count INTEGER DEFAULT 0,
                    max_pages INTEGER DEFAULT 10,
                    search_duration REAL,
                    from_cache INTEGER DEFAULT 0,
                    cached INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Search results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    entity_name TEXT,
                    entity_name_khmer TEXT,
                    registration_number TEXT,
                    original_id TEXT,
                    status TEXT,
                    registration_date TEXT,
                    re_registration_date TEXT,
                    entity_type TEXT,
                    address TEXT,
                    tin TEXT,
                    tax_registration_date TEXT,
                    annual_return_date TEXT,
                    details_fetched INTEGER DEFAULT 0,
                    directors_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (search_id) REFERENCES search_history(id)
                )
            """)
            
            # User interactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    interaction_type TEXT NOT NULL,
                    command TEXT,
                    message_text TEXT,
                    callback_data TEXT,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Exports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    search_id INTEGER,
                    export_type TEXT DEFAULT 'csv',
                    filename TEXT,
                    records_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (search_id) REFERENCES search_history(id)
                )
            """)
            
            # Broadcast messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    target_type TEXT DEFAULT 'all',
                    total_users INTEGER DEFAULT 0,
                    successful_sends INTEGER DEFAULT 0,
                    failed_sends INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users(user_id)
                )
            """)
            
            # Admin logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users(user_id)
                )
            """)
            
            # Cached searches table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_term TEXT NOT NULL,
                    search_term_normalized TEXT NOT NULL,
                    entity_type TEXT DEFAULT 'Companies',
                    results_json TEXT NOT NULL,
                    results_count INTEGER NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1,
                    expires_at TIMESTAMP NOT NULL,
                    source TEXT DEFAULT 'live_search',
                    UNIQUE(search_term_normalized, entity_type)
                )
            """)
            
            # Director searches table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS director_searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    search_term TEXT NOT NULL,
                    search_term_normalized TEXT NOT NULL,
                    results_count INTEGER DEFAULT 0,
                    duration REAL,
                    from_cache INTEGER DEFAULT 0,
                    cached INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Director results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS director_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    person_name TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    registration_number TEXT NOT NULL,
                    role TEXT,
                    status TEXT,
                    company_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (search_id) REFERENCES director_searches(id)
                )
            """)
            
            # Cache statistics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL UNIQUE,
                    cache_hits INTEGER DEFAULT 0,
                    cache_misses INTEGER DEFAULT 0,
                    total_searches INTEGER DEFAULT 0,
                    avg_cache_age_hours REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_created ON search_history(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_results_search ON search_results(search_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions(interaction_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exports_user ON exports(user_id)")
            
            # Cache indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cached_search_term ON cached_searches(search_term_normalized)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cached_expires ON cached_searches(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cached_last_accessed ON cached_searches(last_accessed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cached_at ON cached_searches(cached_at DESC)")
            
            # Director search indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_searches_user ON director_searches(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_searches_term ON director_searches(search_term_normalized)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_searches_date ON director_searches(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_results_search ON director_results(search_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_results_company ON director_results(registration_number)")
            
            logger.info("Database initialized successfully")
            
            # Run migrations
            self._run_migrations()
            
            # (Bot standalone: API tables not needed)
    
    def _run_migrations(self):
        """Run database migrations for schema updates."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Migration 1: Add cache status columns to search_history
            try:
                # Check if columns exist
                cursor.execute("PRAGMA table_info(search_history)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'from_cache' not in columns:
                    cursor.execute("ALTER TABLE search_history ADD COLUMN from_cache INTEGER DEFAULT 0")
                    logger.info("Added 'from_cache' column to search_history table")
                
                if 'cached' not in columns:
                    cursor.execute("ALTER TABLE search_history ADD COLUMN cached INTEGER DEFAULT 0")
                    logger.info("Added 'cached' column to search_history table")
                    
            except Exception as e:
                logger.error(f"Migration error: {e}")
            
            # Migration 2: Add last_search_mode to users table
            try:
                cursor.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'last_search_mode' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_search_mode TEXT DEFAULT 'company'")
                    logger.info("Added 'last_search_mode' column to users table")
                    
            except Exception as e:
                logger.error(f"Migration error for last_search_mode: {e}")
    
    # User Management
    def add_or_update_user(self, user_id: int, username: str = None, first_name: str = None, 
                          last_name: str = None, language_code: str = None, is_bot: bool = False):
        """Add new user or update existing user info."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, language_code, is_bot)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    language_code = excluded.language_code,
                    last_active = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name, language_code, int(is_bot)))
    
    def update_user_activity(self, user_id: int):
        """Update user's last active timestamp."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?
            """, (user_id,))
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        user = self.get_user(user_id)
        return user and user['is_admin'] == 1
    
    def set_admin(self, user_id: int, is_admin: bool = True):
        """Set user admin status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_admin = ? WHERE user_id = ?
            """, (int(is_admin), user_id))
    
    def block_user(self, user_id: int, blocked: bool = True):
        """Block or unblock a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_blocked = ? WHERE user_id = ?
            """, (int(blocked), user_id))
    
    def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        user = self.get_user(user_id)
        return user and user['is_blocked'] == 1
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users with pagination."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_stats(self) -> Dict:
        """Get overall user statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END) as total_admins,
                    SUM(CASE WHEN is_blocked = 1 THEN 1 ELSE 0 END) as blocked_users,
                    SUM(CASE WHEN date(last_active) = date('now') THEN 1 ELSE 0 END) as active_today,
                    SUM(CASE WHEN date(last_active) >= date('now', '-7 days') THEN 1 ELSE 0 END) as active_week
                FROM users
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    # Search History Management
    def add_search(self, user_id: int, search_term: str, entity_type: str = 'Companies',
                   results_count: int = 0, max_pages: int = 10, duration: float = 0,
                   from_cache: bool = False, cached: bool = False) -> int:
        """Add search to history and return search_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO search_history 
                (user_id, search_term, entity_type, results_count, max_pages, search_duration, from_cache, cached)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, search_term, entity_type, results_count, max_pages, duration, 
                  int(from_cache), int(cached)))
            
            # Update user's total searches
            cursor.execute("""
                UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?
            """, (user_id,))
            
            return cursor.lastrowid
    
    def add_search_result(self, search_id: int, result_data: Dict):
        """Add a search result to database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Convert directors list to JSON
            directors_json = json.dumps([d.to_dict() for d in result_data.get('directors', [])])
            
            cursor.execute("""
                INSERT INTO search_results 
                (search_id, entity_name, entity_name_khmer, registration_number, original_id,
                 status, registration_date, re_registration_date, entity_type, address,
                 tin, tax_registration_date, annual_return_date, details_fetched, directors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                search_id,
                result_data.get('entity_name'),
                result_data.get('entity_name_khmer'),
                result_data.get('registration_number'),
                result_data.get('original_id'),
                result_data.get('status'),
                result_data.get('registration_date'),
                result_data.get('re_registration_date'),
                result_data.get('entity_type'),
                result_data.get('address'),
                result_data.get('tin'),
                result_data.get('tax_registration_date'),
                result_data.get('annual_return_date'),
                int(bool(result_data.get('directors'))),
                directors_json
            ))

    def update_search_cache_status(self, search_id: int, cached: bool):
        """Update the cache status of a search."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE search_history
                SET cached = ?
                WHERE id = ?
            """, (int(cached), search_id))
    
    def get_user_search_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get user's search history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM search_history 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_search_results(self, search_id: int) -> List[Dict]:
        """Get results for a specific search."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM search_results WHERE search_id = ?
            """, (search_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # Interaction Logging
    def log_interaction(self, user_id: int, interaction_type: str, command: str = None,
                       message_text: str = None, callback_data: str = None, 
                       success: bool = True, error_message: str = None):
        """Log user interaction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO interactions 
                (user_id, interaction_type, command, message_text, callback_data, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, interaction_type, command, message_text, callback_data, int(success), error_message))
    
    def get_user_interactions(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get user's interaction history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM interactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # Export Management
    def add_export(self, user_id: int, search_id: int = None, export_type: str = 'csv',
                   filename: str = None, records_count: int = 0) -> int:
        """Log export activity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO exports 
                (user_id, search_id, export_type, filename, records_count)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, search_id, export_type, filename, records_count))
            
            # Update user's total exports
            cursor.execute("""
                UPDATE users SET total_exports = total_exports + 1 WHERE user_id = ?
            """, (user_id,))
            
            return cursor.lastrowid
    
    # Broadcast Management
    def create_broadcast(self, admin_id: int, message_text: str, target_type: str = 'all') -> int:
        """Create a new broadcast."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count target users
            if target_type == 'all':
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
            elif target_type == 'active':
                cursor.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE is_blocked = 0 AND date(last_active) >= date('now', '-7 days')
                """)
            else:
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
            
            total_users = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO broadcasts (admin_id, message_text, target_type, total_users)
                VALUES (?, ?, ?, ?)
            """, (admin_id, message_text, target_type, total_users))
            
            return cursor.lastrowid
    
    def update_broadcast_status(self, broadcast_id: int, successful: int, failed: int, status: str = 'completed'):
        """Update broadcast status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broadcasts 
                SET successful_sends = ?, failed_sends = ?, status = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (successful, failed, status, broadcast_id))
    
    def get_broadcast_targets(self, target_type: str = 'all') -> List[int]:
        """Get list of user IDs for broadcast."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if target_type == 'all':
                cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            elif target_type == 'active':
                cursor.execute("""
                    SELECT user_id FROM users 
                    WHERE is_blocked = 0 AND date(last_active) >= date('now', '-7 days')
                """)
            else:
                cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            
            return [row[0] for row in cursor.fetchall()]
    
    def get_broadcasts(self, limit: int = 20) -> List[Dict]:
        """Get broadcast history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.*, u.username as admin_username 
                FROM broadcasts b
                LEFT JOIN users u ON b.admin_id = u.user_id
                ORDER BY b.created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # Admin Logging
    def log_admin_action(self, admin_id: int, action: str, target_user_id: int = None, details: str = None):
        """Log admin action."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_logs (admin_id, action, target_user_id, details)
                VALUES (?, ?, ?, ?)
            """, (admin_id, action, target_user_id, details))
    
    def get_admin_logs(self, limit: int = 100) -> List[Dict]:
        """Get admin action logs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT al.*, u.username as admin_username
                FROM admin_logs al
                LEFT JOIN users u ON al.admin_id = u.user_id
                ORDER BY al.created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # Statistics and Analytics
    def get_search_stats(self) -> Dict:
        """Get search statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_searches,
                    SUM(results_count) as total_results,
                    AVG(results_count) as avg_results_per_search,
                    AVG(search_duration) as avg_duration,
                    COUNT(DISTINCT user_id) as unique_users,
                    SUM(CASE WHEN date(created_at) = date('now') THEN 1 ELSE 0 END) as searches_today,
                    SUM(CASE WHEN date(created_at) >= date('now', '-7 days') THEN 1 ELSE 0 END) as searches_week
                FROM search_history
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def get_popular_searches(self, limit: int = 10) -> List[Dict]:
        """Get most popular search terms."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT search_term, COUNT(*) as search_count
                FROM search_history
                GROUP BY LOWER(search_term)
                ORDER BY search_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_database_size(self) -> Dict:
        """Get database size information."""
        try:
            db_size = Path(self.db_path).stat().st_size
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get table counts
                tables = ['users', 'search_history', 'search_results', 'interactions', 
                         'exports', 'broadcasts', 'admin_logs']
                
                counts = {}
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    counts[f"{table}_count"] = cursor.fetchone()[0]
                
                return {
                    'size_bytes': db_size,
                    'size_mb': round(db_size / (1024 * 1024), 2),
                    'size_gb': round(db_size / (1024 * 1024 * 1024), 4),
                    **counts
                }
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return {}

    # Cache Management Methods
    def get_cached_search(self, search_term: str, entity_type: str = "Companies") -> Optional['CachedSearch']:
        """
        Retrieve cached search from database
        
        Returns:
            CachedSearch object if found and not expired, None otherwise
        """
        from .cache_manager import CachedSearch
        
        normalized = search_term.lower().strip()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cached_searches
                WHERE search_term_normalized = ?
                  AND entity_type = ?
                  AND expires_at > datetime('now')
                LIMIT 1
            """, (normalized, entity_type))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return CachedSearch(
                id=row['id'],
                search_term=row['search_term'],
                search_term_normalized=row['search_term_normalized'],
                entity_type=row['entity_type'],
                results_json=row['results_json'],
                results_count=row['results_count'],
                cached_at=datetime.fromisoformat(row['cached_at']),
                last_accessed=datetime.fromisoformat(row['last_accessed']),
                access_count=row['access_count'],
                expires_at=datetime.fromisoformat(row['expires_at']),
                source=row['source']
            )
    
    def store_cached_search(
        self,
        search_term: str,
        entity_type: str,
        results_json: str,
        results_count: int,
        expires_at: datetime,
        source: str = "live_search"
    ) -> Optional[int]:
        """
        Store search results in cache
        
        Returns:
            Cache entry ID or None on error
        """
        normalized = search_term.lower().strip()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO cached_searches 
                    (search_term, search_term_normalized, entity_type, results_json, 
                     results_count, expires_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(search_term_normalized, entity_type) DO UPDATE SET
                        search_term = excluded.search_term,
                        results_json = excluded.results_json,
                        results_count = excluded.results_count,
                        cached_at = CURRENT_TIMESTAMP,
                        last_accessed = CURRENT_TIMESTAMP,
                        access_count = 1,
                        expires_at = excluded.expires_at,
                        source = excluded.source
                """, (search_term, normalized, entity_type, results_json, 
                      results_count, expires_at.isoformat(), source))
                
                # Get the ID of the inserted or updated row
                if cursor.lastrowid:
                    return cursor.lastrowid
                else:
                    # If lastrowid is 0 (UPDATE case), fetch the ID
                    cursor.execute("""
                        SELECT id FROM cached_searches 
                        WHERE search_term_normalized = ? AND entity_type = ?
                    """, (normalized, entity_type))
                    row = cursor.fetchone()
                    return row[0] if row else None
            except Exception as e:
                logger.error(f"Error storing cached search: {e}")
                return None
    
    def update_cache_access(self, cache_id: int) -> bool:
        """
        Update last_accessed timestamp and increment access_count
        
        Returns:
            True if updated successfully
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE cached_searches
                SET last_accessed = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ?
            """, (cache_id,))
            return cursor.rowcount > 0
    
    def delete_cached_search(self, cache_id: int) -> bool:
        """Delete a specific cached search"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cached_searches WHERE id = ?", (cache_id,))
            return cursor.rowcount > 0
    
    def delete_expired_cache(self) -> int:
        """
        Delete all expired cache entries
        
        Returns:
            Number of entries deleted
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM cached_searches
                WHERE expires_at < datetime('now')
            """)
            return cursor.rowcount
    
    def clear_cache(self, search_term: Optional[str] = None) -> int:
        """
        Clear cache entries
        
        Args:
            search_term: Specific term to clear, or None for all
        
        Returns:
            Number of entries cleared
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if search_term:
                normalized = search_term.lower().strip()
                cursor.execute("""
                    DELETE FROM cached_searches
                    WHERE search_term_normalized = ?
                """, (normalized,))
            else:
                cursor.execute("DELETE FROM cached_searches")
            
            return cursor.rowcount
    
    def evict_lru_cache(self, max_entries: int) -> int:
        """
        Evict least recently used cache entries if over limit
        
        Args:
            max_entries: Maximum number of cache entries to keep
        
        Returns:
            Number of entries evicted
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check current count
            cursor.execute("SELECT COUNT(*) FROM cached_searches")
            current_count = cursor.fetchone()[0]
            
            if current_count <= max_entries:
                return 0
            
            # Delete oldest accessed entries
            entries_to_delete = current_count - max_entries
            cursor.execute("""
                DELETE FROM cached_searches
                WHERE id IN (
                    SELECT id FROM cached_searches
                    ORDER BY last_accessed ASC
                    LIMIT ?
                )
            """, (entries_to_delete,))
            
            return cursor.rowcount
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache metrics
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get basic stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_entries,
                    SUM(results_count) as total_results,
                    AVG(results_count) as avg_results_per_search,
                    SUM(access_count) as total_accesses,
                    AVG(access_count) as avg_accesses_per_entry,
                    AVG((julianday('now') - julianday(cached_at)) * 24) as avg_age_hours,
                    MAX((julianday('now') - julianday(cached_at)) * 24) as max_age_hours,
                    SUM(LENGTH(results_json)) as total_json_size
                FROM cached_searches
            """)
            
            row = cursor.fetchone()
            
            # Get most popular searches
            cursor.execute("""
                SELECT search_term, access_count, results_count
                FROM cached_searches
                ORDER BY access_count DESC
                LIMIT 10
            """)
            
            popular = [
                {
                    'search_term': r['search_term'],
                    'access_count': r['access_count'],
                    'results_count': r['results_count']
                }
                for r in cursor.fetchall()
            ]
            
            return {
                'total_entries': row['total_entries'] or 0,
                'total_results': row['total_results'] or 0,
                'avg_results_per_search': round(row['avg_results_per_search'] or 0, 1),
                'total_accesses': row['total_accesses'] or 0,
                'avg_accesses_per_entry': round(row['avg_accesses_per_entry'] or 0, 1),
                'avg_age_hours': round(row['avg_age_hours'] or 0, 1),
                'max_age_hours': round(row['max_age_hours'] or 0, 1),
                'cache_size_mb': round((row['total_json_size'] or 0) / (1024 * 1024), 2),
                'popular_searches': popular
            }

    # Director Search Management Methods
    def add_director_search(
        self, 
        user_id: int, 
        search_term: str,
        results_count: int = 0,
        duration: float = 0,
        from_cache: bool = False,
        cached: bool = False
    ) -> int:
        """
        Add director search to history and return search_id.
        
        Args:
            user_id: User ID performing the search
            search_term: Director name searched
            results_count: Number of companies found
            duration: Search duration in seconds
            from_cache: Whether results came from cache
            cached: Whether results were stored in cache
            
        Returns:
            search_id of the inserted record
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            normalized = search_term.lower().strip()
            
            cursor.execute("""
                INSERT INTO director_searches 
                (user_id, search_term, search_term_normalized, results_count, duration, from_cache, cached)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, search_term, normalized, results_count, duration, 
                  int(from_cache), int(cached)))
            
            # Update user's total searches
            cursor.execute("""
                UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?
            """, (user_id,))
            
            return cursor.lastrowid
    
    def add_director_result(self, search_id: int, result_data: Dict):
        """
        Add a director search result to database.
        
        Args:
            search_id: ID of the director search
            result_data: Dictionary with result fields
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO director_results 
                (search_id, person_name, company_name, registration_number, role, status, company_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                search_id,
                result_data.get('person_name'),
                result_data.get('company_name'),
                result_data.get('registration_number'),
                result_data.get('role'),
                result_data.get('status'),
                result_data.get('company_type', '')
            ))
    
    def update_director_search_cache_status(self, search_id: int, cached: bool):
        """
        Update the cache status of a director search.
        
        Args:
            search_id: ID of the director search
            cached: Whether results were cached
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE director_searches
                SET cached = ?
                WHERE id = ?
            """, (int(cached), search_id))
    
    def get_director_searches(
        self, 
        user_id: Optional[int] = None,
        limit: int = 20,
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get director search history.
        
        Args:
            user_id: Filter by user ID (None for all users)
            limit: Maximum number of results
            since: Filter searches after this datetime
            
        Returns:
            List of director search records
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM director_searches WHERE 1=1"
            params = []
            
            if user_id is not None:
                query += " AND user_id = ?"
                params.append(user_id)
            
            if since is not None:
                query += " AND created_at >= ?"
                params.append(since.isoformat())
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_director_results(self, search_id: int) -> List[Dict]:
        """
        Get results for a specific director search.
        
        Args:
            search_id: ID of the director search
            
        Returns:
            List of director result records
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM director_results WHERE search_id = ?
            """, (search_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_director_search_stats(self) -> Dict:
        """
        Get director search statistics.
        
        Returns:
            Dictionary with director search metrics
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_searches,
                    SUM(results_count) as total_results,
                    AVG(results_count) as avg_results_per_search,
                    AVG(duration) as avg_duration,
                    COUNT(DISTINCT user_id) as unique_users,
                    SUM(CASE WHEN from_cache = 1 THEN 1 ELSE 0 END) as cache_hits,
                    SUM(CASE WHEN date(created_at) = date('now') THEN 1 ELSE 0 END) as searches_today,
                    SUM(CASE WHEN date(created_at) >= date('now', '-7 days') THEN 1 ELSE 0 END) as searches_week
                FROM director_searches
            """)
            row = cursor.fetchone()
            
            stats = dict(row) if row else {}
            
            # Calculate cache hit rate
            if stats.get('total_searches', 0) > 0:
                stats['cache_hit_rate'] = round(
                    (stats.get('cache_hits', 0) / stats['total_searches']) * 100, 1
                )
            else:
                stats['cache_hit_rate'] = 0.0
            
            return stats
    
    def get_popular_directors(self, limit: int = 10) -> List[Dict]:
        """
        Get most searched directors.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of popular director searches
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    search_term,
                    COUNT(*) as search_count,
                    AVG(results_count) as avg_results
                FROM director_searches
                GROUP BY search_term_normalized
                ORDER BY search_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_user_search_mode(self, user_id: int, mode: str):
        """
        Update user's last search mode preference.
        
        Args:
            user_id: User ID
            mode: Search mode ('company' or 'director')
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_search_mode = ? WHERE user_id = ?
            """, (mode, user_id))
    
    def get_user_search_mode(self, user_id: int) -> str:
        """
        Get user's last search mode preference.
        
        Args:
            user_id: User ID
            
        Returns:
            Search mode ('company' or 'director'), defaults to 'company'
        """
        user = self.get_user(user_id)
        if user and 'last_search_mode' in user:
            return user['last_search_mode'] or 'company'
        return 'company'

    def vacuum_database(self) -> bool:
        """
        Vacuum the database to reclaim space and optimize performance

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("VACUUM")
                logger.info("Database vacuumed successfully")
                return True
        except Exception as e:
            logger.error(f"Error vacuuming database: {e}")
            return False


# (Bot standalone: mixins not needed)

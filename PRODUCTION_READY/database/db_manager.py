"""
Smart Door Security System - Production Database Manager
Thread-safe database operations with connection pooling, security measures, and performance optimization.
"""

import sqlite3
import threading
import hashlib
import pickle
import bcrypt
import secrets
import logging
import time
import json
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from contextlib import contextmanager
import sys
from collections import defaultdict
import queue

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DATABASE_PATH

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """Thread-safe connection pool for database operations."""
    
    def __init__(self, db_path: str, max_connections: int = 10):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool = queue.Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        self._active_connections = 0
        
        # Initialize pool with connections
        for _ in range(max_connections):
            conn = self._create_connection()
            self._pool.put(conn)
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
        conn.execute("PRAGMA synchronous = NORMAL")  # Balance safety and speed
        conn.execute("PRAGMA cache_size = 10000")  # 10MB cache
        return conn
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        conn = None
        try:
            # Try to get connection from pool with timeout
            conn = self._pool.get(timeout=5.0)
            yield conn
        except queue.Empty:
            # Pool exhausted, create temporary connection
            conn = self._create_connection()
            yield conn
        finally:
            if conn:
                try:
                    conn.commit()
                    self._pool.put(conn, block=False)
                except queue.Full:
                    # Pool full, close connection
                    conn.close()
    
    def close_all(self):
        """Close all connections in the pool."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break


class SecureDatabaseManager:
    """Production-ready database manager with security and performance features."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the secure database manager."""
        if self._initialized:
            return
        
        self.db_path = DATABASE_PATH
        self._pool = DatabaseConnectionPool(str(self.db_path))
        self._initialized = True
        self._init_database()
        
        # Performance monitoring
        self._query_stats = defaultdict(int)
        self._connection_stats = {'created': 0, 'closed': 0}
        
        logger.info("Secure database manager initialized")
    
    def _init_database(self):
        """Initialize database with schema and security measures."""
        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema = f.read()
            
            with self._pool.get_connection() as conn:
                conn.executescript(schema)
            
            # Create additional security indexes
            self._create_security_indexes()
            
            # Create audit triggers
            self._create_audit_triggers()
            
            logger.info("Database initialized with security features")
        else:
            logger.error(f"Schema file not found: {schema_path}")
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    def _create_security_indexes(self):
        """Create indexes for security and performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_admin_username ON admin(username);",
            "CREATE INDEX IF NOT EXISTS idx_admin_active ON admin(is_active);",
            "CREATE INDEX IF NOT EXISTS idx_users_employee_active ON users(employee_id, is_active);",
            "CREATE INDEX IF NOT EXISTS idx_access_logs_user_date ON access_logs(user_id, access_date);",
            "CREATE INDEX IF NOT EXISTS idx_access_logs_result ON access_logs(result);",
            "CREATE INDEX IF NOT EXISTS idx_system_logs_level_time ON system_logs(log_level, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_fingerprint_user ON fingerprint_data(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_face_encodings_user ON face_encodings(user_id);"
        ]
        
        with self._pool.get_connection() as conn:
            for index_sql in indexes:
                try:
                    conn.execute(index_sql)
                except sqlite3.OperationalError as e:
                    if "already exists" not in str(e):
                        logger.warning(f"Index creation failed: {e}")
        
        logger.info("Security indexes created")
    
    def _create_audit_triggers(self):
        """Create audit triggers for security monitoring."""
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS audit_admin_login
            AFTER UPDATE ON admin
            FOR EACH ROW
            WHEN NEW.last_login != OLD.last_login
            BEGIN
                INSERT INTO system_logs (log_level, module, message, details)
                VALUES ('INFO', 'Auth', 'Admin login', 'User: ' || NEW.username);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS audit_user_changes
            AFTER UPDATE ON users
            FOR EACH ROW
            BEGIN
                INSERT INTO system_logs (log_level, module, message, details)
                VALUES ('INFO', 'UserManagement', 'User updated', 
                       'User ID: ' || NEW.id || ', Active: ' || NEW.is_active);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS audit_access_denied
            AFTER INSERT ON access_logs
            FOR EACH ROW
            WHEN NEW.result = 'DENIED'
            BEGIN
                INSERT INTO system_logs (log_level, module, message, details)
                VALUES ('WARNING', 'AccessControl', 'Access denied', 
                       'User: ' || NEW.user_name || ', Reason: ' || NEW.failure_reason);
            END;
            """
        ]
        
        with self._pool.get_connection() as conn:
            for trigger_sql in triggers:
                try:
                    conn.execute(trigger_sql)
                except sqlite3.OperationalError as e:
                    if "already exists" not in str(e):
                        logger.warning(f"Trigger creation failed: {e}")
        
        logger.info("Audit triggers created")
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        with self._pool.get_connection() as conn:
            yield conn
    
    def execute(self, query: str, params: tuple = (), log_query: bool = False) -> sqlite3.Cursor:
        """Execute a query with security and performance monitoring."""
        start_time = time.time()
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                # Log slow queries
                execution_time = time.time() - start_time
                if execution_time > 0.1:  # Log queries slower than 100ms
                    logger.warning(f"Slow query detected: {execution_time:.3f}s - {query[:100]}")
                
                return cursor
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise
    
    def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """Execute a query with multiple parameter sets."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
        except sqlite3.Error as e:
            logger.error(f"Database error in execute_many: {e}")
            raise
    
    def execute_transaction(self, queries: List[Tuple[str, tuple]]) -> bool:
        """Execute multiple queries in a transaction."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for query, params in queries:
                    cursor.execute(query, params)
                return True
        except sqlite3.Error as e:
            logger.error(f"Transaction failed: {e}")
            return False
    
    def commit(self):
        """Commit current transaction."""
        # Connection pool handles auto-commit
        pass
    
    def rollback(self):
        """Rollback current transaction."""
        # Connection pool handles rollback on exception
        pass
    
    def close(self):
        """Close all connections."""
        self._pool.close_all()
        logger.info("Database connections closed")


class SecureAdminRepository:
    """Secure repository for admin operations with enhanced security."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def get_by_username(self, username: str) -> Optional[Dict]:
        """Get admin by username with security logging."""
        try:
            cursor = self.db.execute(
                "SELECT * FROM admin WHERE username = ? AND is_active = 1",
                (username,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving admin by username: {e}")
            return None
    
    def get_by_id(self, admin_id: int) -> Optional[Dict]:
        """Get admin by ID with security logging."""
        try:
            cursor = self.db.execute(
                "SELECT * FROM admin WHERE id = ? AND is_active = 1",
                (admin_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving admin by ID: {e}")
            return None
    
    def create_admin(self, username: str, password: str, email: str, full_name: str) -> bool:
        """Create a new admin with secure password hashing."""
        try:
            # Hash password with high cost factor
            password_hash = bcrypt.hashpw(
                password.encode('utf-8'), 
                bcrypt.gensalt(rounds=12)  # High cost factor for security
            ).decode('utf-8')
            
            cursor = self.db.execute(
                """INSERT INTO admin (username, password_hash, email, full_name)
                   VALUES (?, ?, ?, ?)""",
                (username, password_hash, email, full_name)
            )
            
            logger.info(f"Admin created: {username}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Admin creation failed - username/email already exists: {username}")
            return False
        except Exception as e:
            logger.error(f"Error creating admin: {e}")
            return False
    
    def verify_password(self, username: str, password: str) -> Optional[Dict]:
        """Verify admin password with timing attack protection."""
        admin = self.get_by_username(username)
        if not admin:
            # Constant time comparison to prevent timing attacks
            bcrypt.checkpw(b"dummy", b"dummy")
            return None
        
        try:
            if bcrypt.checkpw(password.encode('utf-8'), admin['password_hash'].encode('utf-8')):
                return admin
            else:
                return None
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return None
    
    def update_last_login(self, admin_id: int):
        """Update last login timestamp with security audit."""
        try:
            self.db.execute(
                "UPDATE admin SET last_login = ?, updated_at = ? WHERE id = ?",
                (datetime.now(), datetime.now(), admin_id)
            )
            
            # Log successful login
            admin = self.get_by_id(admin_id)
            if admin:
                logger.info(f"Admin login: {admin['username']}")
        except Exception as e:
            logger.error(f"Error updating last login: {e}")
    
    def create_session(self, admin_id: int, expires_minutes: int = 480) -> str:
        """Create a secure admin session."""
        try:
            # Generate cryptographically secure session token
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(minutes=expires_minutes)
            
            self.db.execute(
                """INSERT INTO admin_sessions (admin_id, session_token, expires_at)
                   VALUES (?, ?, ?)""",
                (admin_id, session_token, expires_at)
            )
            
            return session_token
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return ""
    
    def get_session(self, token: str) -> Optional[Dict]:
        """Get session by token with security validation."""
        try:
            cursor = self.db.execute(
                """SELECT s.*, a.username, a.full_name 
                   FROM admin_sessions s
                   JOIN admin a ON s.admin_id = a.id
                   WHERE s.session_token = ? AND s.expires_at > ? AND a.is_active = 1""",
                (token, datetime.now())
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving session: {e}")
            return None
    
    def delete_session(self, token: str):
        """Delete a session."""
        try:
            self.db.execute("DELETE FROM admin_sessions WHERE session_token = ?", (token,))
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        try:
            self.db.execute("DELETE FROM admin_sessions WHERE expires_at < ?", (datetime.now(),))
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")


class SecureUserRepository:
    """Secure repository for user operations with validation."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def create(self, employee_id: str, first_name: str, last_name: str,
               email: str = None, phone: str = None, department: str = None,
               designation: str = None, created_by: int = None) -> int:
        """Create a new user with validation."""
        # Input validation
        if not self._validate_user_input(employee_id, first_name, last_name):
            raise ValueError("Invalid user input")
        
        try:
            cursor = self.db.execute(
                """INSERT INTO users (employee_id, first_name, last_name, email, phone, 
                                      department, designation, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (employee_id, first_name, last_name, email, phone, department, designation, created_by)
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            if "employee_id" in str(e):
                raise ValueError("Employee ID already exists")
            raise e
    
    def _validate_user_input(self, employee_id: str, first_name: str, last_name: str) -> bool:
        """Validate user input for security."""
        # Basic validation
        if not employee_id or not first_name or not last_name:
            return False
        
        # Length validation
        if len(employee_id) > 50 or len(first_name) > 50 or len(last_name) > 50:
            return False
        
        # Character validation (prevent SQL injection)
        import re
        if not re.match(r'^[a-zA-Z0-9\-_]+$', employee_id):
            return False
        if not re.match(r'^[a-zA-Z\s]+$', first_name):
            return False
        if not re.match(r'^[a-zA-Z\s]+$', last_name):
            return False
        
        return True
    
    def get_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID."""
        try:
            cursor = self.db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving user by ID: {e}")
            return None
    
    def get_by_employee_id(self, employee_id: str) -> Optional[Dict]:
        """Get user by employee ID."""
        try:
            cursor = self.db.execute(
                "SELECT * FROM users WHERE employee_id = ?",
                (employee_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving user by employee ID: {e}")
            return None
    
    def get_all(self, active_only: bool = False, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users with pagination."""
        try:
            query = "SELECT * FROM users"
            params = []
            
            if active_only:
                query += " WHERE is_active = 1"
            
            query += " ORDER BY first_name, last_name LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = self.db.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving users: {e}")
            return []
    
    def update(self, user_id: int, **kwargs) -> bool:
        """Update user with validation."""
        if not kwargs:
            return False
        
        # Validate input
        allowed_fields = ['first_name', 'last_name', 'email', 'phone', 
                          'department', 'designation', 'is_active',
                          'face_enrolled', 'fingerprint_enrolled']
        
        updates = []
        values = []
        for key, value in kwargs.items():
            if key in allowed_fields and self._validate_field(key, value):
                updates.append(f"{key} = ?")
                values.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        values.extend([datetime.now(), user_id])
        
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        
        try:
            self.db.execute(query, tuple(values))
            return True
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False
    
    def _validate_field(self, field: str, value: Any) -> bool:
        """Validate individual field."""
        if value is None:
            return True
        
        if field in ['first_name', 'last_name']:
            return isinstance(value, str) and len(value) <= 50
        elif field == 'email':
            return value is None or (isinstance(value, str) and len(value) <= 100)
        elif field == 'phone':
            return value is None or (isinstance(value, str) and len(value) <= 20)
        elif field in ['department', 'designation']:
            return value is None or (isinstance(value, str) and len(value) <= 100)
        elif field in ['is_active', 'face_enrolled', 'fingerprint_enrolled']:
            return isinstance(value, bool)
        
        return False
    
    def delete(self, user_id: int) -> bool:
        """Delete a user (cascades to face and fingerprint data)."""
        try:
            self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False
    
    def set_active(self, user_id: int, is_active: bool) -> bool:
        """Enable or disable a user."""
        try:
            self.db.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (is_active, datetime.now(), user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user status: {e}")
            return False


class SecureFaceEncodingRepository:
    """Secure repository for face encoding operations."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def save_encoding(self, user_id: int, encoding_array, num_samples: int = 1,
                      quality_score: float = 0.0) -> bool:
        """Save face encoding with security measures."""
        try:
            # Serialize numpy array securely
            encoding_bytes = pickle.dumps(encoding_array)
            encoding_hash = hashlib.sha256(encoding_bytes).hexdigest()
            
            # Check if encoding exists
            cursor = self.db.execute(
                "SELECT id FROM face_encodings WHERE user_id = ?",
                (user_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing
                self.db.execute(
                    """UPDATE face_encodings 
                       SET encoding_data = ?, encoding_hash = ?, num_samples = ?, 
                           quality_score = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (sqlite3.Binary(encoding_bytes), encoding_hash, num_samples, 
                     quality_score, datetime.now(), user_id)
                )
            else:
                # Insert new
                self.db.execute(
                    """INSERT INTO face_encodings (user_id, encoding_data, encoding_hash, 
                                                   num_samples, quality_score)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, sqlite3.Binary(encoding_bytes), encoding_hash, 
                     num_samples, quality_score)
                )
            
            # Update user's face_enrolled status
            self.db.execute(
                "UPDATE users SET face_enrolled = 1, updated_at = ? WHERE id = ?",
                (datetime.now(), user_id)
            )
            
            return True
        except Exception as e:
            logger.error(f"Error saving face encoding: {e}")
            return False
    
    def get_encoding(self, user_id: int) -> Optional[Any]:
        """Get face encoding for a user."""
        try:
            cursor = self.db.execute(
                "SELECT encoding_data FROM face_encodings WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return pickle.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"Error retrieving face encoding: {e}")
            return None
    
    def get_all_encodings(self) -> List[Dict]:
        """Get all face encodings with user IDs."""
        try:
            cursor = self.db.execute(
                """SELECT fe.user_id, fe.encoding_data, u.first_name, u.last_name, u.employee_id
                   FROM face_encodings fe
                   JOIN users u ON fe.user_id = u.id
                   WHERE u.is_active = 1"""
            )
            results = []
            for row in cursor.fetchall():
                encoding = pickle.loads(row[1])
                results.append({
                    'user_id': row[0],
                    'encoding': encoding,
                    'name': f"{row[2]} {row[3]}",
                    'employee_id': row[4]
                })
            return results
        except Exception as e:
            logger.error(f"Error retrieving face encodings: {e}")
            return []
    
    def delete_encoding(self, user_id: int) -> bool:
        """Delete face encoding for a user."""
        try:
            self.db.execute("DELETE FROM face_encodings WHERE user_id = ?", (user_id,))
            self.db.execute(
                "UPDATE users SET face_enrolled = 0, updated_at = ? WHERE id = ?",
                (datetime.now(), user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting face encoding: {e}")
            return False


class SecureFingerprintRepository:
    """Secure repository for fingerprint data operations."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def save_fingerprint(self, user_id: int, fingerprint_id: int,
                         template_hash: str, finger_position: str = 'right_index') -> bool:
        """Save fingerprint data with security measures."""
        try:
            # Check if exists
            cursor = self.db.execute(
                "SELECT id FROM fingerprint_data WHERE user_id = ?",
                (user_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                self.db.execute(
                    """UPDATE fingerprint_data 
                       SET fingerprint_id = ?, template_hash = ?, finger_position = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (fingerprint_id, template_hash, finger_position, datetime.now(), user_id)
                )
            else:
                self.db.execute(
                    """INSERT INTO fingerprint_data (user_id, fingerprint_id, template_hash, finger_position)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, fingerprint_id, template_hash, finger_position)
                )
            
            # Update user's fingerprint_enrolled status
            self.db.execute(
                "UPDATE users SET fingerprint_enrolled = 1, updated_at = ? WHERE id = ?",
                (datetime.now(), user_id)
            )
            
            return True
        except Exception as e:
            logger.error(f"Error saving fingerprint: {e}")
            return False
    
    def get_by_fingerprint_id(self, fingerprint_id: int) -> Optional[Dict]:
        """Get user by fingerprint sensor ID."""
        try:
            cursor = self.db.execute(
                """SELECT fd.*, u.first_name, u.last_name, u.employee_id, u.is_active
                   FROM fingerprint_data fd
                   JOIN users u ON fd.user_id = u.id
                   WHERE fd.fingerprint_id = ?""",
                (fingerprint_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving fingerprint by ID: {e}")
            return None
    
    def get_by_user_id(self, user_id: int) -> Optional[Dict]:
        """Get fingerprint data by user ID."""
        try:
            cursor = self.db.execute(
                "SELECT * FROM fingerprint_data WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving fingerprint by user ID: {e}")
            return None
    
    def get_all_fingerprints(self) -> List[Dict]:
        """Get all fingerprint mappings."""
        try:
            cursor = self.db.execute(
                """SELECT fd.fingerprint_id, fd.user_id, u.first_name, u.last_name, u.employee_id
                   FROM fingerprint_data fd
                   JOIN users u ON fd.user_id = u.id
                   WHERE u.is_active = 1"""
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving fingerprints: {e}")
            return []
    
    def delete_fingerprint(self, user_id: int) -> bool:
        """Delete fingerprint data for a user."""
        try:
            self.db.execute("DELETE FROM fingerprint_data WHERE user_id = ?", (user_id,))
            self.db.execute(
                "UPDATE users SET fingerprint_enrolled = 0, updated_at = ? WHERE id = ?",
                (datetime.now(), user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting fingerprint: {e}")
            return False


class SecureAccessLogRepository:
    """Secure repository for access log operations with performance optimization."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def log_access(self, user_id: Optional[int], event_type: str, result: str,
                   face_match: bool = False, fingerprint_match: bool = False,
                   failure_reason: str = None, confidence_score: float = None,
                   ip_address: str = None) -> bool:
        """Log an access attempt with security audit."""
        try:
            now = datetime.now()
            
            # Get user info if available
            employee_id = None
            user_name = None
            if user_id:
                user_repo = SecureUserRepository()
                user = user_repo.get_by_id(user_id)
                if user:
                    employee_id = user['employee_id']
                    user_name = f"{user['first_name']} {user['last_name']}"
            
            self.db.execute(
                """INSERT INTO access_logs 
                   (user_id, employee_id, user_name, event_type, access_date, access_time,
                    result, face_match, fingerprint_match, failure_reason, confidence_score, ip_address)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, employee_id, user_name, event_type, now.date(), now.time().isoformat(),
                 result, face_match, fingerprint_match, failure_reason, confidence_score, ip_address)
            )
            
            # Log security events
            if result == 'DENIED':
                logger.warning(f"Access denied: {user_name or 'Unknown'} - {failure_reason}")
            
            return True
        except Exception as e:
            logger.error(f"Error logging access: {e}")
            return False
    
    def get_logs(self, start_date: date = None, end_date: date = None,
                 user_id: int = None, result: str = None, 
                 limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get access logs with filters and pagination."""
        try:
            query = "SELECT * FROM access_logs WHERE 1=1"
            params = []
            
            if start_date:
                query += " AND access_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND access_date <= ?"
                params.append(end_date)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            if result:
                query += " AND result = ?"
                params.append(result)
            
            query += " ORDER BY access_date DESC, access_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = self.db.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving access logs: {e}")
            return []
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """Get most recent logs."""
        try:
            cursor = self.db.execute(
                """SELECT * FROM access_logs 
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving recent logs: {e}")
            return []
    
    def get_stats(self, days: int = 7) -> Dict:
        """Get access statistics for the last N days."""
        try:
            cursor = self.db.execute(
                """SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN result = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN result = 'DENIED' THEN 1 ELSE 0 END) as denied
                   FROM access_logs
                   WHERE access_date >= date('now', ?)""",
                (f'-{days} days',)
            )
            row = cursor.fetchone()
            return dict(row) if row else {'total': 0, 'successful': 0, 'failed': 0, 'denied': 0}
        except Exception as e:
            logger.error(f"Error retrieving statistics: {e}")
            return {'total': 0, 'successful': 0, 'failed': 0, 'denied': 0}


class SecureSystemLogRepository:
    """Secure repository for system log operations."""
    
    def __init__(self):
        self.db = SecureDatabaseManager()
    
    def log(self, level: str, module: str, message: str, details: str = None):
        """Log a system event with security filtering."""
        # Filter sensitive information
        safe_message = self._filter_sensitive_data(message)
        safe_details = self._filter_sensitive_data(details) if details else None
        
        try:
            self.db.execute(
                "INSERT INTO system_logs (log_level, module, message, details) VALUES (?, ?, ?, ?)",
                (level, module, safe_message, safe_details)
            )
        except Exception as e:
            logger.error(f"Error logging system event: {e}")
    
    def _filter_sensitive_data(self, text: str) -> str:
        """Filter sensitive information from log messages."""
        if not text:
            return text
        
        import re
        # Remove potential sensitive patterns
        text = re.sub(r'password\s*=\s*[^&\s]+', 'password=*****', text, flags=re.IGNORECASE)
        text = re.sub(r'token\s*=\s*[^&\s]+', 'token=*****', text, flags=re.IGNORECASE)
        text = re.sub(r'key\s*=\s*[^&\s]+', 'key=*****', text, flags=re.IGNORECASE)
        
        return text
    
    def info(self, module: str, message: str, details: str = None):
        self.log('INFO', module, message, details)
    
    def warning(self, module: str, message: str, details: str = None):
        self.log('WARNING', module, message, details)
    
    def error(self, module: str, message: str, details: str = None):
        self.log('ERROR', module, message, details)
    
    def get_logs(self, level: str = None, module: str = None, 
                 limit: int = 100) -> List[Dict]:
        """Get system logs with filters."""
        try:
            query = "SELECT * FROM system_logs WHERE 1=1"
            params = []
            
            if level:
                query += " AND log_level = ?"
                params.append(level)
            if module:
                query += " AND module = ?"
                params.append(module)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = self.db.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving system logs: {e}")
            return []


# Initialize database on import
if __name__ == "__main__":
    db = SecureDatabaseManager()
    print(f"Secure database initialized at: {DATABASE_PATH}")
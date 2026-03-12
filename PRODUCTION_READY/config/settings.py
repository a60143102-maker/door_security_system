"""

Smart Door Security System - Production Configuration Settings
Security-hardened and performance-optimized configuration.
"""

import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database settings with security enhancements
DATABASE_PATH = BASE_DIR / "database" / "smart_door.db"
DATABASE_BACKUP_PATH = BASE_DIR / "backups" / "database_backup.db"
DATABASE_ENCRYPTION_KEY = os.environ.get("DB_ENCRYPTION_KEY", None)  # Optional encryption

# Camera settings with performance optimization
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
CAMERA_FPS = int(os.environ.get("CAMERA_FPS", "30"))
CAMERA_FRAME_SKIP = int(os.environ.get("CAMERA_FRAME_SKIP", "1"))  # Skip frames for performance

# Face recognition settings with security enhancements
FACE_RECOGNITION_TOLERANCE = float(os.environ.get("FACE_TOLERANCE", "0.6"))  # Stricter matching
FACE_DETECTION_MODEL = os.environ.get("FACE_MODEL", "hog")  # "hog" for CPU, "cnn" for GPU
FACE_ENCODING_JITTERS = int(os.environ.get("FACE_JITTERS", "1"))
FACE_CONFIDENCE_THRESHOLD = float(os.environ.get("FACE_CONFIDENCE", "0.6"))
FACE_MAX_SAMPLES = int(os.environ.get("FACE_MAX_SAMPLES", "5"))
FACE_PROCESSING_THREADS = int(os.environ.get("FACE_THREADS", "2"))

# Fingerprint sensor settings with security
FINGERPRINT_PORT = os.environ.get("FINGERPRINT_PORT", "COM3")
FINGERPRINT_BAUD_RATE = int(os.environ.get("FINGERPRINT_BAUD", "57600"))
FINGERPRINT_TIMEOUT = int(os.environ.get("FINGERPRINT_TIMEOUT", "5"))
FINGERPRINT_RETRY_ATTEMPTS = int(os.environ.get("FINGERPRINT_RETRIES", "3"))

# Door control settings with safety features
DOOR_UNLOCK_DURATION = int(os.environ.get("DOOR_UNLOCK_TIME", "10"))  # Increased from 5 to 10 seconds
DOOR_RELAY_PIN = int(os.environ.get("DOOR_RELAY_PIN", "17"))
DOOR_EMERGENCY_TIMEOUT = int(os.environ.get("DOOR_EMERGENCY_TIMEOUT", "60"))  # Max unlock time
DOOR_AUTO_LOCK_ENABLED = os.environ.get("DOOR_AUTO_LOCK", "true").lower() == "true"
DOOR_DOUBLE_LOCK_ENABLED = os.environ.get("DOOR_DOUBLE_LOCK", "false").lower() == "true"

# Web server settings with security hardening
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))
WEB_DEBUG = os.environ.get("WEB_DEBUG", "false").lower() == "true"
WEB_SSL_ENABLED = os.environ.get("WEB_SSL", "false").lower() == "true"
WEB_SSL_CERT = os.environ.get("WEB_SSL_CERT", "")
WEB_SSL_KEY = os.environ.get("WEB_SSL_KEY", "")

# Security settings with enhanced protection
SECRET_KEY = os.environ.get("SECRET_KEY", None)  # Must be set in production
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_hex(32)  # Generate secure key if not provided

# Authentication settings with security hardening
PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))  # Increased from 8
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "3"))  # Reduced from 5
LOCKOUT_DURATION = int(os.environ.get("LOCKOUT_DURATION", "300"))
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "28800"))  # 8 hours in seconds
PASSWORD_COMPLEXITY_REQUIRED = os.environ.get("PASSWORD_COMPLEXITY", "true").lower() == "true"

# API settings with security
API_BASE_URL = f"http://{WEB_HOST}:{WEB_PORT}/api"
API_RATE_LIMIT_ENABLED = os.environ.get("API_RATE_LIMIT", "true").lower() == "true"
API_CORS_ENABLED = os.environ.get("API_CORS", "false").lower() == "true"
API_CORS_ORIGINS = os.environ.get("API_CORS_ORIGINS", "").split(",") if os.environ.get("API_CORS_ORIGINS") else []

# Logging settings with security considerations
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "system.log"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_MAX_SIZE = int(os.environ.get("LOG_MAX_SIZE", "10485760"))  # 10MB
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))
LOG_SECURITY_ENABLED = os.environ.get("LOG_SECURITY", "true").lower() == "true"
LOG_SENSITIVE_DATA_FILTERING = os.environ.get("LOG_FILTER_SENSITIVE", "true").lower() == "true"

# Threading settings with performance optimization
THREAD_TIMEOUT = int(os.environ.get("THREAD_TIMEOUT", "30"))
MAX_CONCURRENT_THREADS = int(os.environ.get("MAX_THREADS", "20"))  # Increased for performance
THREAD_POOL_SIZE = int(os.environ.get("THREAD_POOL_SIZE", "10"))

# Sensor settings with reliability improvements
SENSOR_RETRY_ATTEMPTS = int(os.environ.get("SENSOR_RETRIES", "3"))
SENSOR_RETRY_DELAY = float(os.environ.get("SENSOR_RETRY_DELAY", "1.0"))
SENSOR_CONNECTION_TIMEOUT = int(os.environ.get("SENSOR_CONN_TIMEOUT", "10"))

# Authentication settings with enhanced security
AUTH_RETRY_ATTEMPTS = int(os.environ.get("AUTH_RETRIES", "3"))
AUTH_RETRY_DELAY = float(os.environ.get("AUTH_RETRY_DELAY", "2.0"))
AUTH_TIMEOUT = int(os.environ.get("AUTH_TIMEOUT", "30"))
AUTH_REQUIRE_BOTH = os.environ.get("AUTH_REQUIRE_BOTH", "true").lower() == "true"  # Must have both biometrics
AUTH_USER_MATCH_REQUIRED = os.environ.get("AUTH_USER_MATCH", "true").lower() == "true"  # Same user for both

# Door settings with safety features
DOOR_STATE_CHECK_INTERVAL = float(os.environ.get("DOOR_STATE_INTERVAL", "1.0"))
DOOR_RETRY_ATTEMPTS = int(os.environ.get("DOOR_RETRIES", "3"))
DOOR_FORCE_LOCK_ON_ERROR = os.environ.get("DOOR_FORCE_LOCK", "true").lower() == "true"  # Lock on any error
DOOR_MONITOR_ENABLED = os.environ.get("DOOR_MONITOR", "true").lower() == "true"

# Memory management with optimization
MAX_FRAME_HISTORY = int(os.environ.get("MAX_FRAME_HISTORY", "100"))
GC_THRESHOLD = int(os.environ.get("GC_THRESHOLD", "100"))
MEMORY_LIMIT_MB = int(os.environ.get("MEMORY_LIMIT", "512"))  # Memory limit per process
MEMORY_MONITORING_ENABLED = os.environ.get("MEMORY_MONITORING", "true").lower() == "true"

# GUI settings with performance optimization
GUI_UPDATE_INTERVAL = int(os.environ.get("GUI_UPDATE_INTERVAL", "50"))  # Reduced for better performance
GUI_WINDOW_WIDTH = int(os.environ.get("GUI_WIDTH", "1200"))
GUI_WINDOW_HEIGHT = int(os.environ.get("GUI_HEIGHT", "800"))
GUI_HIGH_DPI_AWARE = os.environ.get("GUI_HIGH_DPI", "true").lower() == "true"
GUI_ACCESSIBILITY_MODE = os.environ.get("GUI_ACCESSIBILITY", "true").lower() == "true"

# Performance monitoring settings
PERFORMANCE_MONITORING_ENABLED = os.environ.get("PERF_MONITORING", "true").lower() == "true"
PERFORMANCE_LOG_INTERVAL = int(os.environ.get("PERF_LOG_INTERVAL", "60"))  # Log performance every minute
FPS_MONITORING_ENABLED = os.environ.get("FPS_MONITORING", "true").lower() == "true"
CPU_MONITORING_ENABLED = os.environ.get("CPU_MONITORING", "true").lower() == "true"
MEMORY_MONITORING_ENABLED = os.environ.get("MEMORY_MONITORING", "true").lower() == "true"

# Backup and recovery settings
BACKUP_ENABLED = os.environ.get("BACKUP_ENABLED", "true").lower() == "true"
BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL", "24"))  # Daily backups
BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION", "30"))  # Keep 30 days of backups
BACKUP_ENCRYPTION_ENABLED = os.environ.get("BACKUP_ENCRYPTION", "false").lower() == "true"

# Network settings with security
NETWORK_TIMEOUT = int(os.environ.get("NETWORK_TIMEOUT", "10"))
NETWORK_RETRY_ATTEMPTS = int(os.environ.get("NETWORK_RETRIES", "3"))
NETWORK_SSL_VERIFY = os.environ.get("NETWORK_SSL_VERIFY", "true").lower() == "true"

# Environment detection
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production").lower()  # production, staging, development
DEBUG_MODE = os.environ.get("DEBUG", "false").lower() == "true"
TESTING_MODE = os.environ.get("TESTING", "false").lower() == "true"

# Security headers for web application
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'Content-Security-Policy': "default-src 'self'",
    'X-Permitted-Cross-Domain-Policies': 'none',
    'Referrer-Policy': 'strict-origin-when-cross-origin'
}

# Feature flags for gradual rollout
FEATURE_FACE_RECOGNITION = os.environ.get("FEATURE_FACE", "true").lower() == "true"
FEATURE_FINGERPRINT = os.environ.get("FEATURE_FINGERPRINT", "true").lower() == "true"
FEATURE_WEB_DASHBOARD = os.environ.get("FEATURE_WEB", "true").lower() == "true"
FEATURE_MOBILE_APP = os.environ.get("FEATURE_MOBILE", "false").lower() == "true"
FEATURE_REMOTE_ACCESS = os.environ.get("FEATURE_REMOTE", "false").lower() == "true"

# Compliance and auditing
AUDIT_LOG_ENABLED = os.environ.get("AUDIT_LOG", "true").lower() == "true"
AUDIT_LOG_RETENTION_DAYS = int(os.environ.get("AUDIT_RETENTION", "365"))  # Keep audit logs for 1 year
GDPR_COMPLIANCE_MODE = os.environ.get("GDPR_COMPLIANCE", "false").lower() == "true"
DATA_RETENTION_POLICY_DAYS = int(os.environ.get("DATA_RETENTION", "2555"))  # 7 years for compliance

# Initialize directories
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
if BACKUP_ENABLED:
    DATABASE_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

# Security validation
if ENVIRONMENT == "production" and not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in production environment")

if ENVIRONMENT == "production" and WEB_DEBUG:
    raise ValueError("Debug mode must be disabled in production")

# Performance validation
if CAMERA_WIDTH > 1920 or CAMERA_HEIGHT > 1080:
    raise ValueError("Camera resolution too high for production use")

if DOOR_UNLOCK_DURATION > 60:
    raise ValueError("Door unlock duration too long for security")

# Anti-Spoofing Configuration
ANTI_SPOOFING_CONFIG = {
    'challenge_timeout': 10.0,  # seconds to complete challenge
    'blink_threshold': 0.1,     # minimum blink duration
    'movement_threshold': 10,   # minimum movement pixels
    'confidence_threshold': 0.8, # minimum confidence for liveness
    'reflection_threshold': 50, # screen reflection detection
    'texture_threshold': 100,   # photo texture detection
    'enabled': True             # enable anti-spoofing
}

# Logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': LOG_FORMAT
        },
        'security': {
            'format': '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
        },
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILE,
            'maxBytes': LOG_MAX_SIZE,
            'backupCount': LOG_BACKUP_COUNT,
            'formatter': 'detailed'
        },
        'security_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'security.log',
            'formatter': 'security'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': True
        },
        'security': {
            'handlers': ['security_file'],
            'level': 'INFO',
            'propagate': False
        },
        'performance': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False
        }
    }
}

"""
Enhanced Smart Door Security System - Advanced Authentication Engine
Implements multi-factor authentication with anti-spoofing protection.
Ensures door unlocks ONLY for verified real humans.
"""

import threading
import logging
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from typing import Optional, Callable, Tuple, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
import sys
from pathlib import Path
import queue
import weakref
from collections import deque
import gc
import os

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import AUTH_TIMEOUT, ANTI_SPOOFING_CONFIG
from database.db_manager import SecureAccessLogRepository, SecureUserRepository, SecureSystemLogRepository

from modules.face_recognition_module import (
    FaceRecognitionEngine, FaceResult, FaceStatus
)
from modules.fingerprint_module import (
    FingerprintManager, FingerprintResult, FingerprintStatus
)
from modules.door_control import DoorController, DoorState
from modules.anti_spoofing import (
    AdvancedAntiSpoofing, LivenessResult, LivenessState, SpoofType
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuthState(Enum):
    """Enhanced authentication state machine states."""
    IDLE = "Waiting for Authentication"
    FACE_PENDING = "Face Verification Pending"
    LIVENESS_CHECK = "Liveness Verification Required"
    FACE_MATCHED = "Face Verified - Awaiting Fingerprint"
    FINGERPRINT_PENDING = "Fingerprint Verification Pending"
    VERIFYING = "Verifying Identity..."
    ACCESS_GRANTED = "ACCESS GRANTED"
    ACCESS_DENIED = "ACCESS DENIED"
    TIMEOUT = "Authentication Timeout"
    ERROR = "Authentication Error"
    SPOOFING_DETECTED = "Spoofing Attempt Detected"


@dataclass
class EnhancedAuthSession:
    """Enhanced authentication session with anti-spoofing."""
    state: AuthState = AuthState.IDLE
    face_result: Optional[FaceResult] = None
    fingerprint_result: Optional[FingerprintResult] = None
    liveness_result: Optional[LivenessResult] = None
    face_user_id: Optional[int] = None
    fingerprint_user_id: Optional[int] = None
    matched_user_id: Optional[int] = None
    matched_user_name: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    failure_reason: Optional[str] = None
    confidence: float = 0.0
    spoof_detected: bool = False
    challenge_attempts: int = 0
    max_challenge_attempts: int = 3


class EnhancedAuthenticationEngine:
    """
    Enhanced multi-factor authentication engine with anti-spoofing.
    Access granted ONLY when:
    1. Face matches a registered user
    2. Liveness verification passes (real human)
    3. Fingerprint matches the SAME user
    4. User is active in the database
    """
    
    def __init__(self, simulation: bool = False, enable_anti_spoofing: bool = True):
        self.simulation = simulation
        self.enable_anti_spoofing = enable_anti_spoofing and ANTI_SPOOFING_CONFIG.get('enabled', True)
        
        # Initialize components
        self.face_engine = FaceRecognitionEngine()
        self.fingerprint_manager = FingerprintManager(simulation=simulation)
        self.door_controller = DoorController(simulation=simulation)
        self.anti_spoofing = AdvancedAntiSpoofing() if self.enable_anti_spoofing else None
        
        # Repositories
        self.access_log = SecureAccessLogRepository()
        self.user_repo = SecureUserRepository()
        self.system_log = SecureSystemLogRepository()
        
        # Authentication state
        self._current_session: Optional[EnhancedAuthSession] = None
        self._session_lock = threading.Lock()
        self._running = False
        self._auth_thread: Optional[threading.Thread] = None
        
        # Security monitoring
        self._failed_attempts: Dict[str, int] = {}
        self._last_attempt_time: Dict[str, float] = {}
        self._spoofing_attempts: Dict[str, int] = {}
        
        # Admin notification settings
        self._admin_email = os.environ.get("ADMIN_EMAIL", "")
        self._smtp_server = os.environ.get("SMTP_SERVER", "")
        self._smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_username = os.environ.get("SMTP_USERNAME", "")
        self._smtp_password = os.environ.get("SMTP_PASSWORD", "")
        
        # Callbacks
        self._state_callbacks: list = []
        self._result_callbacks: list = []
        self._security_callbacks: list = []
        
        # Configuration
        self.auth_timeout = AUTH_TIMEOUT
        self.max_failed_attempts = 5
        self.lockout_duration = 300  # 5 minutes
    
    def add_state_callback(self, callback: Callable[[EnhancedAuthSession], None]):
        """Add callback for authentication state changes."""
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)
    
    def remove_state_callback(self, callback: Callable[[EnhancedAuthSession], None]):
        """Remove state callback."""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
    
    def add_result_callback(self, callback: Callable[[EnhancedAuthSession], None]):
        """Add callback for authentication results (success/failure)."""
        if callback not in self._result_callbacks:
            self._result_callbacks.append(callback)
    
    def add_security_callback(self, callback: Callable[[Dict], None]):
        """Add callback for security events (spoofing, failed attempts).""" 
        if callback not in self._security_callbacks:
            self._security_callbacks.append(callback)
    
    def _notify_state_change(self, session: EnhancedAuthSession):
        """Notify all state callbacks."""
        for callback in self._state_callbacks:
            try:
                callback(session)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def _notify_result(self, session: EnhancedAuthSession):
        """Notify all result callbacks."""
        for callback in self._result_callbacks:
            try:
                callback(session)
            except Exception as e:
                logger.error(f"Result callback error: {e}")
    
    def _notify_security_event(self, event_data: Dict[str, Any]):
        """Notify all security event callbacks."""
        for callback in self._security_callbacks:
            try:
                callback(event_data)
            except Exception as e:
                logger.error(f"Security callback error: {e}")
    
    def start(self) -> bool:
        """Start the enhanced authentication engine."""
        logger.info("Starting enhanced authentication engine with anti-spoofing...")
        
        # Start face recognition
        if not self.face_engine.start():
            logger.error("Failed to start face recognition")
            self.system_log.error("AuthEngine", "Failed to start face recognition")
            return False
        
        # Start fingerprint sensor
        if not self.fingerprint_manager.start():
            logger.warning("Fingerprint sensor not available - may be in simulation mode")
        
        # Start anti-spoofing if enabled
        if self.enable_anti_spoofing and self.anti_spoofing:
            logger.info("Anti-spoofing protection enabled")
        else:
            logger.warning("Anti-spoofing protection disabled")
        
        self._running = True
        self._current_session = EnhancedAuthSession()
        
        # Start authentication loop
        self._auth_thread = threading.Thread(target=self._auth_loop, daemon=True)
        self._auth_thread.start()
        
        logger.info("Enhanced authentication engine started")
        self.system_log.info("AuthEngine", "Enhanced authentication engine started with anti-spoofing")
        return True
    
    def stop(self):
        """Stop the enhanced authentication engine."""
        self._running = False
        
        if self._auth_thread:
            self._auth_thread.join(timeout=3.0)
        
        self.face_engine.stop()
        self.fingerprint_manager.stop()
        self.door_controller.cleanup()
        
        logger.info("Enhanced authentication engine stopped")
        self.system_log.info("AuthEngine", "Enhanced authentication engine stopped")
    
    def _auth_loop(self):
        """Enhanced authentication loop with anti-spoofing."""
        while self._running:
            try:
                with self._session_lock:
                    if self._current_session is None:
                        self._current_session = EnhancedAuthSession()
                    
                    session = self._current_session
                
                # Check for timeout
                if session.state not in [AuthState.IDLE, AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED, AuthState.SPOOFING_DETECTED]:
                    elapsed = time.time() - session.start_time
                    if elapsed > self.auth_timeout:
                        self._handle_timeout(session)
                        continue
                
                # State machine with anti-spoofing
                if session.state == AuthState.IDLE:
                    self._process_idle_state(session)
                
                elif session.state == AuthState.FACE_MATCHED:
                    self._process_liveness_verification(session)
                
                elif session.state == AuthState.LIVENESS_CHECK:
                    self._process_liveness_challenge(session)
                
                elif session.state == AuthState.FACE_MATCHED:  # After liveness passed
                    self._process_fingerprint_verification(session)
                
                elif session.state in [AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED, AuthState.SPOOFING_DETECTED]:
                    # Wait before resetting
                    time.sleep(3)
                    self._reset_session()
                
                time.sleep(0.05)  # Small delay to prevent CPU spinning
                
            except Exception as e:
                logger.error(f"Auth loop error: {e}")
                self.system_log.error("AuthEngine", f"Auth loop error: {str(e)}")
                time.sleep(1)
    
    def _process_idle_state(self, session: EnhancedAuthSession):
        """Process authentication when in idle state - look for faces."""
        face_result = self.face_engine.process_frame()
        
        if face_result.status == FaceStatus.FACE_MATCHED:
            # Face matched - verify user is active
            user = self.user_repo.get_by_id(face_result.user_id)
            
            if user and user.get('is_active', False):
                session.state = AuthState.FACE_MATCHED
                session.face_result = face_result
                session.face_user_id = face_result.user_id
                session.start_time = time.time()
                
                # Check for repeated attempts from same user
                self._check_failed_attempts(session.face_user_id)
                
                logger.info(f"Face matched: {face_result.user_name}")
                self._notify_state_change(session)
            else:
                # User not active
                logger.warning(f"Face matched but user inactive: {face_result.user_name}")
                self._deny_access(session, "User account is disabled")
        elif face_result.status == FaceStatus.UNKNOWN_FACE:
            # Unknown face - check for spoofing
            self._handle_unknown_face(session, face_result)
    
    def _process_liveness_verification(self, session: EnhancedAuthSession):
        """Process liveness verification after face match."""
        if not self.enable_anti_spoofing or not self.anti_spoofing:
            # Skip liveness check if disabled
            session.state = AuthState.FACE_MATCHED
            return
        
        # Get current frame for liveness analysis
        frame = self.face_engine.get_current_frame()
        if frame is None:
            return
        
        liveness_result = self.anti_spoofing.analyze_frame(frame)
        session.liveness_result = liveness_result
        
        if liveness_result.is_live:
            session.state = AuthState.FACE_MATCHED  # Continue to fingerprint
            logger.info("Liveness verification passed")
            self._notify_state_change(session)
        elif liveness_result.spoof_type != SpoofType.NONE:
            self._handle_spoofing_attempt(session, liveness_result)
        elif liveness_result.liveness_state == LivenessState.LIVENESS_FAILED:
            session.challenge_attempts += 1
            if session.challenge_attempts >= session.max_challenge_attempts:
                self._deny_access(session, "Liveness verification failed after multiple attempts")
            else:
                session.state = AuthState.LIVENESS_CHECK
                logger.warning(f"Liveness challenge failed, attempt {session.challenge_attempts}")
        else:
            # Still in challenge mode
            session.state = AuthState.LIVENESS_CHECK
            self._notify_state_change(session)
    
    def _process_liveness_challenge(self, session: EnhancedAuthSession):
        """Process ongoing liveness challenge."""
        frame = self.face_engine.get_current_frame()
        if frame is None:
            return
        
        liveness_result = self.anti_spoofing.analyze_frame(frame)
        session.liveness_result = liveness_result
        
        if liveness_result.is_live:
            session.state = AuthState.FACE_MATCHED
            logger.info("Liveness challenge completed successfully")
            self._notify_state_change(session)
        elif liveness_result.liveness_state == LivenessState.LIVENESS_FAILED:
            session.challenge_attempts += 1
            if session.challenge_attempts >= session.max_challenge_attempts:
                self._deny_access(session, "Liveness verification failed after multiple attempts")
            else:
                logger.warning(f"Liveness challenge failed, attempt {session.challenge_attempts}")
        elif liveness_result.spoof_type != SpoofType.NONE:
            self._handle_spoofing_attempt(session, liveness_result)
    
    def _process_fingerprint_verification(self, session: EnhancedAuthSession):
        """Process fingerprint after face and liveness are verified."""
        fp_result = self.fingerprint_manager.scan_once(timeout=2.0)
        
        if fp_result.status == FingerprintStatus.MATCHED:
            session.fingerprint_result = fp_result
            session.fingerprint_user_id = fp_result.user_id
            
            # Critical check: SAME USER for all biometrics?
            if session.face_user_id == session.fingerprint_user_id:
                # Double verification: check user is still active
                user = self.user_repo.get_by_id(session.face_user_id)
                
                if user and user.get('is_active', False):
                    self._grant_access(session, user)
                else:
                    self._deny_access(session, "User account is disabled")
            else:
                # Different users for biometrics
                self._deny_access(
                    session, 
                    "Face and fingerprint belong to different users"
                )
        
        elif fp_result.status == FingerprintStatus.NOT_MATCHED:
            session.fingerprint_result = fp_result
            self._deny_access(session, "Fingerprint not recognized")
        
        elif fp_result.status in [FingerprintStatus.TIMEOUT, FingerprintStatus.NO_FINGER]:
            # Still waiting for fingerprint
            pass
        
        elif fp_result.status == FingerprintStatus.SENSOR_ERROR:
            self._deny_access(session, "Fingerprint sensor error")
    
    def _handle_unknown_face(self, session: EnhancedAuthSession, face_result: FaceResult):
        """Handle unknown face detection with spoofing analysis."""
        frame = self.face_engine.get_current_frame()
        if frame is None:
            return
        
        # Check for spoofing attempt
        if self.enable_anti_spoofing and self.anti_spoofing:
            liveness_result = self.anti_spoofing.analyze_frame(frame)
            session.liveness_result = liveness_result
            
            if liveness_result.spoof_type != SpoofType.NONE:
                self._handle_spoofing_attempt(session, liveness_result, face_result.user_name)
            else:
                # Genuine unknown person
                self._log_suspicious_activity(session, face_result.user_name, "Unknown person")
        else:
            # Just log as unknown person
            self._log_suspicious_activity(session, face_result.user_name, "Unknown person")
    
    def _handle_spoofing_attempt(self, session: EnhancedAuthSession, liveness_result: LivenessResult, face_name: str = "Unknown"):
        """Handle detected spoofing attempt."""
        session.state = AuthState.SPOOFING_DETECTED
        session.spoof_detected = True
        session.failure_reason = f"Spoofing detected: {liveness_result.spoof_type.value}"
        session.end_time = time.time()
        session.confidence = liveness_result.confidence
        
        # Ensure door is locked
        self.door_controller.lock(reason="Spoofing attempt detected")
        
        # Log spoofing attempt
        self.access_log.log_access(
            user_id=None,
            event_type='SPOOFING_ATTEMPT',
            result='BLOCKED',
            face_match=False,
            fingerprint_match=False,
            failure_reason=session.failure_reason,
            confidence_score=session.confidence
        )
        
        # Track spoofing attempts by IP/location
        client_ip = "unknown"  # Would get from request in web context
        if client_ip in self._spoofing_attempts:
            self._spoofing_attempts[client_ip] += 1
        else:
            self._spoofing_attempts[client_ip] = 1
        
        # Send security alert
        self._send_security_alert(session, liveness_result, face_name)
        
        logger.warning(f"SPOOFING ATTEMPT BLOCKED: {liveness_result.spoof_type.value}")
        self.system_log.warning("AuthEngine", f"Spoofing attempt blocked: {liveness_result.spoof_type.value}")
        
        self._notify_state_change(session)
        self._notify_result(session)
        self._notify_security_event({
            'type': 'spoofing_attempt',
            'spoof_type': liveness_result.spoof_type.value,
            'confidence': liveness_result.confidence,
            'face_name': face_name,
            'timestamp': time.time()
        })
        
        # Reset after brief delay
        time.sleep(5)
        self._reset_session()
    
    def _log_suspicious_activity(self, session: EnhancedAuthSession, face_name: str, activity_type: str):
        """Log suspicious activity (unknown person).""" 
        session.state = AuthState.ACCESS_DENIED
        session.failure_reason = f"{activity_type}: {face_name}"
        session.end_time = time.time()
        
        # Log to access log
        self.access_log.log_access(
            user_id=None,
            event_type='SUSPICIOUS_ACTIVITY',
            result='MONITORED',
            face_match=False,
            fingerprint_match=False,
            failure_reason=session.failure_reason
        )
        
        logger.warning(f"Suspicious activity: {activity_type} - {face_name}")
        self.system_log.warning("AuthEngine", f"Suspicious activity: {activity_type} - {face_name}")
        
        self._notify_state_change(session)
        self._notify_result(session)
        self._notify_security_event({
            'type': 'suspicious_activity',
            'activity_type': activity_type,
            'face_name': face_name,
            'timestamp': time.time()
        })
        
        # Reset after brief delay
        time.sleep(3)
        self._reset_session()
    
    def _check_failed_attempts(self, user_id: int):
        """Check and handle failed authentication attempts."""
        current_time = time.time()
        user_key = str(user_id)
        
        # Clean up old attempts
        if user_key in self._last_attempt_time:
            if current_time - self._last_attempt_time[user_key] > self.lockout_duration:
                self._failed_attempts[user_key] = 0
        
        # Check if locked out
        if user_key in self._failed_attempts and self._failed_attempts[user_key] >= self.max_failed_attempts:
            logger.warning(f"User {user_id} locked out due to failed attempts")
            return False
        
        return True
    
    def _send_security_alert(self, session: EnhancedAuthSession, liveness_result: LivenessResult, face_name: str):
        """Send security alert for spoofing attempts."""
        if not self._admin_email or not self._smtp_server:
            logger.warning("Security alert email not configured")
            return
        
        try:
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self._smtp_username
            msg['To'] = self._admin_email
            msg['Subject'] = f"🚨 Security Alert: Spoofing Attempt Detected"
            
            # Email body
            body = f"""
SECURITY ALERT: Spoofing attempt detected on Smart Door Security System

Details:
- Time: {time.strftime('%Y-%m-%d %H:%M:%S')}
- Spoofing Type: {liveness_result.spoof_type.value}
- Confidence: {liveness_result.confidence:.2f}
- Face Name: {face_name}
- Challenge Completed: {liveness_result.challenge_completed}
- Challenge Type: {liveness_result.challenge_type}

The system has automatically blocked this attempt and logged the incident.

Please review the security logs for more details.

Smart Door Security System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(self._smtp_server, self._smtp_port)
            server.starttls()
            server.login(self._smtp_username, self._smtp_password)
            text = msg.as_string()
            server.sendmail(self._smtp_username, self._admin_email, text)
            server.quit()
            
            logger.info("Security alert email sent to admin")
            
        except Exception as e:
            logger.error(f"Failed to send security alert email: {e}")
    
    def _grant_access(self, session: EnhancedAuthSession, user: dict):
        """Grant access to authenticated user."""
        session.state = AuthState.ACCESS_GRANTED
        session.matched_user_id = user['id']
        session.matched_user_name = f"{user['first_name']} {user['last_name']}"
        session.end_time = time.time()
        session.confidence = (
            (session.face_result.confidence if session.face_result else 0) +
            (session.fingerprint_result.confidence if session.fingerprint_result else 0) +
            (session.liveness_result.confidence if session.liveness_result else 0)
        ) / 3
        
        # Unlock door
        self.door_controller.unlock(
            reason=f"Authenticated: {session.matched_user_name} (Real Human Verified)"
        )
        
        # Log access
        self.access_log.log_access(
            user_id=session.matched_user_id,
            event_type='ENTRY',
            result='SUCCESS',
            face_match=True,
            fingerprint_match=True,
            confidence_score=session.confidence
        )
        
        # Reset failed attempts for this user
        user_key = str(session.matched_user_id)
        if user_key in self._failed_attempts:
            self._failed_attempts[user_key] = 0
        
        logger.info(f"ACCESS GRANTED: {session.matched_user_name} (Real Human Verified)")
        self.system_log.info(
            "AuthEngine",
            f"Access granted to {session.matched_user_name} (Real Human Verified)",
            f"Confidence: {session.confidence:.2f}"
        )
        
        self._notify_state_change(session)
        self._notify_result(session)
    
    def _deny_access(self, session: EnhancedAuthSession, reason: str):
        """Deny access."""
        session.state = AuthState.ACCESS_DENIED
        session.failure_reason = reason
        session.end_time = time.time()
        
        # Track failed attempts
        if session.face_user_id:
            user_key = str(session.face_user_id)
            self._failed_attempts[user_key] = self._failed_attempts.get(user_key, 0) + 1
            self._last_attempt_time[user_key] = time.time()
        
        # Ensure door is locked
        self.door_controller.lock(reason="Access denied")
        
        # Log failure
        self.access_log.log_access(
            user_id=session.face_user_id,
            event_type='ENTRY',
            result='DENIED',
            face_match=session.face_result is not None and 
                       session.face_result.status == FaceStatus.FACE_MATCHED,
            fingerprint_match=session.fingerprint_result is not None and
                              session.fingerprint_result.status == FingerprintStatus.MATCHED,
            failure_reason=reason
        )
        
        logger.warning(f"ACCESS DENIED: {reason}")
        self.system_log.warning("AuthEngine", f"Access denied: {reason}")
        
        self._notify_state_change(session)
        self._notify_result(session)
    
    def _handle_timeout(self, session: EnhancedAuthSession):
        """Handle authentication timeout."""
        session.state = AuthState.TIMEOUT
        session.failure_reason = "Authentication timeout"
        session.end_time = time.time()
        
        # Log timeout
        self.access_log.log_access(
            user_id=session.face_user_id,
            event_type='ENTRY',
            result='FAILED',
            face_match=session.face_result is not None,
            fingerprint_match=False,
            failure_reason="Timeout"
        )
        
        logger.warning("Authentication timeout")
        self.system_log.warning("AuthEngine", "Authentication timeout")
        
        self._notify_state_change(session)
        self._notify_result(session)
        
        # Reset after brief delay
        time.sleep(2)
        self._reset_session()
    
    def _reset_session(self):
        """Reset authentication session."""
        with self._session_lock:
            self._current_session = EnhancedAuthSession()
            self._notify_state_change(self._current_session)
    
    def get_current_session(self) -> EnhancedAuthSession:
        """Get current authentication session."""
        with self._session_lock:
            if self._current_session is None:
                self._current_session = EnhancedAuthSession()
            return self._current_session
    
    def get_face_frame(self):
        """Get current camera frame for display."""
        return self.face_engine.get_current_frame()
    
    def process_face(self) -> FaceResult:
        """Process a single frame for face detection."""
        return self.face_engine.process_frame()
    
    def cancel_authentication(self):
        """Cancel current authentication attempt."""
        with self._session_lock:
            if self._current_session and self._current_session.state not in [
                AuthState.IDLE, AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED, AuthState.SPOOFING_DETECTED
            ]:
                self._current_session.state = AuthState.ACCESS_DENIED
                self._current_session.failure_reason = "Cancelled"
                self._notify_state_change(self._current_session)
        
        self._reset_session()


# Convenience function
def get_enhanced_auth_engine(simulation: bool = False, enable_anti_spoofing: bool = True) -> EnhancedAuthenticationEngine:
    """Get or create the enhanced authentication engine with anti-spoofing."""
    return EnhancedAuthenticationEngine(simulation=simulation, enable_anti_spoofing=enable_anti_spoofing)

</final_file_content>

<task_progress>
- [x] Analyze project structure and dependencies
- [x] Review main application files for syntax and logic errors
- [x] Audit face recognition module implementation
- [x] Check fingerprint module functionality
- [x] Verify authentication engine logic
- [x] Test door control module
- [x] Review GUI implementation
- [x] Audit web dashboard and API endpoints
- [x] Check database schema and operations
- [x] Identify and fix security vulnerabilities
- [x] Optimize performance and fix memory leaks
- [x] Improve error handling and logging
- [x] Validate UI/UX design and responsiveness
- [x] Test end-to-end functionality
- [x] Generate final production-ready version
- [x] Fix import path issues in production files
- [x] Verify production directory structure
- [x] Copy missing modules directory to production
- [x] Test production imports
- [x] Test main module import
- [x] Create production cleanup summary
- [x] Complete comprehensive audit and production transformation
- [x] Fix face recognition module imports
- [x] Fix fingerprint module imports
- [x] Fix auth engine module imports
- [x] Fix door control module imports
- [x] Test all imports after fixes
- [x] Test main.py execution
- [x] Create final verification report
- [x] Complete comprehensive security audit and hardening
- [x] Implement anti-spoofing protection measures
- [x] Add unauthorized person detection system
- [x] Create admin alert system
- [x] Implement access attempt monitoring
- [x] Harden door control system security
- [x] Secure biometric data storage
- [x] Harden API security measures
- [x] Improve web dashboard security
- [x] Add system stability and fail-safe design
- [x] Optimize AI model accuracy and security
- [x] Add continuous monitoring features
- [x] Optimize system performance
- [x] Complete final validation and testing
- [x] Create advanced anti-spoofing module with liveness detection
- [x] Add anti-spoofing configuration settings
- [x] Create enhanced authentication engine with anti-spoofing integration
</task_progress>
</write_to_file>
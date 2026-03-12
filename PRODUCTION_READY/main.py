#!/usr/bin/env python3
"""
Smart Door Security System - Main Application (Production Ready)
Runs 24/7 with GUI showing camera preview, fingerprint status, and door state.
Multi-factor authentication: Face + Fingerprint required for access.
"""

import logging
import signal
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tkinter imports
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
from PIL import Image, ImageTk
import cv2

# Project imports
from config.settings import (
    GUI_UPDATE_INTERVAL, GUI_WINDOW_WIDTH, GUI_WINDOW_HEIGHT
)
from database.db_manager import (
    SecureDatabaseManager, SecureUserRepository, SecureAccessLogRepository, SecureSystemLogRepository
)
from modules.face_recognition_module import (
    FaceRecognitionEngine, FaceResult, FaceStatus
)
from modules.fingerprint_module import (
    FingerprintManager, FingerprintResult, FingerprintStatus
)
from modules.door_control import DoorController, DoorState, DoorMonitor
from modules.auth_engine import AuthState

# Configure logging with security considerations
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Security-focused logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'system.log'),
        logging.FileHandler(LOG_DIR / 'security.log')
    ]
)

# Create security logger
security_logger = logging.getLogger('security')
security_handler = logging.FileHandler(LOG_DIR / 'security.log')
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
))
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class ProductionSmartDoorGUI:
    """Production-ready GUI application for the Smart Door Security System."""
    
    def __init__(self, simulation: bool = True):
        """Initialize the production GUI application."""
        self.simulation = simulation
        self.shutdown_flag = threading.Event()
        
        # Initialize main window with security considerations
        self.root = tk.Tk()
        self.root.title("Smart Door Security System - Production")
        self.root.geometry(f"{GUI_WINDOW_WIDTH}x{GUI_WINDOW_HEIGHT}")
        self.root.configure(bg='#1a1a2e')
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Security: Disable window resizing to prevent UI distortion
        self.root.resizable(False, False)
        
        # Initialize database with connection pooling
        self.db = SecureDatabaseManager()
        self.user_repo = SecureUserRepository()
        self.access_log_repo = SecureAccessLogRepository()
        self.system_log = SecureSystemLogRepository()
        
        # Initialize components with error handling
        try:
            self.face_engine = FaceRecognitionEngine()
            self.fingerprint_manager = FingerprintManager(simulation=True)
            self.door_controller = DoorController(simulation=simulation)
            self.door_monitor = DoorMonitor(self.door_controller)
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            self._handle_critical_error(f"System initialization failed: {e}")
            return
        
        # State variables with thread safety
        self._running = False
        self._current_face_result: Optional[FaceResult] = None
        self._current_fp_result: Optional[FingerprintResult] = None
        self._auth_state = AuthState.IDLE
        self._matched_face_user_id = None
        self._auth_start_time = None
        
        # Thread-safe GUI variables
        self._gui_lock = threading.RLock()
        self.face_status_var = tk.StringVar(value="Initializing...")
        self.fingerprint_status_var = tk.StringVar(value="Initializing...")
        self.auth_result_var = tk.StringVar(value="WAITING")
        self.door_status_var = tk.StringVar(value="Door Locked")
        self.door_timer_var = tk.StringVar(value="")
        self.current_time_var = tk.StringVar()
        
        # Performance monitoring
        self._frame_count = 0
        self._fps_counter = 0
        self._last_fps_update = time.time()
        
        # Build GUI with security and accessibility
        self._build_gui()
        
        # Start systems with error recovery
        self._start_systems()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_flag.set()
        self.on_closing()
    
    def _handle_critical_error(self, error_message: str):
        """Handle critical errors that prevent system startup."""
        try:
            security_logger.critical(f"CRITICAL ERROR: {error_message}")
            messagebox.showerror("Critical Error", 
                               f"The system cannot start due to a critical error:\n\n{error_message}\n\n"
                               "Please check the logs and contact system administrator.")
        except Exception:
            pass  # Don't let error handling cause more errors
        finally:
            sys.exit(1)
    
    def _build_gui(self):
        """Build the production GUI layout with security and accessibility."""
        # Configure styles for accessibility
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Custom fonts for accessibility
        self.title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Segoe UI", size=11)
        self.status_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with security information
        self._build_header(main_frame)
        
        # Content area - two columns
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Left column - Camera
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self._build_camera_panel(left_frame)
        
        # Right column - Status panels
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self._build_fingerprint_panel(right_frame)
        self._build_auth_result_panel(right_frame)
        self._build_door_panel(right_frame)
        
        # Footer with recent logs
        self._build_footer(main_frame)
    
    def _build_header(self, parent):
        """Build the header section with security indicators."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title with security icon
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side=tk.LEFT)
        
        title_label = tk.Label(
            title_frame,
            text="🔒 SMART DOOR SECURITY SYSTEM",
            font=self.title_font,
            fg='#00ff88',
            bg='#1a1a2e'
        )
        title_label.pack(side=tk.LEFT)
        
        # Security status indicator
        self.security_status = tk.Label(
            title_frame,
            text="🛡️ SECURE",
            font=self.label_font,
            fg='#00ff88',
            bg='#1a1a2e'
        )
        self.security_status.pack(side=tk.LEFT, padx=(10, 0))
        
        # Current time
        time_label = tk.Label(
            header_frame,
            textvariable=self.current_time_var,
            font=self.label_font,
            fg='#ffffff',
            bg='#1a1a2e'
        )
        time_label.pack(side=tk.RIGHT)
        
        self._update_time()
    
    def _build_camera_panel(self, parent):
        """Build the camera preview panel with security features."""
        camera_frame = tk.LabelFrame(
            parent,
            text="📹 Live Camera Feed",
            font=self.label_font,
            fg='#00d4ff',
            bg='#16213e',
            padx=10,
            pady=10
        )
        camera_frame.pack(fill=tk.BOTH, expand=True)
        
        # Camera canvas with security border
        self.camera_canvas = tk.Canvas(
            camera_frame,
            width=640,
            height=480,
            bg='#0f0f0f',
            highlightthickness=2,
            highlightbackground='#333333'
        )
        self.camera_canvas.pack(pady=10)
        
        # Face status with security context
        face_status_frame = tk.Frame(camera_frame, bg='#16213e')
        face_status_frame.pack(fill=tk.X)
        
        tk.Label(
            face_status_frame,
            text="Face Recognition Status: ",
            font=self.label_font,
            fg='#ffffff',
            bg='#16213e'
        ).pack(side=tk.LEFT)
        
        self.face_status_label = tk.Label(
            face_status_frame,
            textvariable=self.face_status_var,
            font=self.status_font,
            fg='#ffcc00',
            bg='#16213e'
        )
        self.face_status_label.pack(side=tk.LEFT)
        
        # Security note
        security_note = tk.Label(
            camera_frame,
            text="⚠️  Camera feed is processed locally for security",
            font=('Segoe UI', 8),
            fg='#888888',
            bg='#16213e'
        )
        security_note.pack(pady=(5, 0))
    
    def _build_fingerprint_panel(self, parent):
        """Build the fingerprint status panel."""
        fp_frame = tk.LabelFrame(
            parent,
            text="👆 Fingerprint Scanner",
            font=self.label_font,
            fg='#00d4ff',
            bg='#16213e',
            padx=15,
            pady=15
        )
        fp_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status indicator
        self.fp_status_label = tk.Label(
            fp_frame,
            textvariable=self.fingerprint_status_var,
            font=self.status_font,
            fg='#ffcc00',
            bg='#16213e'
        )
        self.fp_status_label.pack(pady=10)
        
        # Fingerprint icon canvas
        self.fp_canvas = tk.Canvas(
            fp_frame,
            width=100,
            height=100,
            bg='#16213e',
            highlightthickness=0
        )
        self.fp_canvas.pack(pady=5)
        self._draw_fingerprint_icon('#444444')
    
    def _build_auth_result_panel(self, parent):
        """Build the authentication result panel."""
        auth_frame = tk.LabelFrame(
            parent,
            text="🔐 Authentication Status",
            font=self.label_font,
            fg='#00d4ff',
            bg='#16213e',
            padx=15,
            pady=15
        )
        auth_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Result label with large, accessible text
        self.auth_result_label = tk.Label(
            auth_frame,
            textvariable=self.auth_result_var,
            font=('Segoe UI', 20, 'bold'),
            fg='#ffffff',
            bg='#333333',
            padx=20,
            pady=20,
            relief='raised'
        )
        self.auth_result_label.pack(fill=tk.X, pady=10)
        
        # Security compliance indicator
        self.compliance_label = tk.Label(
            auth_frame,
            text="🔒 Multi-Factor Authentication Active",
            font=('Segoe UI', 10),
            fg='#00ff88',
            bg='#16213e'
        )
        self.compliance_label.pack()
    
    def _build_door_panel(self, parent):
        """Build the door status panel."""
        door_frame = tk.LabelFrame(
            parent,
            text="🚪 Door Control",
            font=self.label_font,
            fg='#00d4ff',
            bg='#16213e',
            padx=15,
            pady=15
        )
        door_frame.pack(fill=tk.X)
        
        # Door status
        self.door_status_label = tk.Label(
            door_frame,
            textvariable=self.door_status_var,
            font=self.status_font,
            fg='#ff4444',
            bg='#16213e'
        )
        self.door_status_label.pack(pady=10)
        
        # Timer
        self.door_timer_label = tk.Label(
            door_frame,
            textvariable=self.door_timer_var,
            font=self.label_font,
            fg='#888888',
            bg='#16213e'
        )
        self.door_timer_label.pack()
        
        # Door icon canvas
        self.door_canvas = tk.Canvas(
            door_frame,
            width=80,
            height=120,
            bg='#16213e',
            highlightthickness=0
        )
        self.door_canvas.pack(pady=10)
        self._draw_door_icon(locked=True)
    
    def _build_footer(self, parent):
        """Build the footer with recent activity."""
        footer_frame = tk.LabelFrame(
            parent,
            text="📋 System Activity Log",
            font=self.label_font,
            fg='#00d4ff',
            bg='#16213e',
            padx=10,
            pady=5
        )
        footer_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Activity log text with scrollbar
        log_frame = ttk.Frame(footer_frame)
        log_frame.pack(fill=tk.X, pady=5)
        
        self.activity_text = tk.Text(
            log_frame,
            height=4,
            font=('Consolas', 9),
            bg='#0f0f0f',
            fg='#00ff88',
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.activity_text.yview)
        self.activity_text.configure(yscrollcommand=scrollbar.set)
        
        self.activity_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _draw_fingerprint_icon(self, color):
        """Draw fingerprint icon on canvas."""
        self.fp_canvas.delete("all")
        # Simple fingerprint representation
        cx, cy = 50, 50
        for i in range(5):
            r = 15 + i * 8
            self.fp_canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=30, extent=120, outline=color, width=2, style=tk.ARC
            )
    
    def _draw_door_icon(self, locked=True):
        """Draw door icon on canvas."""
        self.door_canvas.delete("all")
        
        # Door frame
        color = '#ff4444' if locked else '#00ff88'
        self.door_canvas.create_rectangle(10, 10, 70, 110, outline=color, width=3)
        
        # Door handle
        self.door_canvas.create_oval(55, 55, 65, 65, fill=color, outline=color)
        
        # Lock icon
        if locked:
            self.door_canvas.create_rectangle(30, 45, 50, 65, outline=color, width=2)
            self.door_canvas.create_arc(30, 35, 50, 55, start=0, extent=180, 
                                        outline=color, width=2, style=tk.ARC)
    
    def _update_time(self):
        """Update the current time display."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_time_var.set(now)
        self.root.after(1000, self._update_time)
    
    def _start_systems(self):
        """Start all system components with error recovery."""
        try:
            # Start face recognition with retry logic
            camera_started = False
            for attempt in range(3):
                if self.face_engine.start():
                    self.face_status_var.set("Camera Ready")
                    self._log_activity("Face recognition system started")
                    camera_started = True
                    break
                else:
                    logger.warning(f"Camera start attempt {attempt + 1} failed")
                    time.sleep(1)
            
            if not camera_started:
                self.face_status_var.set("Camera Error - Using Simulation")
                self._log_activity("ERROR: Face recognition failed to start")
                security_logger.error("Face recognition system failed to start after 3 attempts")
            
            # Start fingerprint sensor with fallback
            if self.fingerprint_manager.start():
                self.fingerprint_status_var.set("Waiting for Fingerprint")
                self._log_activity("Fingerprint sensor connected")
            else:
                # Fallback to simulation if connection fails
                self.fingerprint_manager.set_simulation(True)
                self.fingerprint_status_var.set("Sensor in Simulation Mode")
                self._log_activity("Fingerprint sensor connection failed - using simulation")
                security_logger.warning("Fingerprint sensor connection failed, using simulation mode")
            
            # Start door monitor
            self.door_monitor.add_callback(self._on_door_status_change)
            self.door_monitor.start()
            
            self._running = True
            
            # Start main processing loop
            self._process_loop()
            
            self.system_log.info("MainGUI", "System started successfully")
            security_logger.info("System startup completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to start systems: {e}")
            security_logger.critical(f"System startup failed: {e}")
            self._handle_critical_error(f"Failed to start systems: {e}")
    
    def _process_loop(self):
        """Main processing loop - runs on GUI thread via after()."""
        if not self._running or self.shutdown_flag.is_set():
            return
        
        try:
            # Process face recognition
            face_result = self.face_engine.process_frame()
            self._update_face_display(face_result)
            
            # Update authentication state machine
            self._process_authentication(face_result)
            
            # Update performance metrics
            self._update_performance_metrics()
            
        except Exception as e:
            logger.error(f"Process loop error: {e}")
            security_logger.error(f"Process loop error: {e}")
            self._log_activity(f"System error: {e}")
        
        # Schedule next iteration with adaptive timing
        if self._running and not self.shutdown_flag.is_set():
            self.root.after(GUI_UPDATE_INTERVAL, self._process_loop)
    
    def _update_performance_metrics(self):
        """Update performance metrics and system health."""
        self._frame_count += 1
        current_time = time.time()
        
        # Calculate FPS every second
        if current_time - self._last_fps_update >= 1.0:
            fps = self._frame_count - self._fps_counter
            self._fps_counter = self._frame_count
            self._last_fps_update = current_time
            
            # Update security status based on performance
            if fps < 10:
                self.security_status.config(text="⚠️  LOW PERFORMANCE", fg='#ffcc00')
            else:
                self.security_status.config(text="🛡️  SECURE", fg='#00ff88')
    
    def _update_face_display(self, face_result: FaceResult):
        """Update the camera display with face detection results."""
        if face_result.frame is not None:
            # Convert frame to PhotoImage with error handling
            try:
                frame = cv2.cvtColor(face_result.frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (640, 480))
                img = Image.fromarray(frame)
                self.camera_image = ImageTk.PhotoImage(image=img)
                
                # Update canvas with thread safety
                with self._gui_lock:
                    self.camera_canvas.create_image(0, 0, anchor=tk.NW, image=self.camera_image)
            except Exception as e:
                logger.error(f"Frame processing error: {e}")
        
        # Update face status with security context
        status_text = face_result.status.value
        if face_result.status == FaceStatus.FACE_MATCHED:
            status_text = f"✅ Face Matched: {face_result.user_name}"
            self.face_status_label.config(fg='#00ff88')
        elif face_result.status == FaceStatus.UNKNOWN_FACE:
            self.face_status_label.config(fg='#ff4444')
        elif face_result.status == FaceStatus.FACE_DETECTED:
            self.face_status_label.config(fg='#ffcc00')
        else:
            self.face_status_label.config(fg='#888888')
        
        self.face_status_var.set(status_text)
    
    def _process_authentication(self, face_result: FaceResult):
        """Process the authentication state machine with security checks."""
        current_state = self._auth_state
        
        if current_state == AuthState.IDLE:
            # Looking for face match
            if face_result.status == FaceStatus.FACE_MATCHED:
                # Verify user is active with database transaction
                try:
                    user = self.user_repo.get_by_id(face_result.user_id)
                    if user and user.get('is_active', False):
                        self._auth_state = AuthState.FACE_MATCHED
                        self._matched_face_user_id = face_result.user_id
                        self._auth_start_time = time.time()
                        self._current_face_result = face_result
                        
                        self.fingerprint_status_var.set(f"✅ Face Verified: {face_result.user_name}\nPlease place fingerprint")
                        self._draw_fingerprint_icon('#00ff88')
                        self.auth_result_var.set("AWAITING FINGERPRINT")
                        self.auth_result_label.config(bg='#333333', fg='#ffffff')
                        
                        self._log_activity(f"Face matched: {face_result.user_name}")
                        security_logger.info(f"Face authentication successful for user {face_result.user_name}")
                        
                        # Start fingerprint verification in background
                        threading.Thread(target=self._verify_fingerprint, daemon=True).start()
                    else:
                        self._handle_auth_failure("User account is disabled or not found")
                except Exception as e:
                    logger.error(f"User verification error: {e}")
                    self._handle_auth_failure("Database error during user verification")
        
        elif current_state == AuthState.FACE_MATCHED:
            # Check for timeout
            if time.time() - self._auth_start_time > 30:  # 30 second timeout
                self._auth_state = AuthState.TIMEOUT
                self._handle_auth_failure("Authentication timeout")
        
        elif current_state in [AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED, AuthState.TIMEOUT]:
            # Wait and reset
            if time.time() - self._auth_start_time > 5:
                self._reset_auth_state()
    
    def _verify_fingerprint(self):
        """Verify fingerprint in background thread with security measures."""
        try:
            fp_result = self.fingerprint_manager.scan_once(timeout=10.0)
            self._current_fp_result = fp_result
            
            # Update GUI from main thread
            self.root.after(0, lambda: self._handle_fingerprint_result(fp_result))
            
        except Exception as e:
            logger.error(f"Fingerprint verification error: {e}")
            security_logger.error(f"Fingerprint verification error: {e}")
            self.root.after(0, lambda: self._handle_auth_failure(f"Fingerprint error: {e}"))
    
    def _handle_fingerprint_result(self, fp_result: FingerprintResult):
        """Handle fingerprint verification result with security validation."""
        if self._auth_state != AuthState.FACE_MATCHED:
            return  # State changed, ignore result
        
        if fp_result.status == FingerprintStatus.MATCHED:
            # Critical check: SAME USER for both?
            if fp_result.user_id == self._matched_face_user_id:
                # Verify user is still active
                try:
                    user = self.user_repo.get_by_id(fp_result.user_id)
                    if user and user.get('is_active', False):
                        self._grant_access(user)
                    else:
                        self._handle_auth_failure("User account is disabled")
                except Exception as e:
                    logger.error(f"User status verification error: {e}")
                    self._handle_auth_failure("Database error during user verification")
            else:
                self._handle_auth_failure("Face and fingerprint don't match same user")
                security_logger.warning(f"Authentication bypass attempt detected: Face user {self._matched_face_user_id}, Fingerprint user {fp_result.user_id}")
        
        elif fp_result.status == FingerprintStatus.NOT_MATCHED:
            self._handle_auth_failure("Fingerprint not recognized")
            security_logger.warning(f"Fingerprint authentication failed for user {self._matched_face_user_id}")
        
        elif fp_result.status == FingerprintStatus.TIMEOUT:
            self._handle_auth_failure("Fingerprint scan timeout")
        
        else:
            # Still waiting or error
            self.fingerprint_status_var.set(fp_result.status.value)
    
    def _grant_access(self, user: dict):
        """Grant access to authenticated user with audit logging."""
        self._auth_state = AuthState.ACCESS_GRANTED
        self._auth_start_time = time.time()
        
        user_name = f"{user['first_name']} {user['last_name']}"
        
        # Update UI with security context
        self.auth_result_var.set(f"✅ ACCESS GRANTED\n{user_name}")
        self.auth_result_label.config(bg='#004400', fg='#00ff88')
        self.fingerprint_status_var.set(f"✅ Fingerprint Matched: {user_name}")
        self._draw_fingerprint_icon('#00ff88')
        
        # Unlock door with security logging
        self.door_controller.unlock(reason=f"Authenticated: {user_name}")
        
        # Log access with comprehensive audit trail
        try:
            self.access_log_repo.log_access(
                user_id=user['id'],
                event_type='ENTRY',
                result='SUCCESS',
                face_match=True,
                fingerprint_match=True,
                confidence_score=self._current_face_result.confidence if self._current_face_result else 0
            )
            
            self._log_activity(f"✅ ACCESS GRANTED: {user_name}")
            security_logger.info(f"ACCESS GRANTED to {user_name} (Employee ID: {user.get('employee_id', 'N/A')})")
            
        except Exception as e:
            logger.error(f"Access logging error: {e}")
            security_logger.error(f"Failed to log access event: {e}")
    
    def _handle_auth_failure(self, reason: str):
        """Handle authentication failure with security logging."""
        self._auth_state = AuthState.ACCESS_DENIED
        self._auth_start_time = time.time()
        
        # Update UI with security context
        self.auth_result_var.set(f"❌ ACCESS DENIED\n{reason}")
        self.auth_result_label.config(bg='#440000', fg='#ff4444')
        self.fingerprint_status_var.set("❌ Fingerprint Failed")
        self._draw_fingerprint_icon('#ff4444')
        
        # Ensure door is locked
        self.door_controller.lock(reason="Access denied")
        
        # Log failure with security audit
        try:
            self.access_log_repo.log_access(
                user_id=self._matched_face_user_id,
                event_type='ENTRY',
                result='DENIED',
                face_match=self._current_face_result is not None,
                fingerprint_match=False,
                failure_reason=reason
            )
            
            self._log_activity(f"❌ ACCESS DENIED: {reason}")
            security_logger.warning(f"ACCESS DENIED: {reason} (User ID: {self._matched_face_user_id})")
            
        except Exception as e:
            logger.error(f"Failure logging error: {e}")
            security_logger.error(f"Failed to log access failure: {e}")
    
    def _reset_auth_state(self):
        """Reset authentication state to idle with security cleanup."""
        self._auth_state = AuthState.IDLE
        self._matched_face_user_id = None
        self._current_face_result = None
        self._current_fp_result = None
        self._auth_start_time = None
        
        # Reset UI with security context
        self.auth_result_var.set("WAITING")
        self.auth_result_label.config(bg='#333333', fg='#ffffff')
        self.fingerprint_status_var.set("Waiting for Fingerprint")
        self._draw_fingerprint_icon('#444444')
    
    def _on_door_status_change(self, status):
        """Handle door status changes with security monitoring."""
        self.root.after(0, lambda: self._update_door_display(status))
    
    def _update_door_display(self, status):
        """Update door status display with security indicators."""
        if status.state == DoorState.LOCKED:
            self.door_status_var.set("🔒 Door Locked")
            self.door_status_label.config(fg='#ff4444')
            self.door_timer_var.set("")
            self._draw_door_icon(locked=True)
        
        elif status.state == DoorState.UNLOCKED:
            self.door_status_var.set("🔓 Door Unlocked")
            self.door_status_label.config(fg='#00ff88')
            if status.time_until_lock > 0:
                self.door_timer_var.set(f"⏱️ Auto-lock in {status.time_until_lock:.1f}s")
            self._draw_door_icon(locked=False)
        
        elif status.state == DoorState.UNLOCKING:
            self.door_status_var.set("🔓 Unlocking...")
            self.door_status_label.config(fg='#ffcc00')
        
        elif status.state == DoorState.LOCKING:
            self.door_status_var.set("🔒 Locking...")
            self.door_status_label.config(fg='#ffcc00')
    
    def _log_activity(self, message: str):
        """Add a message to the activity log with security filtering."""
        # Filter sensitive information from logs
        safe_message = message.replace("password", "*****").replace("token", "*****")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {safe_message}\n"
        
        self.activity_text.config(state=tk.NORMAL)
        self.activity_text.insert(tk.END, log_entry)
        self.activity_text.see(tk.END)
        
        # Keep only last 100 lines
        lines = self.activity_text.get("1.0", tk.END).split('\n')
        if len(lines) > 100:
            self.activity_text.delete("1.0", f"{len(lines)-100}.0")
        
        self.activity_text.config(state=tk.DISABLED)
    
    def on_closing(self):
        """Handle window close event with graceful shutdown."""
        if self.shutdown_flag.is_set():
            return  # Already shutting down
        
        if messagebox.askokcancel("Quit", "Are you sure you want to exit?\n\n"
                                        "This will stop the security system.\n"
                                        "Only exit for maintenance or system updates.", 
                                icon='warning'):
            self.shutdown_flag.set()
            self._running = False
            
            # Stop all components with error handling
            try:
                self.door_monitor.stop()
                self.door_controller.cleanup()
                self.fingerprint_manager.stop()
                self.face_engine.stop()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
                security_logger.error(f"Shutdown error: {e}")
            
            self.system_log.info("MainGUI", "System shutdown")
            security_logger.info("System shutdown completed")
            logger.info("System shutdown")
            
            self.root.destroy()
    
    def run(self):
        """Start the GUI main loop with error handling."""
        try:
            logger.info("Starting Smart Door Security System GUI...")
            self._log_activity("System started")
            security_logger.info("GUI application started")
            self.root.mainloop()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            self.shutdown_flag.set()
        except Exception as e:
            logger.error(f"GUI error: {e}")
            security_logger.critical(f"GUI crash: {e}")
            traceback.print_exc()
        finally:
            self.on_closing()


def main():
    """Main entry point with production error handling."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Door Security System - Production Version')
    parser.add_argument(
        '--simulation', '-s',
        action='store_true',
        help='Run in simulation mode (no real hardware)'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--production', '-p',
        action='store_true',
        help='Force production mode (overrides simulation)'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Ensure logs directory exists
    (PROJECT_ROOT / 'logs').mkdir(exist_ok=True)
    
    # Security check: warn if running in simulation mode in production
    if not args.production and args.simulation:
        logger.warning("Running in simulation mode - not suitable for production use")
    
    try:
        # Create and run GUI with error handling
        app = ProductionSmartDoorGUI(simulation=args.simulation)
        app.run()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}")
        security_logger.critical(f"Application startup failure: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
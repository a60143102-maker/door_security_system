# Smart Door Security System - Production Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the Smart Door Security System in a production environment with security and performance optimizations.

## Prerequisites

### Hardware Requirements
- **Processor**: Quad-core 2.0GHz or higher
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 50GB free space (SSD recommended)
- **Camera**: USB webcam (1080p recommended)
- **Fingerprint Sensor**: R307/R305 compatible sensor
- **Door Relay**: 5V/12V relay module
- **Network**: Stable internet connection

### Software Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended), Windows 10+, or Raspberry Pi OS
- **Python**: 3.9 or higher
- **Database**: SQLite (included)

## Installation Steps

### 1. System Preparation

#### Ubuntu/Debian
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3-pip python3-venv python3-dev
sudo apt install -y libjpeg-dev libtiff-dev libavcodec-dev libavformat-dev libswscale-dev
sudo apt install -y libv4l-dev libxvidcore-dev libx264-dev libgtk-3-dev
sudo apt install -y libatlas-base-dev gfortran libhdf5-dev

# Install OpenCV dependencies
sudo apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
sudo apt install -y libqtgui4 libqtwebkit4 libqt4-test python3-pyqt5
```

#### Windows
```cmd
# Install Visual Studio Build Tools
# Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/

# Install Python dependencies
pip install --upgrade pip setuptools wheel
```

#### Raspberry Pi
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv python3-dev
sudo apt install -y libjpeg-dev libtiff-dev libavcodec-dev libavformat-dev libswscale-dev
sudo apt install -y libv4l-dev libatlas-base-dev gfortran

# Enable camera interface (if using Pi Camera)
sudo raspi-config
# Navigate to Interface Options > Camera > Enable
```

### 2. Application Setup

#### Create Application Directory
```bash
# Create application directory
sudo mkdir -p /opt/smart-door-system
sudo chown $USER:$USER /opt/smart-door-system

# Copy application files
cp -r PRODUCTION_READY/* /opt/smart-door-system/
cd /opt/smart-door-system
```

#### Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# .\venv\Scripts\activate  # Windows

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

#### Install Dependencies
```bash
# Install production dependencies
pip install -r requirements.txt

# For face recognition (may take time to compile)
pip install face-recognition dlib

# Verify installation
python -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python -c "import face_recognition; print('Face recognition: OK')"
```

### 3. Security Configuration

#### Environment Variables
Create `.env` file with production settings:
```bash
cat > .env << EOF
# Database Security
DB_ENCRYPTION_KEY=$(openssl rand -hex 32)

# Web Security
SECRET_KEY=$(openssl rand -hex 32)
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_SSL=false
WEB_DEBUG=false

# Authentication Security
PASSWORD_MIN_LENGTH=12
MAX_LOGIN_ATTEMPTS=3
LOCKOUT_DURATION=300
SESSION_TIMEOUT=28800

# Performance Settings
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
FACE_TOLERANCE=0.6
DOOR_UNLOCK_TIME=10

# Environment
ENVIRONMENT=production
DEBUG=false
EOF

# Secure the .env file
chmod 600 .env
```

#### Firewall Configuration
```bash
# Ubuntu/Debian
sudo ufw enable
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 5000/tcp  # Web dashboard
sudo ufw deny 80/tcp     # Block HTTP
sudo ufw allow 443/tcp   # HTTPS (if SSL enabled)

# Check firewall status
sudo ufw status verbose
```

#### SSL Certificate (Optional)
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Or use Let's Encrypt for production
sudo apt install -y certbot
sudo certbot certonly --standalone -d your-domain.com
```

### 4. Database Setup

#### Initialize Database
```bash
# Run database initialization
python -c "
from database.db_manager import SecureDatabaseManager
db = SecureDatabaseManager()
print('Database initialized successfully')
"

# Create initial admin user
python -c "
from database.db_manager import SecureAdminRepository
admin_repo = SecureAdminRepository()
admin_repo.create_admin('admin', 'YourSecurePassword123!', 'admin@company.com', 'System Administrator')
print('Admin user created')
"
```

#### Database Backup Setup
```bash
# Create backup directory
sudo mkdir -p /var/backups/smart-door
sudo chown $USER:$USER /var/backups/smart-door

# Create backup script
cat > backup_database.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/smart-door"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/opt/smart-door-system/database/smart_door.db"
BACKUP_FILE="$BACKUP_DIR/smart_door_$DATE.db"

# Create backup
cp "$DB_PATH" "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"

# Keep only last 30 days
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "Database backup completed: ${BACKUP_FILE}.gz"
EOF

chmod +x backup_database.sh

# Schedule daily backups
echo "0 2 * * * /opt/smart-door-system/backup_database.sh" | sudo crontab -
```

### 5. Service Configuration

#### Systemd Service (Linux)
Create service file:
```bash
sudo tee /etc/systemd/system/smart-door.service > /dev/null << 'EOF'
[Unit]
Description=Smart Door Security System
After=network.target

[Service]
Type=simple
User=smartdoor
Group=smartdoor
WorkingDirectory=/opt/smart-door-system
Environment=PATH=/opt/smart-door-system/venv/bin
ExecStart=/opt/smart-door-system/venv/bin/python main.py --production
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

Create user and set permissions:
```bash
# Create service user
sudo useradd -r -s /bin/false smartdoor

# Set permissions
sudo chown -R smartdoor:smartdoor /opt/smart-door-system
sudo chmod -R 755 /opt/smart-door-system

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable smart-door
sudo systemctl start smart-door

# Check status
sudo systemctl status smart-door
```

#### Windows Service
```powershell
# Install NSSM (Non-Sucking Service Manager)
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "nssm.zip"
Expand-Archive -Path "nssm.zip" -DestinationPath "C:\nssm"

# Create service
C:\nssm\nssm.exe install SmartDoor "C:\opt\smart-door-system\venv\Scripts\python.exe"
C:\nssm\nssm.exe set SmartDoor AppDirectory "C:\opt\smart-door-system"
C:\nssm\nssm.exe set SmartDoor AppParameters "main.py --production"
C:\nssm\nssm.exe set SmartDoor AppStdout "C:\opt\smart-door-system\logs\service.log"
C:\nssm\nssm.exe set SmartDoor AppStderr "C:\opt\smart-door-system\logs\error.log"

# Start service
C:\nssm\nssm.exe start SmartDoor
```

### 6. Monitoring and Logging

#### Log Rotation
Create logrotate configuration:
```bash
sudo tee /etc/logrotate.d/smart-door > /dev/null << 'EOF'
/opt/smart-door-system/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 smartdoor smartdoor
    postrotate
        systemctl reload smart-door
    endscript
}
EOF
```

#### Monitoring Script
Create monitoring script:
```bash
cat > monitor_system.sh << 'EOF'
#!/bin/bash
LOG_FILE="/opt/smart-door-system/logs/monitor.log"
SERVICE_NAME="smart-door"

# Check if service is running
if ! systemctl is-active --quiet $SERVICE_NAME; then
    echo "$(date): Service $SERVICE_NAME is not running" >> $LOG_FILE
    systemctl restart $SERVICE_NAME
fi

# Check disk space
DISK_USAGE=$(df /opt/smart-door-system | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
    echo "$(date): Disk usage is ${DISK_USAGE}%" >> $LOG_FILE
fi

# Check memory usage
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
if (( $(echo "$MEMORY_USAGE > 80" | bc -l) )); then
    echo "$(date): Memory usage is ${MEMORY_USAGE}%" >> $LOG_FILE
fi

# Check camera access
if ! ls /dev/video* > /dev/null 2>&1; then
    echo "$(date): No camera detected" >> $LOG_FILE
fi

echo "$(date): System check completed" >> $LOG_FILE
EOF

chmod +x monitor_system.sh

# Schedule monitoring
echo "*/5 * * * * /opt/smart-door-system/monitor_system.sh" | sudo crontab -
```

### 7. Security Hardening

#### File Permissions
```bash
# Set secure permissions
sudo find /opt/smart-door-system -type f -name "*.py" -exec chmod 644 {} \;
sudo find /opt/smart-door-system -type d -exec chmod 755 {} \;
sudo chmod 600 /opt/smart-door-system/.env
sudo chmod 755 /opt/smart-door-system/main.py
```

#### SELinux/AppArmor (Optional)
```bash
# Ubuntu AppArmor
sudo apt install -y apparmor-utils
sudo aa-complain /opt/smart-door-system/venv/bin/python

# CentOS SELinux
sudo setsebool -P httpd_can_network_connect 1
sudo setsebool -P httpd_execmem 1
```

#### Network Security
```bash
# Disable unused services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable cups

# Enable fail2ban
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 8. Testing and Validation

#### Basic Functionality Test
```bash
# Test database connection
python -c "
from database.db_manager import SecureDatabaseManager
db = SecureDatabaseManager()
print('Database connection: OK')
"

# Test camera access
python -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print(f'Camera access: {ret}')
cap.release()
"

# Test web server
curl http://localhost:5000/login
```

#### Security Scan
```bash
# Install security scanner
pip install bandit safety

# Run security scan
bandit -r . -f json -o security_report.json
safety check --json --output security_deps.json

# Review reports
cat security_report.json | jq '.results[] | {file: .filename, line: .line_number, issue: .issue_text}'
```

#### Performance Test
```bash
# Monitor resource usage
htop

# Test concurrent access
ab -n 1000 -c 10 http://localhost:5000/api/users

# Check response times
time curl -s http://localhost:5000/dashboard > /dev/null
```

### 9. Production Checklist

#### Security Checklist
- [ ] Change default admin password
- [ ] Enable firewall
- [ ] Configure SSL/TLS
- [ ] Set up fail2ban
- [ ] Disable debug mode
- [ ] Secure file permissions
- [ ] Enable audit logging
- [ ] Configure backup encryption

#### Performance Checklist
- [ ] Optimize camera resolution
- [ ] Configure database indexes
- [ ] Set up log rotation
- [ ] Monitor resource usage
- [ ] Configure thread pools
- [ ] Test under load

#### Monitoring Checklist
- [ ] Set up system monitoring
- [ ] Configure alerting
- [ ] Test backup/restore
- [ ] Monitor security logs
- [ ] Set up performance metrics

#### Documentation Checklist
- [ ] Update emergency procedures
- [ ] Document system architecture
- [ ] Create runbooks
- [ ] Train operators
- [ ] Document troubleshooting

### 10. Maintenance

#### Regular Tasks
```bash
# Daily
- Check system logs
- Verify backup completion
- Monitor resource usage

# Weekly
- Review security logs
- Update dependencies
- Test disaster recovery

# Monthly
- Security audit
- Performance review
- Update documentation

# Quarterly
- Penetration testing
- Compliance review
- System upgrades
```

#### Updates and Patches
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Update Python packages
source venv/bin/activate
pip list --outdated
pip install --upgrade package_name

# Restart services
sudo systemctl restart smart-door
```

#### Backup and Recovery
```bash
# Manual backup
python -c "
from database.db_manager import SecureDatabaseManager
import shutil
import os
db = SecureDatabaseManager()
backup_path = '/backup/smart_door_backup.db'
shutil.copy('/opt/smart-door-system/database/smart_door.db', backup_path)
print('Backup completed')
"

# Restore from backup
sudo systemctl stop smart-door
cp /backup/smart_door_backup.db /opt/smart-door-system/database/smart_door.db
sudo systemctl start smart-door
```

## Troubleshooting

### Common Issues

#### Camera Not Detected
```bash
# Check camera
ls /dev/video*
v4l2-ctl --list-devices

# Test camera
ffmpeg -f v4l2 -i /dev/video0 -t 5 test.mp4
```

#### Database Locked
```bash
# Check for locks
lsof /opt/smart-door-system/database/smart_door.db

# Kill processes
sudo kill -9 <PID>
```

#### Service Won't Start
```bash
# Check logs
sudo journalctl -u smart-door -f

# Check permissions
ls -la /opt/smart-door-system/
```

#### High Memory Usage
```bash
# Monitor memory
watch -n 1 'free -h'

# Check for memory leaks
python -m memory_profiler main.py
```

### Emergency Procedures

#### Emergency Shutdown
```bash
# Graceful shutdown
sudo systemctl stop smart-door

# Force shutdown (if needed)
sudo systemctl kill smart-door
```

#### Emergency Access
```bash
# Create emergency admin
python -c "
from database.db_manager import SecureAdminRepository
admin_repo = SecureAdminRepository()
admin_repo.create_admin('emergency', 'EmergencyPass123!', 'emergency@company.com', 'Emergency Admin')
"
```

#### System Recovery
```bash
# Restore from backup
sudo systemctl stop smart-door
cp /backup/latest_backup.db /opt/smart-door-system/database/smart_door.db
sudo systemctl start smart-door

# Verify recovery
curl http://localhost:5000/login
```

## Support

For additional support:
- Check system logs: `/opt/smart-door-system/logs/`
- Review security logs: `/opt/smart-door-system/logs/security.log`
- Monitor performance: `/opt/smart-door-system/logs/performance.log`
- Contact: admin@company.com

## Security Notes

⚠️ **Important Security Reminders:**
- Never use default passwords in production
- Regularly update all dependencies
- Monitor security logs daily
- Implement network segmentation
- Use VPN for remote access
- Regular security audits required
- Backup encryption is mandatory
- Document all security procedures

This deployment guide ensures your Smart Door Security System is production-ready with enterprise-grade security and performance.
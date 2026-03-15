# Gunicorn configuration file for Render.com deployment
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:" + str(os.getenv("PORT", "10000"))
backlog = 2048

# Worker processes
# Use 2 workers to avoid duplicate request issues with Render's load balancer
workers = 2
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Timeout settings - CRITICAL for fixing 502 errors
timeout = 120  # 120 seconds (was default 30)
graceful_timeout = 120
keepalive = 5

# Logging — disable gunicorn access log (Flask after_request handles API logging, skips /health)
accesslog = None
errorlog = "-"
loglevel = "info"

# Simplified format (only used if accesslog is re-enabled)
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s'

# Filter out /health noise from gunicorn's own logger
import logging

class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if '/health' in msg or '/favicon.ico' in msg:
            return False
        return True

def on_starting(server):
    """Add health check filter to gunicorn's error logger to suppress /health noise."""
    server.log.error_log.addFilter(HealthCheckFilter())

def post_fork(server, worker):
    """Also filter in each worker process."""
    server.log.error_log.addFilter(HealthCheckFilter())
    server.log.access_log.addFilter(HealthCheckFilter())

# Process naming
proc_name = "concordia_sequence_planner"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (not needed on Render)
keyfile = None
certfile = None

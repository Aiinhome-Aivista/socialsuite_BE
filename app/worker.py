"""
Standalone scheduler process. Run separately from the web workers so scheduled
publishing keeps working even while the API restarts.

    python -m app.worker

Deployed as its own systemd unit (see deploy/socialsuite-worker.service).
"""
import time

from app.services.scheduler import start_scheduler

if __name__ == "__main__":
    start_scheduler()
    print("[worker] scheduler started; waiting for jobs...")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("[worker] shutting down")

#!/bin/bash
# Trading agent auto-runner with logging

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
MODE="${1:-analyze}"
LOG_FILE="$LOG_DIR/${MODE}_${TIMESTAMP}.log"

echo "[$TIMESTAMP] Running: python3 main.py $MODE" | tee "$LOG_FILE"
echo "─────────────────────────────────────────" | tee -a "$LOG_FILE"

cd "$SCRIPT_DIR"
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
PYTHONUNBUFFERED=1 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 main.py "$MODE" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "" >> "$LOG_FILE"
echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] Finished with exit code $EXIT_CODE" >> "$LOG_FILE"

# Regenerate the public dashboard report
echo "" >> "$LOG_FILE"
echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] Regenerating dashboard report..." >> "$LOG_FILE"
PYTHONUNBUFFERED=1 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 report.py >> "$LOG_FILE" 2>&1

# Auto-publish the dashboard update to GitHub (Vercel auto-deploys from main)
if [ -f "latest_report.html" ]; then
    echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] Publishing dashboard to GitHub..." >> "$LOG_FILE"
    git add latest_report.html >> "$LOG_FILE" 2>&1
    if ! git diff --cached --quiet; then
        git commit -m "Auto-update dashboard — $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG_FILE" 2>&1
        git push origin main >> "$LOG_FILE" 2>&1 && \
            echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] Dashboard published successfully." >> "$LOG_FILE" || \
            echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] WARNING: git push failed." >> "$LOG_FILE"
    else
        echo "[$( date +"%Y-%m-%d_%H-%M-%S" )] No dashboard changes to publish." >> "$LOG_FILE"
    fi
fi

# Keep only last 30 days of logs
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null

exit $EXIT_CODE

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

# Keep only last 30 days of logs
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null

exit $EXIT_CODE

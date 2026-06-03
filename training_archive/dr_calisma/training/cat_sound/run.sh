#!/bin/bash
# run.sh — Cat Sound Training + Analysis
#
# Usage:
#   nohup bash /home/user02/dr/training/cat_sound/run.sh >> /home/user02/dr/cat_sound_training.log 2>&1 &

set -u

SCRIPT_DIR="/home/user02/dr/training/cat_sound"
WORK_DIR="/home/user02/dr"
VENV="/home/user02/ml_1/bin/activate"
LOG="${WORK_DIR}/cat_sound_training.log"
MAX_RETRIES=10
RETRY_DELAY=15

source "${VENV}"
cd "${WORK_DIR}"

echo ""
echo "================================================================================"
echo "[$(date '+%F %T')] cat_sound training basladi | PID=$$"
echo "================================================================================"

retry=0
while [ $retry -lt $MAX_RETRIES ]; do
    echo "[$(date '+%F %T')] DENEME $((retry+1))/$MAX_RETRIES"
    python -u "${SCRIPT_DIR}/training.py"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%F %T')] TRAINING BASARILI"
        break
    else
        retry=$((retry+1))
        echo "[$(date '+%F %T')] COKUS: exit=$EXIT_CODE"
        [ $retry -lt $MAX_RETRIES ] && sleep $RETRY_DELAY
    fi
done

[ $retry -ge $MAX_RETRIES ] && echo "MAX RETRY" && exit 1

echo "[$(date '+%F %T')] Analysis baslatiliyor..."
a_retry=0
while [ $a_retry -lt 3 ]; do
    python -u "${SCRIPT_DIR}/analysis.py"
    [ $? -eq 0 ] && echo "[$(date '+%F %T')] ANALYSIS BASARILI" && break
    a_retry=$((a_retry+1))
    [ $a_retry -lt 3 ] && sleep 10
done

echo "[$(date '+%F %T')] TAMAMLANDI"

#!/bin/bash
# run.sh — Cat Thermal Classification Training + Analysis
#
# Usage:
#   nohup bash /home/user02/dr/training/cat_thermal/run.sh >> /home/user02/dr/cat_thermal_training.log 2>&1 &

set -u
SCRIPT_DIR="/home/user02/dr/training/cat_thermal"
WORK_DIR="/home/user02/dr"
VENV="/home/user02/ml_1/bin/activate"
PY_SCRIPT="${SCRIPT_DIR}/training.py"
ANALYSIS_SCRIPT="${SCRIPT_DIR}/analysis.py"
MAX_RETRIES=10
RETRY_DELAY=15

source "${VENV}"
cd "${WORK_DIR}"

echo ""
echo "================================================================================"
echo "[$(date '+%F %T')] cat_thermal training basladi | PID=$$"
echo "================================================================================"

retry=0
while [ $retry -lt $MAX_RETRIES ]; do
    echo "[$(date '+%F %T')] DENEME $((retry+1))/$MAX_RETRIES"
    python -u "${PY_SCRIPT}"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%F %T')] TRAINING BASARILI (exit=0)"
        break
    else
        retry=$((retry+1))
        echo "[$(date '+%F %T')] COKUS: exit=$EXIT_CODE | retry=$retry/$MAX_RETRIES"
        [ $retry -lt $MAX_RETRIES ] && sleep $RETRY_DELAY
    fi
done

[ $retry -ge $MAX_RETRIES ] && echo "MAX RETRY ASILDI" && exit 1

echo ""
echo "[$(date '+%F %T')] Analysis baslatiliyor..."
a_retry=0
while [ $a_retry -lt 3 ]; do
    python -u "${ANALYSIS_SCRIPT}"
    A_EXIT=$?
    if [ $A_EXIT -eq 0 ]; then
        echo "[$(date '+%F %T')] ANALYSIS BASARILI"
        break
    else
        a_retry=$((a_retry+1))
        [ $a_retry -lt 3 ] && sleep 10
    fi
done

echo "[$(date '+%F %T')] TAMAMLANDI"

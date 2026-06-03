#!/bin/bash
# run.sh — YOLO Feline Reticulocytes Training + Analysis
#
# Usage:
#   nohup bash /home/user02/dr/training/feline_reticulocytes/run.sh >> /home/user02/dr/feline_ret_training.log 2>&1 &

set -u

SCRIPT_DIR="/home/user02/dr/training/feline_reticulocytes"
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
echo "[$(date '+%F %T')] run feline_reticulocytes basladi | PID=$$"
echo "================================================================================"

retry=0
while [ $retry -lt $MAX_RETRIES ]; do
    echo ""
    echo "[$(date '+%F %T')] DENEME $((retry+1))/$MAX_RETRIES — training baslatiliyor..."
    python -u "${PY_SCRIPT}"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%F %T')] TRAINING BASARILI (exit=0)"
        break
    else
        retry=$((retry+1))
        echo "[$(date '+%F %T')] COKUS: exit=$EXIT_CODE | retry=$retry/$MAX_RETRIES"
        if [ $retry -lt $MAX_RETRIES ]; then
            sleep $RETRY_DELAY
        fi
    fi
done

if [ $retry -ge $MAX_RETRIES ]; then
    echo "[$(date '+%F %T')] MAX RETRY ASILDI"
    exit 1
fi

echo ""
echo "[$(date '+%F %T')] Analysis baslatiliyor..."
ANALYSIS_MAX_RETRY=3
a_retry=0
while [ $a_retry -lt $ANALYSIS_MAX_RETRY ]; do
    python -u "${ANALYSIS_SCRIPT}"
    A_EXIT=$?
    if [ $A_EXIT -eq 0 ]; then
        echo "[$(date '+%F %T')] ANALYSIS BASARILI"
        break
    else
        a_retry=$((a_retry+1))
        if [ $a_retry -lt $ANALYSIS_MAX_RETRY ]; then
            sleep 10
        fi
    fi
done

echo "[$(date '+%F %T')] TAMAMLANDI"

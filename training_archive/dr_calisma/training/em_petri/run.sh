#!/bin/bash
# run_petri.sh — Auto-restart wrapper for training.py
# Eger Python cokerse otomatik yeniden baslatir.
# Model-level skip sayesinde tamamlanan modeller atlanir.
#
# Usage:
#   nohup bash /home/user02/dr/training/run_petri.sh >> /home/user02/dr/all_training.log 2>&1 &
#
# Stop:
#   pkill -f "run_petri.sh"
#   pkill -f "training.py"

set -u

SCRIPT_DIR="/home/user02/dr/training/em_petri"
WORK_DIR="/home/user02/dr"
VENV="/home/user02/ml_1/bin/activate"
PY_SCRIPT="${SCRIPT_DIR}/training.py"
ANALYSIS_SCRIPT="${SCRIPT_DIR}/analysis.py"
LOG="${WORK_DIR}/all_training.log"
MAX_RETRIES=50
RETRY_DELAY=15

source "${VENV}"
cd "${WORK_DIR}"

echo ""
echo "================================================================================"
echo "[$(date '+%F %T')] run_petri.sh basladi | PID=$$"
echo "================================================================================"

retry=0
while [ $retry -lt $MAX_RETRIES ]; do
    echo ""
    echo "[$(date '+%F %T')] DENEME $((retry+1))/$MAX_RETRIES — training.py baslatiliyor..."

    python -u "${PY_SCRIPT}"
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "[$(date '+%F %T')] BASARILI: training.py normal sonlandi (exit=0)"
        echo "================================================================================"
        break
    else
        retry=$((retry+1))
        echo ""
        echo "[$(date '+%F %T')] COKUS: exit=$EXIT_CODE | retry=$retry/$MAX_RETRIES"
        if [ $retry -lt $MAX_RETRIES ]; then
            echo "[$(date '+%F %T')] ${RETRY_DELAY}s sonra yeniden deneniyor..."
            sleep $RETRY_DELAY
        fi
    fi
done

if [ $retry -ge $MAX_RETRIES ]; then
    echo ""
    echo "[$(date '+%F %T')] MAKSIMUM RETRY ASILDI ($MAX_RETRIES) — durduruluyor"
    exit 1
fi

echo ""
echo "[$(date '+%F %T')] Tum egitim tamamlandi. analysis.py baslatiliyor..."

# Analysis retry loop (separate from training retry)
ANALYSIS_MAX_RETRY=5
ANALYSIS_RETRY_DELAY=10
a_retry=0
while [ $a_retry -lt $ANALYSIS_MAX_RETRY ]; do
    echo ""
    echo "[$(date '+%F %T')] ANALIZ DENEME $((a_retry+1))/$ANALYSIS_MAX_RETRY"
    python -u "${ANALYSIS_SCRIPT}"
    A_EXIT=$?
    if [ $A_EXIT -eq 0 ]; then
        echo ""
        echo "[$(date '+%F %T')] ANALIZ BASARILI (exit=0)"
        break
    else
        a_retry=$((a_retry+1))
        echo ""
        echo "[$(date '+%F %T')] ANALIZ COKUS: exit=$A_EXIT | retry=$a_retry/$ANALYSIS_MAX_RETRY"
        if [ $a_retry -lt $ANALYSIS_MAX_RETRY ]; then
            echo "[$(date '+%F %T')] ${ANALYSIS_RETRY_DELAY}s sonra tekrar deneniyor..."
            echo "[$(date '+%F %T')] (Basarili olan bolumler skip edilecek)"
            sleep $ANALYSIS_RETRY_DELAY
        fi
    fi
done

if [ $a_retry -ge $ANALYSIS_MAX_RETRY ]; then
    echo "[$(date '+%F %T')] ANALIZ MAX RETRY ASILDI"
    exit 2
fi

echo "[$(date '+%F %T')] TUM SURE@ TAMAMLANDI (egitim + analiz)"

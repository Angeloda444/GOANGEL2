#!/bin/bash
set +e

if [ -z "${STAGE}" ]; then
  echo "STAGE env var requis" >&2
  exit 2
fi

export GH_TOKEN="${GITHUB_TOKEN}"

echo "═══════════════════════════════════════════════════════════"
echo "  GOANGEL STAGE : ${STAGE}"
echo "  Repo          : ${GITHUB_REPOSITORY}"
echo "  Run ID        : ${GITHUB_RUN_ID}"
echo "  Attempt       : ${GITHUB_RUN_ATTEMPT}"
echo "═══════════════════════════════════════════════════════════"

pip install --upgrade pip -q
pip install -q requests python-dotenv numpy pandas scipy scikit-learn
pip install -q xgboost lightgbm catboost penaltyblog
pip install -q torch --index-url https://download.pytorch.org/whl/cpu

cat > .env <<ENVEOF
BZZOIRO_TOKENS="${TOKENS}"
BZZOIRO_WORKERS_PER_KEY=${WORKERS_PER_KEY}
BZZOIRO_MAX_WORKERS=${MAX_WORKERS}
BZZOIRO_RATE_LIMIT_PER_MINUTE=${RATE_LIMIT}
BZZOIRO_RATE_LIMIT_SAFETY_MARGIN=1
BZZOIRO_HISTORICAL_SEASONS_LOOKBACK=${SEASONS}
BZZOIRO_ENRICH_XG=${ENRICH}
API_MAX_RETRIES=6
API_RETRY_BACKOFF_SECONDS=0.4
API_TIMEOUT_SECONDS=25
GOANGEL_CACHE_DIR=./cache
GOANGEL_LOG_LEVEL=INFO
GOANGEL_GITHUB_PUSH=true
GOANGEL_GITHUB_REPO=${GITHUB_REPOSITORY}
GOANGEL_GITHUB_USER=${GITHUB_REPOSITORY_OWNER}
GOANGEL_GITHUB_BRANCH=cache-auto
GH_PAT=${GITHUB_TOKEN}
GOANGEL_MAX_ATTEMPTS_PER_MODEL=${MAX_ATTEMPTS}
ENVEOF

mkdir -p cache
if gh api "repos/${GITHUB_REPOSITORY}/branches/cache-auto" >/dev/null 2>&1; then
  echo "↻ Restauration cache-auto..."
  rm -rf /tmp/ckpt_restore
  git clone --depth 1 --branch cache-auto \
    "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" \
    /tmp/ckpt_restore 2>/dev/null
  if [ -d /tmp/ckpt_restore/cache ]; then
    cp -r /tmp/ckpt_restore/cache/. cache/ 2>/dev/null || true
  fi
fi

if [ -f "cache/stages/done/${STAGE}.done" ]; then
  echo "✅ Stage ${STAGE} déjà terminé (marqueur .done présent) — skip"
  exit 0
fi

mkdir -p cache/stages/attempts
ATTEMPT_FILE="cache/stages/attempts/${STAGE}.json"
if [ -f "${ATTEMPT_FILE}" ]; then
  ATTEMPT_COUNT=$(python3 -c "import json; print(json.load(open('${ATTEMPT_FILE}')).get('count',0))" 2>/dev/null || echo 0)
else
  ATTEMPT_COUNT=0
fi

if [ "${ATTEMPT_COUNT}" -ge "${MAX_ATTEMPTS}" ]; then
  echo "❌ Stage ${STAGE} : ${MAX_ATTEMPTS} tentatives épuisées — ARRÊT DÉFINITIF"
  exit 3
fi

NEW_COUNT=$((ATTEMPT_COUNT + 1))
echo "{\"count\": ${NEW_COUNT}, \"stage\": \"${STAGE}\", \"last_attempt\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"max\": ${MAX_ATTEMPTS}}" > "${ATTEMPT_FILE}"
echo "▶️  Tentative ${NEW_COUNT}/${MAX_ATTEMPTS} pour ${STAGE}"

START_TS=$(date +%s)
START_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

TIMEOUT_SECONDS="${STAGE_TIMEOUT_SECONDS:-21600}"

echo "─────────────────────────────────────────────────────────────"
echo "▶️  Démarrage Python"
echo "   Heure début    : ${START_DATE}"
echo "   Timeout prévu  : ${TIMEOUT_SECONDS}s ($((${TIMEOUT_SECONDS} / 3600))h)"
echo "   Commande       : python3 -u main.py --stage ${STAGE}"
echo "─────────────────────────────────────────────────────────────"

set +e
python3 -u main.py --stage "${STAGE}" > training.log 2>&1 &
PYTHON_PID=$!

# Boucle de surveillance : attend ou timeout
ELAPSED=0
KILLED_BY_TIMEOUT=0
while kill -0 ${PYTHON_PID} 2>/dev/null; do
  sleep 10
  ELAPSED=$((ELAPSED + 10))

  if [ ${ELAPSED} -ge ${TIMEOUT_SECONDS} ]; then
    echo "⏰ Timeout (${TIMEOUT_SECONDS}s) atteint, arrêt propre..."
    kill -TERM ${PYTHON_PID} 2>/dev/null
    sleep 30
    kill -KILL ${PYTHON_PID} 2>/dev/null
    KILLED_BY_TIMEOUT=1
    break
  fi
done

wait ${PYTHON_PID}
RC=$?
set -e

END_TS=$(date +%s)
END_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DURATION=$((END_TS - START_TS))

echo "─────────────────────────────────────────────────────────────"
echo "🏁 Python terminé"
echo "   Heure fin      : ${END_DATE}"
echo "   Durée          : ${DURATION}s ($((${DURATION} / 60)) min)"
echo "   Exit code      : ${RC}"
echo "   Timeout atteint: ${KILLED_BY_TIMEOUT}"
echo "─────────────────────────────────────────────────────────────"

# Afficher les 100 dernières lignes du log
echo ""
echo "─── Dernières 100 lignes du log Python ───"
tail -100 training.log
echo "─────────────────────────────────────────"

# Interpréter le code retour
if [ ${KILLED_BY_TIMEOUT} -eq 1 ]; then
  RC=124
fi

echo "↻ Push cache-auto..."
cd /tmp && rm -rf gopush
git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" gopush 2>/dev/null
cd gopush
git config user.email "actions@users.noreply.github.com"
git config user.name "GOANGEL Auto"
git checkout -B cache-auto
mkdir -p cache
if [ -d "${GITHUB_WORKSPACE}/cache" ]; then
  cp -r "${GITHUB_WORKSPACE}/cache/." cache/ 2>/dev/null || true
fi
git add -A
git commit -m "checkpoint ${STAGE} run${GITHUB_RUN_ID} att${NEW_COUNT} rc${RC} $(date +%s)" || echo "no changes"

PUSH_OK=0
for push_attempt in 1 2 3; do
  echo "  Push tentative ${push_attempt}/3..."
  if git push origin cache-auto --force 2>&1; then
    PUSH_OK=1
    break
  fi
  sleep 5
done
cd "${GITHUB_WORKSPACE}"

if [ "${PUSH_OK}" != "1" ]; then
  echo "❌ PUSH cache-auto ÉCHOUÉ après 3 tentatives"
  echo "::error::Impossible de persister l'état sur GitHub — ARRÊT DE LA CHAÎNE"
  exit 5
fi
echo "✅ cache-auto pushé (stage=${STAGE})"

if [ "${RC}" = "0" ]; then
  if [ "${IS_RETRY}" = "true" ]; then
    NEXT=$(python3 main.py --stage next 2>/dev/null | grep '^NEXT:' | cut -d: -f2 | tr -d '[:space:]')
    echo "🔗 Stage suivant détecté : ${NEXT}"
    if [ -n "${NEXT}" ] && [ "${NEXT}" != "DONE" ]; then
      sleep 12
      gh workflow run train.yml --repo "${GITHUB_REPOSITORY}" \
        -f seasons_lookback=${SEASONS} \
        -f enrich_xg=${ENRICH} \
        -f workers_per_key=${WORKERS_PER_KEY} \
        -f max_workers=${MAX_WORKERS} \
        -f rate_limit_per_minute=${RATE_LIMIT} \
        -f max_attempts_per_model=${MAX_ATTEMPTS} \
        -f force_stage=${NEXT} \
        -f is_retry=true
      echo "🚀 Nouveau run déclenché pour ${NEXT}"
    fi
  fi
  exit 0
fi

if [ "${RC}" = "124" ] || [ "${RC}" = "143" ]; then
  echo "⏰ TIMEOUT volontaire sur ${STAGE} (RC=${RC}) — relance dans un nouveau run"
  sleep 15
  gh workflow run train.yml --repo "${GITHUB_REPOSITORY}" \
    -f seasons_lookback=${SEASONS} \
    -f enrich_xg=${ENRICH} \
    -f workers_per_key=${WORKERS_PER_KEY} \
    -f max_workers=${MAX_WORKERS} \
    -f rate_limit_per_minute=${RATE_LIMIT} \
    -f max_attempts_per_model=${MAX_ATTEMPTS} \
    -f force_stage=${STAGE} \
    -f is_retry=true
  exit 1
fi

echo "❌ HARD FAILURE sur ${STAGE} (RC=${RC}) — ARRÊT DE LA CHAÎNE"
exit 1

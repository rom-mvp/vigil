#!/bin/bash
set -e

echo "🔭 Starting Vigil Security Gateway..."
echo "   Environment: ${VIGIL_ENV:-local}"
echo "   Python Path: ${PYTHONPATH:-/app/src}"

# Check if Redis is accessible (if configured)
if [ ! -z "$VIGIL_REDIS_HOST" ]; then
	echo "   Redis: ${VIGIL_REDIS_HOST}:${VIGIL_REDIS_PORT:-6379}"
fi

# Start the local server using Python module
cd /app
python3 -m vigil.local_server

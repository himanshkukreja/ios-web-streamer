#!/bin/bash

# Test the streaming server with generated video (no iOS required)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting server in test mode..."
echo "Open http://localhost:8080 in your browser to view the test stream."
echo ""

"$SCRIPT_DIR/start-server.sh" --test

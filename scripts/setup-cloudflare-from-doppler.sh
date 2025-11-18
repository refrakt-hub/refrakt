#!/usr/bin/env bash
# Setup Cloudflare tunnel configs from Doppler secrets
# This script pulls dev.yml, prod.yml, and credential JSON files from Doppler
# and writes them to the filesystem for cloudflared to use.
#
# Usage:
#   ./scripts/setup-cloudflare-from-doppler.sh [dev|prod]
#   If no argument provided, uses current Doppler config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Determine which config to use
CONFIG_ARG="${1:-}"
if [ -n "$CONFIG_ARG" ]; then
    DOPPLER_CONFIG="$CONFIG_ARG"
    echo "🔐 Setting up Cloudflare configs from Doppler (config: $DOPPLER_CONFIG)..."
    # Temporarily switch to the specified config
    DOPPLER_CMD="doppler secrets get -c $DOPPLER_CONFIG"
else
    DOPPLER_CONFIG=$(doppler configure get config --plain 2>/dev/null || echo "dev")
    echo "🔐 Setting up Cloudflare configs from Doppler (current config: $DOPPLER_CONFIG)..."
    DOPPLER_CMD="doppler secrets get"
fi

# Ensure cloudflare directory exists
mkdir -p cloudflare

# Pull secrets from Doppler and write config files
# Doppler secrets should be named:
# - CLOUDFLARE_DEV_YML (full content of dev.yml)
# - CLOUDFLARE_PROD_YML (full content of prod.yml)
# - CLOUDFLARE_DEV_CREDENTIALS (full content of dev tunnel JSON)
# - CLOUDFLARE_PROD_CREDENTIALS (full content of prod tunnel JSON)

# Always try to get both dev and prod configs (they're shared across configs)
if $DOPPLER_CMD CLOUDFLARE_DEV_YML --json > /dev/null 2>&1; then
    echo "📝 Writing dev.yml from Doppler..."
    $DOPPLER_CMD CLOUDFLARE_DEV_YML --json | jq -r '.CLOUDFLARE_DEV_YML.computed' > dev.yml
    echo "✅ dev.yml created"
else
    echo "⚠️  CLOUDFLARE_DEV_YML not found in Doppler, skipping dev.yml"
fi

if $DOPPLER_CMD CLOUDFLARE_PROD_YML --json > /dev/null 2>&1; then
    echo "📝 Writing prod.yml from Doppler..."
    $DOPPLER_CMD CLOUDFLARE_PROD_YML --json | jq -r '.CLOUDFLARE_PROD_YML.computed' > prod.yml
    echo "✅ prod.yml created"
else
    echo "⚠️  CLOUDFLARE_PROD_YML not found in Doppler, skipping prod.yml"
fi

# Extract tunnel ID from dev.yml to determine credential filename
if [ -f dev.yml ]; then
    DEV_TUNNEL_ID=$(grep -E "^tunnel:" dev.yml | awk '{print $2}' | tr -d '\r\n')
    if [ -n "$DEV_TUNNEL_ID" ]; then
        if $DOPPLER_CMD CLOUDFLARE_DEV_CREDENTIALS --json > /dev/null 2>&1; then
            echo "📝 Writing dev tunnel credentials..."
            $DOPPLER_CMD CLOUDFLARE_DEV_CREDENTIALS --json | jq -r '.CLOUDFLARE_DEV_CREDENTIALS.computed' > "cloudflare/${DEV_TUNNEL_ID}.json"
            echo "✅ cloudflare/${DEV_TUNNEL_ID}.json created"
        else
            echo "⚠️  CLOUDFLARE_DEV_CREDENTIALS not found in Doppler, skipping dev credentials"
        fi
    fi
fi

# Extract tunnel ID from prod.yml to determine credential filename
if [ -f prod.yml ]; then
    PROD_TUNNEL_ID=$(grep -E "^tunnel:" prod.yml | awk '{print $2}' | tr -d '\r\n')
    if [ -n "$PROD_TUNNEL_ID" ]; then
        if $DOPPLER_CMD CLOUDFLARE_PROD_CREDENTIALS --json > /dev/null 2>&1; then
            echo "📝 Writing prod tunnel credentials..."
            $DOPPLER_CMD CLOUDFLARE_PROD_CREDENTIALS --json | jq -r '.CLOUDFLARE_PROD_CREDENTIALS.computed' > "cloudflare/${PROD_TUNNEL_ID}.json"
            echo "✅ cloudflare/${PROD_TUNNEL_ID}.json created"
        else
            echo "⚠️  CLOUDFLARE_PROD_CREDENTIALS not found in Doppler, skipping prod credentials"
        fi
    fi
fi

echo ""
echo "✅ Cloudflare configs setup complete!"
echo "🔍 Validating configs..."
if [ -f dev.yml ]; then
    cloudflared tunnel --config dev.yml validate 2>/dev/null && echo "✅ dev.yml is valid" || echo "⚠️  dev.yml validation failed"
fi
if [ -f prod.yml ]; then
    cloudflared tunnel --config prod.yml validate 2>/dev/null && echo "✅ prod.yml is valid" || echo "⚠️  prod.yml validation failed"
fi


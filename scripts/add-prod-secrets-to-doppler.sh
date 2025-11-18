#!/usr/bin/env bash
# Helper script to add secrets from prod.env to Doppler (prod config)
# Run this once to migrate your secrets from prod.env to Doppler

set -euo pipefail

echo "🔐 Adding secrets to Doppler (refrakt/prod)..."
echo ""
echo "⚠️  This will add secrets from your prod.env file to Doppler."
echo "⚠️  Make sure you're authenticated: doppler login"
echo "⚠️  Make sure you're using the 'prod' config: doppler setup (select prod)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

# Verify we're using prod config
CURRENT_CONFIG=$(doppler configure get config --plain 2>/dev/null || echo "")
if [ "$CURRENT_CONFIG" != "prod" ]; then
    echo "⚠️  Warning: Current Doppler config is '$CURRENT_CONFIG', not 'prod'"
    echo "   Run: doppler setup (and select 'prod' config)"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 1
    fi
fi

# Add secrets from prod.env
echo "📝 Adding secrets from prod.env..."

# Read prod.env and add each secret to Doppler
while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    
    # Remove leading/trailing whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    
    # Skip if value is empty
    [[ -z "$value" ]] && continue
    
    echo "  Adding: $key"
    echo "$value" | doppler secrets set "$key" --no-interactive || {
        echo "  ⚠️  Failed to add $key (might already exist)"
    }
done < prod.env

echo ""
echo "✅ Secrets from prod.env added to Doppler (prod config)!"
echo ""
echo "📝 Cloudflare configs should already be in Doppler (shared between dev/prod):"
echo "   - CLOUDFLARE_PROD_YML"
echo "   - CLOUDFLARE_PROD_CREDENTIALS"
echo ""
echo "   If not, add them manually:"
echo "   doppler secrets set CLOUDFLARE_PROD_YML -- < prod.yml"
echo "   doppler secrets set CLOUDFLARE_PROD_CREDENTIALS -- < cloudflare/220bc2f3-cd03-4c06-b658-20c8c718cc04.json"


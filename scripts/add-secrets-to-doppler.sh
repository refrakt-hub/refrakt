#!/usr/bin/env bash
# Helper script to add secrets from dev.env to Doppler
# Run this once to migrate your secrets from dev.env to Doppler

set -euo pipefail

echo "🔐 Adding secrets to Doppler (refrakt/dev)..."
echo ""
echo "⚠️  This will add secrets from your dev.env file to Doppler."
echo "⚠️  Make sure you're authenticated: doppler login"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

# Add secrets from dev.env
echo "📝 Adding secrets from dev.env..."

# Read dev.env and add each secret to Doppler
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
done < dev.env

echo ""
echo "✅ Secrets from dev.env added to Doppler!"
echo ""
echo "📝 Next, add Cloudflare configs manually:"
echo "   doppler secrets set CLOUDFLARE_DEV_YML -- < dev.yml"
echo "   doppler secrets set CLOUDFLARE_PROD_YML -- < prod.yml"
echo "   doppler secrets set CLOUDFLARE_DEV_CREDENTIALS -- < cloudflare/1b304a4e-dcc4-4145-a59b-da05876d926a.json"
echo "   doppler secrets set CLOUDFLARE_PROD_CREDENTIALS -- < cloudflare/220bc2f3-cd03-4c06-b658-20c8c718cc04.json"


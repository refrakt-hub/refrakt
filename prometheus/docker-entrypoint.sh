#!/bin/sh
# Entrypoint script to inject PROMETHEUS_BEARER_TOKEN into prometheus.yml

set -e

# Get bearer token from environment
BEARER_TOKEN="${PROMETHEUS_BEARER_TOKEN:-}"

# Copy config file to a writable location
cp /etc/prometheus/prometheus.yml /tmp/prometheus.yml

# If bearer token is set, inject it into prometheus.yml
if [ -n "$BEARER_TOKEN" ]; then
    echo "Bearer token found, injecting into prometheus.yml..."
    # Add bearer_token after scheme line, before static_configs
    # First, remove any existing bearer_token lines (commented or not)
    sed -i '/bearer_token:/d' /tmp/prometheus.yml
    # Add bearer_token after scheme line
    sed -i "/scheme: 'http'/a\    bearer_token: '${BEARER_TOKEN}'" /tmp/prometheus.yml
    echo "Bearer token injected successfully"
    CONFIG_FILE="/tmp/prometheus.yml"
else
    echo "No bearer token set, metrics endpoint may require authentication"
    CONFIG_FILE="/etc/prometheus/prometheus.yml"
fi

# Replace config file path in arguments
ARGS=""
for arg in "$@"; do
    if echo "$arg" | grep -q "config.file"; then
        ARGS="$ARGS --config.file=$CONFIG_FILE"
    else
        ARGS="$ARGS $arg"
    fi
done

# Execute Prometheus with modified arguments
exec /bin/prometheus $ARGS


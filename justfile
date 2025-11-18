# Justfile for Refrakt Application
# Natural Language Orchestrator for Scalable ML/DL Workflows

# Load environment variables from dev.env by default
set dotenv-path := "dev.env"

# Setup tunnel credentials from Doppler (run once or when configs change)
setup-tunnels:
    #!/usr/bin/env bash
    echo "🔐 Setting up Cloudflare tunnel configs from Doppler..."
    if [ -f scripts/setup-cloudflare-from-doppler.sh ]; then
        ./scripts/setup-cloudflare-from-doppler.sh
    else
        echo "⚠️  Setup script not found. Please run manually:"
        echo "   ./scripts/setup-cloudflare-from-doppler.sh"
    fi

# Install all dependencies in editable mode
install:
    #!/usr/bin/env bash
    echo "📦 Installing Refrakt dependencies..."
    echo "🔧 Setting up UV virtual environment..."
    uv venv
    echo "🔧 Installing editable packages..."
    uv run pip install --editable ./src/refrakt_core
    uv run pip install --editable ./src/refrakt_cli  
    uv run pip install --editable ./src/refrakt_viz
    uv run pip install --editable ./src/refrakt_xai
    echo "🔧 Installing backend dependencies..."
    uv run pip install -r pyproject.toml
    echo "✅ Installation complete!"

# Individual process commands
start-tunnel:
    #!/usr/bin/env bash
    echo "🌐 Starting Cloudflare tunnel (dev)..."
    echo "🔗 Tunnel will be available at: $CLOUDFLARE_DOMAIN"
    cloudflared tunnel --config $CLOUDFLARE_TUNNEL_CONFIG run

start-backend:
    #!/usr/bin/env bash
    echo "🚀 Starting Refrakt backend (dev)..."
    echo "📡 Backend will be available at: http://localhost:$PORT"
    echo "📚 API docs: http://localhost:$PORT/docs"
    # Set PYTHONPATH to include backend directory for absolute imports
    export PYTHONPATH="${PWD}/backend:${PYTHONPATH:-}"
    uv run python -m backend.main

# Start backend with Doppler (secrets from Doppler instead of dev.env)
start-backend-doppler:
    #!/usr/bin/env bash
    echo "🚀 Starting Refrakt backend (dev) with Doppler..."
    echo "📡 Backend will be available at: http://localhost:$PORT"
    echo "📚 API docs: http://localhost:$PORT/docs"
    # Set PYTHONPATH to include backend directory for absolute imports
    export PYTHONPATH="${PWD}/backend:${PYTHONPATH:-}"
    doppler run -- uv run python -m backend.main

# Start tunnel with Doppler (if tunnel config needs secrets from Doppler)
start-tunnel-doppler:
    #!/usr/bin/env bash
    echo "🌐 Starting Cloudflare tunnel (dev) with Doppler..."
    echo "🔗 Tunnel will be available at: $CLOUDFLARE_DOMAIN"
    doppler run -- cloudflared tunnel --config $CLOUDFLARE_TUNNEL_CONFIG run

# Start infrastructure services (Redis, Prometheus, Worker) via Docker Compose
start-infra:
    #!/usr/bin/env bash
    echo "🐳 Starting infrastructure services (Redis, Prometheus, Worker)..."
    # Stop backend service if running (we run it locally, not in Docker)
    docker compose stop backend 2>/dev/null || true
    # Export UID/GID for docker-compose to use (for proper file permissions)
    export UID=$(id -u)
    export GID=$(id -g)
    # Start services in detached mode (logs will be shown via mprocs)
    docker compose up -d redis prometheus worker
    echo "⏳ Waiting for services to be healthy..."
    sleep 5
    # Ensure Redis container is running; backend connects via host port (see dev.env QUEUE_URL)
    if ! docker compose ps redis | grep -q "Up"; then
        echo "❌ Redis failed to start"
        exit 1
    fi
    echo "✅ Infrastructure services started"
    echo "📝 Note: Backend running locally will connect to Redis at localhost:6380"

# Individual log streaming commands for Docker services
start-redis-logs:
    #!/usr/bin/env bash
    docker compose logs -f redis

start-prometheus-logs:
    #!/usr/bin/env bash
    docker compose logs -f prometheus

start-worker-logs:
    #!/usr/bin/env bash
    docker compose logs -f worker

# Main start command with mprocs (all processes with logs)
start:
    #!/usr/bin/env bash
    echo "🚀 Starting Refrakt development environment..."
    # Start infrastructure services first (detached)
    just start-infra
    # Then start all processes with mprocs (tunnel, backend, and Docker service logs)
    # Wrapped in `script` to ensure a proper PTY so mprocs doesn't hit "No such device or address (os error 6)"
    script -q -c 'mprocs \
        --names "tunnel,backend,redis,prometheus,worker" \
        "just start-tunnel" \
        "just start-backend" \
        "just start-redis-logs" \
        "just start-prometheus-logs" \
        "just start-worker-logs"' /dev/null

# Start with Doppler (secrets from Doppler instead of dev.env)
start-doppler:
    #!/usr/bin/env bash
    echo "🚀 Starting Refrakt development environment with Doppler..."
    # Pull Cloudflare configs from Doppler first
    if [ -f scripts/setup-cloudflare-from-doppler.sh ]; then
        echo "🔐 Pulling Cloudflare configs from Doppler..."
        ./scripts/setup-cloudflare-from-doppler.sh
    fi
    # Start infrastructure services first (detached)
    just start-infra
    # Then start all processes with mprocs using Doppler for secrets
    script -q -c 'mprocs \
        --names "tunnel,backend,redis,prometheus,worker" \
        "just start-tunnel-doppler" \
        "just start-backend-doppler" \
        "just start-redis-logs" \
        "just start-prometheus-logs" \
        "just start-worker-logs"' /dev/null

# Development helper
dev:
    just install
    just start

# Clean up processes
stop:
    #!/usr/bin/env bash
    echo "🛑 Stopping all Refrakt processes..."
    # Stop mprocs (which will stop tunnel and backend)
    pkill -f "mprocs.*tunnel,backend,redis,prometheus,worker" 2>/dev/null || true
    # Stop any orphaned processes
    pkill -f "cloudflared" 2>/dev/null || echo "No cloudflared processes found"
    pkill -f "python -m backend.main" 2>/dev/null || echo "No backend processes found"
    echo "🐳 Stopping all Docker services..."
    docker compose stop redis prometheus worker backend 2>/dev/null || echo "No docker services running"
    echo "✅ All processes stopped"

# Stop infrastructure services only
stop-infra:
    #!/usr/bin/env bash
    echo "🐳 Stopping infrastructure services..."
    docker compose stop redis prometheus worker
    echo "✅ Infrastructure services stopped"

# Quick development restart
restart:
    just stop
    sleep 2
    just start

# Show status of running processes
status:
    #!/usr/bin/env bash
    echo "🔍 Checking Refrakt processes..."
    echo ""
    echo "Cloudflare tunnels:"
    ps aux | grep cloudflared | grep -v grep || echo "  No tunnel processes running"
    echo ""
    echo "Backend processes:"
    ps aux | grep "python -m backend.main" | grep -v grep || echo "  No backend processes running"
    echo ""
    echo "Docker services:"
    docker compose ps 2>/dev/null || echo "  Docker compose not running"
    echo ""
    echo "Port usage:"
    netstat -tlnp 2>/dev/null | grep -E ":(8001|8002)" || echo "  No Refrakt ports in use"

# Test tunnel connectivity
test-tunnel:
    #!/usr/bin/env bash
    echo "🧪 Testing tunnel connectivity..."
    echo "Testing dev tunnel: dev.akshath.tech"
    curl -I https://dev.akshath.tech || echo "❌ Dev tunnel not accessible"
    echo ""
    echo "Testing prod tunnel: refrakt.akshath.tech"
    curl -I https://refrakt.akshath.tech || echo "❌ Prod tunnel not accessible"

# Show logs
logs:
    #!/usr/bin/env bash
    echo "📋 Recent backend logs:"
    tail -n 50 $LOGS_DIR/backend.log 2>/dev/null || echo "No logs found"

# Clean up old jobs and checkpoints
clean:
    #!/usr/bin/env bash
    echo "🧹 Cleaning up old jobs and checkpoints..."
    find ./jobs -name "*.log" -mtime +7 -delete 2>/dev/null || true
    find ./checkpoints -name "*.pth" -mtime +30 -delete 2>/dev/null || true
    echo "✅ Cleanup complete"

# Help command
help:
    #!/usr/bin/env bash
    echo "🔧 Refrakt Just Commands:"
    echo ""
    echo "Setup:"
    echo "  just install          - Install all dependencies"
    echo "  just setup-tunnels    - Validate tunnel configuration"
    echo ""
    echo "Development:"
    echo "  just dev              - Install deps and start dev environment"
    echo "  just start            - Start dev environment with mprocs (all processes: tunnel, backend, redis, prometheus, worker)"
    echo "  just start-doppler    - Start dev environment with Doppler secrets (recommended)"
    echo "  just restart          - Restart dev environment"
    echo ""
    echo "Individual processes:"
    echo "  just start-tunnel     - Start tunnel only"
    echo "  just start-backend    - Start backend only"
    echo "  just start-backend-doppler - Start backend with Doppler secrets"
    echo "  just start-tunnel-doppler  - Start tunnel with Doppler secrets"
    echo "  just start-infra      - Start infrastructure (Redis, Prometheus, Worker) via Docker"
    echo "  just start-redis-logs - Stream Redis logs"
    echo "  just start-prometheus-logs - Stream Prometheus logs"
    echo "  just start-worker-logs - Stream Worker logs"
    echo "  just stop-infra       - Stop infrastructure services"
    echo ""
    echo "Management:"
    echo "  just stop             - Stop all processes"
    echo "  just status           - Show running processes"
    echo "  just logs             - Show recent logs"
    echo "  just clean            - Clean old jobs/checkpoints"
    echo ""
    echo "Testing:"
    echo "  just test-tunnel      - Test tunnel connectivity"
    echo ""
    echo "Help:"
    echo "  just help             - Show this help message"

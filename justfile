# Justfile for Refrakt Application
# Natural Language Orchestrator for Scalable ML/DL Workflows

# Load environment variables from dev.env by default
set dotenv-path := "dev.env"

# Setup tunnel credentials (run once)
setup-tunnels:
    #!/usr/bin/env bash
    echo "✅ Tunnel credentials already set up in cloudflare/ directory"
    echo "📁 Dev tunnel: cloudflare/1b304a4e-dcc4-4145-a59b-da05876d926a.json"
    echo "📁 Prod tunnel: cloudflare/220bc2f3-cd03-4c06-b658-20c8c718cc04.json"
    echo ""
    echo "🔍 Validating tunnel configs..."
    cloudflared tunnel --config dev.yml validate
    cloudflared tunnel --config prod.yml validate

# Install all dependencies in editable mode
install:
    #!/usr/bin/env bash
    echo "📦 Installing Refrakt dependencies..."
    uv sync
    echo "🔧 Installing editable packages..."
    uv pip install --editable ./src/refrakt_core
    uv pip install --editable ./src/refrakt_cli  
    uv pip install --editable ./src/refrakt_viz
    uv pip install --editable ./src/refrakt_xai
    echo "✅ Installation complete!"

# Start all services (development)
start:
    just start-tunnel-dev &
    just start-backend-dev
    wait

# Cloudflare tunnel (development)
start-tunnel-dev:
    #!/usr/bin/env bash
    echo "🌐 Starting Cloudflare tunnel (dev)..."
    echo "🔗 Tunnel will be available at: $CLOUDFLARE_DOMAIN"
    cloudflared tunnel --config $CLOUDFLARE_TUNNEL_CONFIG run

# Backend (development)
start-backend-dev:
    #!/usr/bin/env bash
    echo "🚀 Starting Refrakt backend (dev)..."
    echo "📡 Backend will be available at: http://localhost:$PORT"
    echo "📚 API docs: http://localhost:$PORT/docs"
    uv run python backend.py dev

# Production commands (use justfile.prod)
start-prod:
    #!/usr/bin/env bash
    echo "🚀 Starting production environment..."
    echo "💡 Use: just --justfile justfile.prod start"
    just --justfile justfile.prod start

# Clean up processes
stop:
    #!/usr/bin/env bash
    echo "🛑 Stopping all Refrakt processes..."
    pkill -f cloudflared || echo "No cloudflared processes found"
    pkill -f "python backend.py" || echo "No backend processes found"
    echo "✅ All processes stopped"

# Development helpers
dev:
    just install
    just start

# Production deployment
deploy:
    just install
    just start-prod

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
    ps aux | grep "python backend.py" | grep -v grep || echo "  No backend processes running"
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
    echo "  just start            - Start dev environment (tunnel + backend)"
    echo "  just restart          - Restart dev environment"
    echo ""
    echo "Production:"
    echo "  just deploy           - Install deps and start prod environment"
    echo "  just start-prod       - Start prod environment (uses justfile.prod)"
    echo "  just --justfile justfile.prod start  - Direct prod start"
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

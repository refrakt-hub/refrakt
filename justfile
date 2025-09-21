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
    uv run python backend.py dev

# Main start command with mprocs (two-column layout)
start:
    mprocs \
        --names "tunnel,backend" \
        "just start-tunnel" \
        "just start-backend"

# Development helper
dev:
    just install
    just start

# Clean up processes
stop:
    #!/usr/bin/env bash
    echo "🛑 Stopping all Refrakt processes..."
    -pkill -f "mprocs.*tunnel,backend"
    -pkill -f "cloudflared" || echo "No cloudflared processes found"
    -pkill -f "python backend.py" || echo "No backend processes found"
    echo "✅ All processes stopped"

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
    echo "  just start            - Start dev environment with mprocs (two-column layout)"
    echo "  just restart          - Restart dev environment"
    echo ""
    echo "Individual processes:"
    echo "  just start-tunnel     - Start tunnel only"
    echo "  just start-backend    - Start backend only"
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

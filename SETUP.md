# Refrakt Setup Guide

## Quick Start

```bash
# Install dependencies and start development environment
just dev

# Or step by step:
just install
just start
```

## Available Commands

### Setup Commands
- `just install` - Install all dependencies (UV + editable packages)
- `just setup-tunnels` - Validate tunnel configuration

### Development Commands
- `just dev` - Install deps and start dev environment
- `just start` - Start dev environment (tunnel + backend)
- `just restart` - Restart dev environment
- `just stop` - Stop all processes

### Production Commands
- `just deploy` - Install deps and start prod environment
- `just start-prod` - Start prod environment

### Management Commands
- `just status` - Show running processes
- `just logs` - Show recent logs
- `just clean` - Clean old jobs/checkpoints
- `just test-tunnel` - Test tunnel connectivity

### Help
- `just help` - Show all available commands

## Environment Configuration

### Development Environment
- **Backend Port**: 8001
- **Domain**: dev.akshath.tech
- **Tunnel Config**: `dev.yml`
- **Environment File**: `dev.env`

### Production Environment
- **Backend Port**: 8002
- **Domain**: refrakt.akshath.tech
- **Tunnel Config**: `prod.yml`
- **Environment File**: `prod.env`

## File Structure

```
refrakt/
├── justfile              # Process orchestration
├── pyproject.toml        # Root UV workspace config
├── dev.env               # Development environment variables
├── prod.env              # Production environment variables
├── dev.yml               # Development tunnel config
├── prod.yml              # Production tunnel config
├── cloudflare/           # Tunnel credentials (gitignored)
│   ├── 1b304a4e-...json  # Dev tunnel credentials
│   └── 220bc2f3-...json  # Prod tunnel credentials
├── backend.py            # FastAPI backend server
├── src/                  # Refrakt packages (editable installs)
│   ├── refrakt_core/
│   ├── refrakt_cli/
│   ├── refrakt_viz/
│   └── refrakt_xai/
```

## Security Notes

- Environment files (`dev.env`, `prod.env`) are gitignored
- Cloudflare credentials are gitignored
- API keys are loaded from environment variables
- Use separate API keys for dev/prod environments

## Troubleshooting

### Tunnel Issues
```bash
# Validate tunnel configs
just setup-tunnels

# Test connectivity
just test-tunnel
```

### Process Issues
```bash
# Check status
just status

# Stop all processes
just stop

# Restart
just restart
```

### Dependency Issues
```bash
# Reinstall everything
just install
```

## Migration from Old Setup

The old `start_backend.sh` script is no longer needed. All functionality is now handled by the `justfile`:

- **Old**: `./start_backend.sh dev`
- **New**: `just start`

- **Old**: Manual tunnel management
- **New**: `just start` (handles both tunnel and backend)

## Next Steps

1. Test the setup: `just dev`
2. Verify tunnel connectivity: `just test-tunnel`
3. Check API docs: http://localhost:8001/docs
4. Access via domain: https://dev.akshath.tech

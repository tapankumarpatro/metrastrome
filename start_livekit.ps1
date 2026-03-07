# ── Metrastrome LiveKit Server Manager ──────────────────────────────
# Ensures LiveKit dev server is running in Docker.
# Usage: .\start_livekit.ps1 [-Force] [-Stop]
#   -Force  : Stop existing container and start fresh
#   -Stop   : Stop LiveKit container

param(
    [switch]$Force,
    [switch]$Stop
)

$CONTAINER_NAME = "metrastrome-livekit"
$IMAGE = "livekit/livekit-server"
$PORTS = @("-p", "7880:7880", "-p", "7881:7881", "-p", "7882:7882/udp")

function Write-Status($msg) { Write-Host "[LiveKit] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "[LiveKit] $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "[LiveKit] $msg" -ForegroundColor Yellow }
function Write-Err($msg)    { Write-Host "[LiveKit] $msg" -ForegroundColor Red }

# Check Docker is available
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Docker not found. Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
}

# Stop mode
if ($Stop) {
    Write-Status "Stopping LiveKit..."
    docker stop $CONTAINER_NAME 2>$null
    docker rm $CONTAINER_NAME 2>$null
    Write-Ok "LiveKit stopped."
    exit 0
}

# Check if our named container exists
$existing = docker ps -a --filter "name=$CONTAINER_NAME" --format "{{.ID}}" 2>$null

if ($existing) {
    $running = docker ps --filter "name=$CONTAINER_NAME" --format "{{.ID}}" 2>$null
    if ($running -and -not $Force) {
        # Already running — verify it's healthy
        $health = docker inspect --format "{{.State.Status}}" $CONTAINER_NAME 2>$null
        if ($health -eq "running") {
            Write-Ok "LiveKit already running (container: $CONTAINER_NAME)"
            Write-Ok "  URL: ws://localhost:7880"
            Write-Ok "  API Key: devkey | Secret: secret"
            exit 0
        }
    }
    # Stop and remove existing (stale or forced)
    Write-Status "Removing existing container..."
    docker stop $CONTAINER_NAME 2>$null
    docker rm $CONTAINER_NAME 2>$null
}

# Check if port 7880 is occupied by something else
$portCheck = netstat -ano | Select-String ":7880 " | Select-String "LISTENING"
if ($portCheck) {
    # Find what's using it — might be another LiveKit container with different name
    $otherContainers = docker ps --filter "publish=7880" --format "{{.Names}}" 2>$null
    if ($otherContainers) {
        Write-Warn "Port 7880 used by container: $otherContainers"
        if ($Force) {
            Write-Status "Force mode: stopping $otherContainers..."
            docker stop $otherContainers 2>$null
            docker rm $otherContainers 2>$null
        } else {
            Write-Warn "Run with -Force to stop it, or use that container."
            Write-Ok "  URL: ws://localhost:7880"
            exit 0
        }
    } else {
        Write-Err "Port 7880 is in use by a non-Docker process. Free it manually."
        exit 1
    }
}

# Pull image if not present
$hasImage = docker images $IMAGE --format "{{.Repository}}" 2>$null
if (-not $hasImage) {
    Write-Status "Pulling LiveKit server image..."
    docker pull $IMAGE
}

# Start LiveKit
Write-Status "Starting LiveKit dev server..."
docker run -d --name $CONTAINER_NAME `
    -p 7880:7880 -p 7881:7881 -p 7882:7882/udp `
    --restart unless-stopped `
    $IMAGE --dev

if ($LASTEXITCODE -eq 0) {
    Start-Sleep -Seconds 2
    $running = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Status}}" 2>$null
    if ($running) {
        Write-Ok "LiveKit server started successfully!"
        Write-Ok "  Container: $CONTAINER_NAME"
        Write-Ok "  URL: ws://localhost:7880"
        Write-Ok "  API Key: devkey"
        Write-Ok "  Secret: secret"
        Write-Ok ""
        Write-Ok "Add to backend .env:"
        Write-Ok "  LIVEKIT_URL=ws://localhost:7880"
        Write-Ok "  LIVEKIT_API_KEY=devkey"
        Write-Ok "  LIVEKIT_API_SECRET=secret"
    } else {
        Write-Err "Container started but doesn't appear healthy. Check: docker logs $CONTAINER_NAME"
        exit 1
    }
} else {
    Write-Err "Failed to start LiveKit. Check Docker logs."
    exit 1
}

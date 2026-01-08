<#
.SYNOPSIS
    Install MINE skills (Windows wrapper)
.DESCRIPTION
    Wrapper script to launch the Python-based MINE installer.
    Supports both local execution and remote execution via Invoke-Expression (IEX).
.EXAMPLE
    Local:  .\scripts\install.ps1
    Remote: irm https://raw.githubusercontent.com/uhl-solutions/MINE/main/scripts/install.ps1 | iex
#>

$ErrorActionPreference = "Stop"

# --- 1. Environment Setup ---
$PythonCmd = "python"
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    if (Get-Command "python3" -ErrorAction SilentlyContinue) {
        $PythonCmd = "python3"
    }
    else {
        Write-Host "Error: Python not found. Please install Python 3.9+." -ForegroundColor Red
        exit 1
    }
}

# --- 2. Locate Installer ---
$InstallerPath = $null

# Check if script is running from a file (Local) or IEX (Remote)
if ($PSCommandPath) {
    $ScriptDir = Split-Path -Parent $PSCommandPath
    $TryPath = Join-Path $ScriptDir "install_skills.py"
    if (Test-Path $TryPath) {
        $InstallerPath = $TryPath
    }
}

# Fallback checks for common local structures
if (-not $InstallerPath) {
    $CommonPaths = @(
        ".\scripts\install_skills.py",
        ".\install_skills.py"
    )
    foreach ($Path in $CommonPaths) {
        if (Test-Path $Path) {
            $InstallerPath = (Resolve-Path $Path).Path
            break
        }
    }
}

# --- 3. Execute ---
if ($InstallerPath) {
    # LOCAL MODE
    & $PythonCmd $InstallerPath @args
}
else {
    # REMOTE MODE
    Write-Host "Installer not found locally. Downloading from GitHub..." -ForegroundColor Cyan

    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Write-Host "Error: git is required for remote installation." -ForegroundColor Red
        exit 1
    }

    $TempDir = Join-Path $env:TEMP ("mine_install_" + [Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

    try {
        Write-Host "Cloning MINE repository..." -ForegroundColor Cyan
        git clone --depth 1 https://github.com/uhl-solutions/MINE.git "$TempDir\mine" | Out-Null
        
        $RemoteInstaller = Join-Path "$TempDir\mine" "scripts\install_skills.py"
        
        Write-Host "Running installer..." -ForegroundColor Cyan
        # Pass --source-root explicitly to help the python script find skills
        & $PythonCmd $RemoteInstaller @args --source-root "$TempDir\mine"
    }
    finally {
        if (Test-Path $TempDir) {
            Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

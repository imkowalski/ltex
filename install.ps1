$ErrorActionPreference = "Stop"

# Python-agnostic installer: uv supplies and isolates the Python runtime.
$Root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$UvCommand = Get-Command uv -ErrorAction SilentlyContinue

# Remove stale setuptools output so local source files are packaged afresh.
$BuildDirectory = Join-Path $Root "build"
if (Test-Path -LiteralPath $BuildDirectory) {
    Remove-Item -LiteralPath $BuildDirectory -Recurse -Force
}

if ($null -eq $UvCommand) {
    Write-Host "uv was not found; installing the standalone uv tool manager..."
    irm https://astral.sh/uv/install.ps1 | iex
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $UvCommand) {
        $Candidate = Join-Path $HOME ".local\bin\uv.exe"
        if (Test-Path $Candidate) { $UvCommand = Get-Command $Candidate }
    }
}

if ($null -eq $UvCommand) {
    throw "uv was installed, but its executable could not be located. Restart PowerShell and run install.ps1 again."
}

& $UvCommand.Source tool install --force --no-cache --reinstall-package ltex --from $Root --with watchdog ltex
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $UvCommand.Source tool update-shell
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not update the user PATH automatically."
}
Write-Host "ltex installed and its user tool directory was added to PATH."
Write-Host "Open a new PowerShell window, then run: ltex --help"
Write-Host "Tool directory:"
& $UvCommand.Source tool dir --bin

if ([Environment]::UserInteractive -and $Host.Name -notlike "*ServerRemoteHost*") {
    $ToolBin = (& $UvCommand.Source tool dir --bin).Trim()
    $LtexBin = Join-Path $ToolBin "ltex.exe"
    if (!(Test-Path $LtexBin)) { $LtexBin = Join-Path $ToolBin "ltex" }
    $CurrentEditor = (& $LtexBin config editor 2>$null).Trim()
    $CurrentViewer = (& $LtexBin config viewer 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($CurrentEditor)) {
        $EditorDefault = if (Get-Command code -ErrorAction SilentlyContinue) { "code" } else { "notepad.exe" }
    } else { $EditorDefault = $CurrentEditor }
    if ([string]::IsNullOrWhiteSpace($CurrentViewer)) { $ViewerDefault = "explorer.exe" } else { $ViewerDefault = $CurrentViewer }

    $EditorChoice = Read-Host "Choose the default editor command [$EditorDefault]"
    if ([string]::IsNullOrWhiteSpace($EditorChoice)) { $EditorChoice = $EditorDefault }
    $ViewerChoice = Read-Host "Choose the default PDF viewer command [$ViewerDefault]"
    if ([string]::IsNullOrWhiteSpace($ViewerChoice)) { $ViewerChoice = $ViewerDefault }
    & $LtexBin config editor $EditorChoice
    & $LtexBin config viewer $ViewerChoice
    Write-Host "Saved editor and viewer defaults."
} else {
    Write-Host "Non-interactive install: editor/viewer selection skipped."
    Write-Host "Set them later with: ltex config editor COMMAND and ltex config viewer COMMAND"
}

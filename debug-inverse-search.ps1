param(
    [string]$File,
    [string]$Line,
    [string]$Column
)

$ErrorActionPreference = "Continue"
$Ltex = Join-Path $env:USERPROFILE ".local\bin\ltex.exe"

Write-Host "ltex inverse-search debug wrapper"
Write-Host "file:   [$File]"
Write-Host "line:   [$Line]"
Write-Host "column: [$Column]"
Write-Host "ltex:   [$Ltex]"
Write-Host ""

if (Test-Path -LiteralPath $Ltex) {
    & $Ltex --debug inverse-search $File $Line $Column
} else {
    Write-Host "ltex executable not found: $Ltex"
}

Write-Host ""
Read-Host "Press Enter to close"

<#
.SYNOPSIS
    Creates one folder per line of a text file (e.g. one per document number).

.EXAMPLE
    .\create-folders.ps1
    .\create-folders.ps1 -InputFile .\dat.txt -DataDir .\data
    .\create-folders.ps1 -TemplateDir .\data\7750646441   # also copy template files into each new folder
#>
param(
    [string]$InputFile = (Join-Path $PSScriptRoot 'dat.txt'),
    [string]$DataDir = (Join-Path $PSScriptRoot 'data'),
    [string]$TemplateDir
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $InputFile -PathType Leaf)) {
    throw "Input file not found: $InputFile"
}
if ($TemplateDir -and -not (Test-Path $TemplateDir -PathType Container)) {
    throw "Template folder not found: $TemplateDir"
}

$created = 0
$skipped = 0

foreach ($line in Get-Content -LiteralPath $InputFile) {
    $name = $line.Trim()
    if (-not $name) { continue }

    if ($name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
        Write-Warning "Skipping invalid folder name: '$name'"
        $skipped++
        continue
    }

    $folder = Join-Path $DataDir $name
    if (Test-Path -LiteralPath $folder) {
        Write-Host "Exists:  $folder"
        $skipped++
        continue
    }

    New-Item -ItemType Directory -Path $folder | Out-Null
    if ($TemplateDir) {
        Copy-Item -Path (Join-Path $TemplateDir '*') -Destination $folder -Recurse
    }
    Write-Host "Created: $folder"
    $created++
}

Write-Host "Done. Created $created folder(s), skipped $skipped."

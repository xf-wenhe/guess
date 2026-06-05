# Multi-platform release build script for Flutter Guess Game
# Builds available platforms and uploads to GitHub Release
#
# Usage:
#   .\scripts\release_build.ps1              # Create new Release
#   .\scripts\release_build.ps1 -Supplement  # Upload to existing Release

param(
    [switch]$Supplement
)

$ErrorActionPreference = "Stop"

# Project root
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $PROJECT_ROOT

# Parse version from pubspec.yaml
function Get-Version {
    $versionLine = Select-String -Path "pubspec.yaml" -Pattern "^version:" | Select-Object -First 1
    $version = ($versionLine.Line -replace "version:\s*", "" -split "\+")[0]
    return $version
}

$VERSION = Get-Version
if ([string]::IsNullOrEmpty($VERSION)) {
    Write-Host "Error: Could not parse version from pubspec.yaml" -ForegroundColor Red
    exit 1
}

Write-Host "========================================" -ForegroundColor Blue
Write-Host "  Flutter Guess Game Release Builder  " -ForegroundColor Blue
Write-Host "========================================" -ForegroundColor Blue
Write-Host "Version: $VERSION" -ForegroundColor Green
Write-Host "Project: $PROJECT_ROOT" -ForegroundColor Green
Write-Host "Current Platform: windows" -ForegroundColor Green
if ($Supplement) {
    Write-Host "Mode: Supplement (upload to existing Release)" -ForegroundColor Yellow
}
Write-Host ""

# Track built files
$BUILD_FILES = @()
$BUILD_NOTES = @()

# Check dependencies
function Check-Dependencies {
    Write-Host "[1/5] Checking dependencies..." -ForegroundColor Yellow

    # Check Flutter
    if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
        Write-Host "Error: Flutter not found. Please install Flutter SDK." -ForegroundColor Red
        exit 1
    }

    # Check gh CLI
    $ghPath = "C:\Program Files\GitHub CLI\gh.exe"
    if (-not (Test-Path $ghPath)) {
        if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
            Write-Host "Error: GitHub CLI (gh) not found. Please install from: https://cli.github.com/" -ForegroundColor Red
            exit 1
        }
        $script:GH_CMD = "gh"
    } else {
        $script:GH_CMD = $ghPath
    }

    # Check gh auth status
    $authStatus = & $script:GH_CMD auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Not logged into GitHub. Run: gh auth login" -ForegroundColor Red
        exit 1
    }

    Write-Host "All dependencies available" -ForegroundColor Green
}

# Run quality checks
function Run-Checks {
    Write-Host "[2/5] Running quality checks..." -ForegroundColor Yellow

    Write-Host "  Running flutter analyze..."
    $analyzeResult = flutter analyze 2>&1
    if ($analyzeResult -match "error .*") {
        Write-Host $analyzeResult
        Write-Host "Error: flutter analyze found errors" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Analyze passed"

    Write-Host "  Running flutter test..."
    if ($env:SKIP_TESTS -eq "1") {
        Write-Host "  Skipping tests (SKIP_TESTS=1)"
    } else {
        flutter test
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: flutter test failed" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "Quality checks passed" -ForegroundColor Green
}

# Build Android (requires Java)
function Build-Android {
    Write-Host "  Building Android APK..." -ForegroundColor Yellow

    # Check Java
    if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
        Write-Host "  [SKIP] Android: Java not found." -ForegroundColor Yellow
        $script:BUILD_NOTES += "Android: skipped (Java not installed)"
        return $false
    }

    flutter build apk --release
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] Android build failed" -ForegroundColor Red
        return $false
    }

    $outputFile = "$PROJECT_ROOT\build\app\outputs\flutter-apk\app-release.apk"
    $releaseFile = "$PROJECT_ROOT\release\guess-$VERSION-android.apk"

    New-Item -ItemType Directory -Force -Path "$PROJECT_ROOT\release" | Out-Null
    Copy-Item $outputFile $releaseFile

    Write-Host "  [OK] Android: $releaseFile" -ForegroundColor Green
    $script:BUILD_FILES += $releaseFile
    return $true
}

# Build Windows
function Build-Windows {
    Write-Host "  Building Windows..." -ForegroundColor Yellow

    flutter build windows --release
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] Windows build failed" -ForegroundColor Red
        return $false
    }

    $outputDir = "$PROJECT_ROOT\build\windows\x64\runner\Release"
    $releaseFile = "$PROJECT_ROOT\release\guess-$VERSION-windows.zip"

    New-Item -ItemType Directory -Force -Path "$PROJECT_ROOT\release" | Out-Null

    # Create zip using PowerShell's Compress-Archive
    if (Test-Path $releaseFile) {
        Remove-Item $releaseFile -Force
    }
    Compress-Archive -Path "$outputDir\*" -DestinationPath $releaseFile

    Write-Host "  [OK] Windows: $releaseFile" -ForegroundColor Green
    $script:BUILD_FILES += $releaseFile
    return $true
}

# Build all available platforms
function Build-All {
    Write-Host "[3/5] Building platforms..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path "$PROJECT_ROOT\release" | Out-Null

    Build-Android | Out-Null
    Build-Windows | Out-Null

    if ($BUILD_FILES.Count -eq 0) {
        Write-Host "Error: No platforms were successfully built" -ForegroundColor Red
        exit 1
    }

    Write-Host "Platforms built" -ForegroundColor Green
}

# Create GitHub release
function Create-Release {
    Write-Host "[4/5] Creating GitHub release..." -ForegroundColor Yellow

    $tag = "v$VERSION"
    $title = "v$VERSION"

    # Check if tag already exists
    $tagExists = git tag -l $tag
    if ($tagExists) {
        if ($Supplement) {
            Write-Host "  Tag $tag exists, will upload supplemental files" -ForegroundColor Yellow
        } else {
            Write-Host "Error: Tag $tag already exists. Please update version in pubspec.yaml." -ForegroundColor Red
            Write-Host "Tip: Use -Supplement to add files to existing release" -ForegroundColor Yellow
            exit 1
        }
    } else {
        if ($Supplement) {
            Write-Host "Error: Tag $tag does not exist. Cannot supplement non-existent release." -ForegroundColor Red
            Write-Host "Tip: Run without -Supplement to create a new release" -ForegroundColor Yellow
            exit 1
        }
    }

    if ($Supplement) {
        # Supplement mode: upload files to existing Release
        Write-Host "  Uploading supplemental files to existing release..."
        foreach ($file in $BUILD_FILES) {
            $filename = Split-Path -Leaf $file

            # Check if file already exists in release
            $existingAssets = & $script:GH_CMD release view $tag --json assets --jq ".assets[].name" 2>$null
            if ($existingAssets -contains $filename) {
                Write-Host "  [SKIP] $filename already exists in release" -ForegroundColor Yellow
            } else {
                Write-Host "  Uploading $filename..."
                & $script:GH_CMD release upload $tag $file
                Write-Host "  [OK] Uploaded: $filename" -ForegroundColor Green
            }
        }
        Write-Host "Supplemental files uploaded" -ForegroundColor Green
    } else {
        # Normal mode: create new Release
        $platformTable = ""
        $systemRequirements = ""

        foreach ($file in $BUILD_FILES) {
            if ($file -match "android") {
                $platformTable += "| Android | ``guess-$VERSION-android.apk`` | Direct install |`n"
                $systemRequirements += "- **Android**: Android 5.0 (API 21) or higher`n"
            }
            if ($file -match "windows") {
                $platformTable += "| Windows | ``guess-$VERSION-windows.zip`` | Extract and run guess.exe |`n"
                $systemRequirements += "- **Windows**: Windows 10 or higher`n"
            }
            if ($file -match "macos") {
                $platformTable += "| macOS | ``guess-$VERSION-macos.zip`` | Extract and open guess.app |`n"
                $systemRequirements += "- **macOS**: macOS 10.14 or higher`n"
            }
        }

        $notes = @"
## Guess Game v$VERSION

### Downloads

| Platform | File | Instructions |
|------|------|------|
$platformTable
### System Requirements

$systemRequirements
### Notes

- macOS may require allowing the app in System Preferences > Security & Privacy
- The game requires the embedding server to be running for semantic scoring
"@

        # Create release with retry logic
        $maxRetries = 3
        $retryCount = 0
        $success = $false

        while ($retryCount -lt $maxRetries) {
            Write-Host "  Attempt $($retryCount + 1)/$maxRetries..."

            $fileArgs = $BUILD_FILES -join " "
            $result = & $script:GH_CMD release create $tag --title $title --notes $notes $BUILD_FILES 2>&1

            if ($LASTEXITCODE -eq 0) {
                $success = $true
                break
            }

            $retryCount++
            if ($retryCount -lt $maxRetries) {
                Write-Host "  Release creation failed, retrying in 5 seconds..." -ForegroundColor Yellow
                Start-Sleep -Seconds 5
            }
        }

        if (-not $success) {
            Write-Host "Error: Failed to create release after $maxRetries attempts" -ForegroundColor Red
            Write-Host "Tip: You can manually create the release with:" -ForegroundColor Yellow
            Write-Host "  gh release create $tag --title `"$title`""
            exit 1
        }

        Write-Host "Release created: $tag" -ForegroundColor Green
    }
}

# Cleanup
function Cleanup {
    Write-Host "[5/5] Cleaning up..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$PROJECT_ROOT\release" -ErrorAction SilentlyContinue
    Write-Host "Cleanup complete" -ForegroundColor Green
}

# Main execution
function Main {
    Check-Dependencies

    if ($Supplement) {
        Write-Host "[2/5] Skipping quality checks (supplement mode)" -ForegroundColor Yellow
    } else {
        Run-Checks
    }

    Build-All
    Create-Release
    Cleanup

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    if ($Supplement) {
        Write-Host "  Supplemental files uploaded!          " -ForegroundColor Green
    } else {
        Write-Host "  Release v$VERSION published!        " -ForegroundColor Green
    }
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "View at: https://github.com/xf-wenhe/guess/releases/tag/v$VERSION"
}

Main

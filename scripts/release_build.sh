#!/bin/bash
# Multi-platform release build script for Flutter Guess Game
# Builds available platforms and uploads to GitHub Release

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root (script location)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Detect current platform
CURRENT_OS=$(uname -s)
case "$CURRENT_OS" in
    Darwin)  CURRENT_PLATFORM="macos" ;;
    Linux)   CURRENT_PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*) CURRENT_PLATFORM="windows" ;;
    *)       CURRENT_PLATFORM="unknown" ;;
esac

# Parse version from pubspec.yaml
parse_version() {
    local version_line=$(grep '^version:' pubspec.yaml | head -1)
    local version=$(echo "$version_line" | sed 's/version: //' | cut -d'+' -f1)
    echo "$version"
}

VERSION=$(parse_version)
if [ -z "$VERSION" ]; then
    echo -e "${RED}Error: Could not parse version from pubspec.yaml${NC}"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Flutter Guess Game Release Builder  ${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Version: ${VERSION}${NC}"
echo -e "${GREEN}Project: ${PROJECT_ROOT}${NC}"
echo -e "${GREEN}Current Platform: ${CURRENT_PLATFORM}${NC}"
echo ""

# Track built files
BUILD_FILES=""
BUILD_NOTES=""

# Check dependencies
check_dependencies() {
    echo -e "${YELLOW}[1/5] Checking dependencies...${NC}"

    # Check Flutter
    if ! command -v flutter &> /dev/null; then
        echo -e "${RED}Error: Flutter not found. Please install Flutter SDK.${NC}"
        exit 1
    fi

    # Check gh CLI
    if ! command -v gh &> /dev/null; then
        echo -e "${RED}Error: GitHub CLI (gh) not found. Please install: brew install gh${NC}"
        exit 1
    fi

    # Check gh auth status
    if ! gh auth status &> /dev/null; then
        echo -e "${RED}Error: Not logged into GitHub. Run: gh auth login${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ All dependencies available${NC}"
}

# Run quality checks
run_checks() {
    echo -e "${YELLOW}[2/5] Running quality checks...${NC}"

    echo "  Running flutter analyze..."
    if flutter analyze 2>&1 | grep -q "error •"; then
        flutter analyze
        echo -e "${RED}Error: flutter analyze found errors${NC}"
        exit 1
    fi
    echo "  Analyze passed"

    echo "  Running flutter test..."
    if [ "${SKIP_TESTS:-0}" = "1" ]; then
        echo "  Skipping tests (SKIP_TESTS=1)"
    else
        if ! flutter test; then
            echo -e "${RED}Error: flutter test failed${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}✓ Quality checks passed${NC}"
}

# Build Android (requires Java)
build_android() {
    echo -e "${YELLOW}  Building Android APK...${NC}"

    # Check Java
    if ! java -version &> /dev/null; then
        echo -e "${RED}  ✗ Android: Java not found. Install with: brew install openjdk@17${NC}"
        BUILD_NOTES="${BUILD_NOTES}\n- Android: 未构建（需要安装 Java）"
        return 1
    fi

    flutter build apk --release

    local output_file="$PROJECT_ROOT/build/app/outputs/flutter-apk/app-release.apk"
    local release_file="$PROJECT_ROOT/release/guess-${VERSION}-android.apk"

    mkdir -p "$PROJECT_ROOT/release"
    cp "$output_file" "$release_file"
    echo -e "${GREEN}  ✓ Android: ${release_file}${NC}"
    BUILD_FILES="${BUILD_FILES} ${release_file}"
    return 0
}

# Build Windows (only on Windows)
build_windows() {
    echo -e "${YELLOW}  Building Windows...${NC}"

    if [ "$CURRENT_PLATFORM" != "windows" ]; then
        echo -e "${YELLOW}  ⊘ Windows: 只能在 Windows 主机上构建${NC}"
        BUILD_NOTES="${BUILD_NOTES}\n- Windows: 未构建（需要在 Windows 上执行）"
        return 1
    fi

    flutter build windows --release

    local output_dir="$PROJECT_ROOT/build/windows/x64/runner/Release"
    local release_file="$PROJECT_ROOT/release/guess-${VERSION}-windows.zip"

    mkdir -p "$PROJECT_ROOT/release"
    cd "$output_dir"
    zip -r "$release_file" .
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}  ✓ Windows: ${release_file}${NC}"
    BUILD_FILES="${BUILD_FILES} ${release_file}"
    return 0
}

# Build macOS (only on macOS)
build_macos() {
    echo -e "${YELLOW}  Building macOS...${NC}"

    if [ "$CURRENT_PLATFORM" != "macos" ]; then
        echo -e "${YELLOW}  ⊘ macOS: 只能在 macOS 主机上构建${NC}"
        BUILD_NOTES="${BUILD_NOTES}\n- macOS: 未构建（需要在 macOS 上执行）"
        return 1
    fi

    flutter build macos --release

    local output_dir="$PROJECT_ROOT/build/macos/Build/Products/Release/guess.app"
    local release_file="$PROJECT_ROOT/release/guess-${VERSION}-macos.zip"

    mkdir -p "$PROJECT_ROOT/release"
    cd "$(dirname "$output_dir")"
    zip -r "$release_file" guess.app
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}  ✓ macOS: ${release_file}${NC}"
    BUILD_FILES="${BUILD_FILES} ${release_file}"
    return 0
}

# Build all available platforms
build_all() {
    echo -e "${YELLOW}[3/5] Building platforms...${NC}"
    mkdir -p "$PROJECT_ROOT/release"

    build_android || true
    build_windows || true
    build_macos || true

    if [ -z "$BUILD_FILES" ]; then
        echo -e "${RED}Error: No platforms were successfully built${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Platforms built${NC}"
}

# Create GitHub release
create_release() {
    echo -e "${YELLOW}[4/5] Creating GitHub release...${NC}"

    local tag="v${VERSION}"
    local title="v${VERSION}"

    # Check if tag already exists
    if git tag -l | grep -q "^${tag}$"; then
        echo -e "${RED}Error: Tag ${tag} already exists. Please update version in pubspec.yaml.${NC}"
        exit 1
    fi

    # Build release notes
    local notes="## 词语猜谜 v${VERSION}

### 下载说明

本次发布包含以下平台：${BUILD_NOTES}

| 平台 | 文件 | 说明 |
|------|------|------|
| Android | \`guess-${VERSION}-android.apk\` | 直接安装 |
| Windows | \`guess-${VERSION}-windows.zip\` | 解压后运行 guess.exe |
| macOS | \`guess-${VERSION}-macos.zip\` | 解压后打开 guess.app |

### 系统要求

- **Android**: Android 5.0 (API 21) 或更高
- **Windows**: Windows 10 或更高
- **macOS**: macOS 10.14 或更高

### 注意事项

- macOS 首次运行可能需要在「系统偏好设置 → 安全性与隐私」中允许运行
- 游戏需要运行 embedding server 才能正常游玩"

    # Create release with files
    gh release create "$tag" \
        --title "$title" \
        --notes "$notes" \
        $BUILD_FILES

    echo -e "${GREEN}✓ Release created: ${tag}${NC}"
}

# Cleanup
cleanup() {
    echo -e "${YELLOW}[5/5] Cleaning up...${NC}"
    rm -rf "$PROJECT_ROOT/release"
    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

# Main execution
main() {
    check_dependencies
    run_checks
    build_all
    create_release
    cleanup

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Release v${VERSION} published!        ${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "View at: https://github.com/xf-wenhe/guess/releases/tag/v${VERSION}"
}

main "$@"
#!/bin/bash

# Complete Xcode Clean Script
# This removes all build artifacts and caches to force a fresh build

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deep Clean Xcode Build${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Find DerivedData location
DERIVED_DATA=$(xcodebuild -showBuildSettings 2>/dev/null | grep -m 1 "BUILD_DIR" | sed 's/[ ]*BUILD_DIR = //' | sed 's/\/Build\/Products//')

if [ -z "$DERIVED_DATA" ]; then
    # Fallback to default location
    DERIVED_DATA="$HOME/Library/Developer/Xcode/DerivedData"
fi

echo -e "${YELLOW}1. Cleaning build folder...${NC}"
cd BroadcastApp
xcodebuild clean -project BroadcastApp.xcodeproj -scheme BroadcastApp 2>/dev/null || true
echo -e "${GREEN}✓ Build folder cleaned${NC}"

echo ""
echo -e "${YELLOW}2. Removing DerivedData...${NC}"
if [ -d "$DERIVED_DATA" ]; then
    # Find and remove only this project's DerivedData
    find "$DERIVED_DATA" -name "BroadcastApp-*" -type d -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✓ DerivedData removed${NC}"
else
    echo -e "${YELLOW}  DerivedData not found (OK)${NC}"
fi

echo ""
echo -e "${YELLOW}3. Removing module cache...${NC}"
rm -rf ~/Library/Developer/Xcode/DerivedData/ModuleCache.noindex 2>/dev/null || true
echo -e "${GREEN}✓ Module cache cleared${NC}"

echo ""
echo -e "${YELLOW}4. Cleaning build products...${NC}"
rm -rf build/ 2>/dev/null || true
rm -rf .build/ 2>/dev/null || true
find . -name "*.xcworkspace" -prune -o -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
echo -e "${GREEN}✓ Build products removed${NC}"

echo ""
echo -e "${YELLOW}5. Clearing Xcode caches...${NC}"
rm -rf ~/Library/Caches/com.apple.dt.Xcode 2>/dev/null || true
echo -e "${GREEN}✓ Xcode caches cleared${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Clean complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Delete the app from your device (long press → Delete)"
echo -e "2. In Xcode: Product → Clean Build Folder (Cmd+Shift+K)"
echo -e "3. Quit and restart Xcode"
echo -e "4. Build and run: Product → Run (Cmd+R)"
echo ""

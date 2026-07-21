#!/bin/bash
CURRENT_DATE=$(date +'%Y-%m-%d %H:%M:%S')
LOG_FILE="$HOME/.gemini/config/backup.log"

echo "=== Auto Backup Started at $CURRENT_DATE ===" >> "$LOG_FILE"

# --- 1. Antigravity Config Backup ---
CONFIG_DIR="$HOME/.gemini/config"
if [ -d "$CONFIG_DIR" ]; then
    cd "$CONFIG_DIR" || exit
    git add .
    if [ -n "$(git status --porcelain)" ]; then
        git commit -m "Auto backup config: $CURRENT_DATE" >> "$LOG_FILE" 2>&1
        git push origin main >> "$LOG_FILE" 2>&1
        echo "Config backed up successfully." >> "$LOG_FILE"
    fi
fi

# --- 2. Second Brain Backup ---
SB_DIR="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/2nd-Brain-i"
if [ -d "$SB_DIR" ]; then
    cd "$SB_DIR" || exit
    git add .
    if [ -n "$(git status --porcelain)" ]; then
        git commit -m "Auto backup Second Brain: $CURRENT_DATE" >> "$LOG_FILE" 2>&1
        git push origin main >> "$LOG_FILE" 2>&1
        echo "Second Brain backed up successfully." >> "$LOG_FILE"
    fi
fi

echo "=== Auto Backup Completed ===" >> "$LOG_FILE"

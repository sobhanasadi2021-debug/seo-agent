#!/usr/bin/env bash
cd "$(dirname "$0")"
( start "" "http://127.0.0.1:8791" 2>/dev/null || xdg-open "http://127.0.0.1:8791" 2>/dev/null || open "http://127.0.0.1:8791" 2>/dev/null ) || true
python3 app.py

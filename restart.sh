#!/bin/bash
# Restart Tuple UI

echo "Stopping Tuple UI..."
pkill -f "python.*tuple_ui.py"

echo "Waiting..."
sleep 2

echo "Starting Tuple UI..."
nohup python3 tuple_ui.py > /dev/null 2>&1 &

echo "Tuple UI restarted!"

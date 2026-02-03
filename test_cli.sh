#!/bin/bash
# Test script for pihole-toolkit
# Run this once sessions have cleared

set -e
cd "$(dirname "$0")"

echo "=== Testing Pi-hole CLI ==="
echo ""

echo "1. Testing config show..."
python3 pihole_cli.py config
echo ""

echo "2. Testing stats..."
python3 pihole_cli.py stats
echo ""

echo "3. Testing status..."
python3 pihole_cli.py status
echo ""

echo "4. Testing top domains (5)..."
python3 pihole_cli.py top -n 5
echo ""

echo "5. Testing top clients (5)..."
python3 pihole_cli.py clients -n 5
echo ""

echo "6. Testing JSON output..."
python3 pihole_cli.py json | head -20
echo "..."
echo ""

echo "=== All tests passed! ==="

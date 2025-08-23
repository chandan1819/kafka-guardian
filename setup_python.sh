#!/bin/bash

# Simple Python setup for Kafka Self-Healing testing

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🐍 Python Setup for Kafka Self-Healing${NC}"
echo "======================================="

# Check Python version
echo -e "${YELLOW}Checking Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✅ Found: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}❌ Python 3 not found${NC}"
    exit 1
fi

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip3 install -r requirements.txt

echo -e "${GREEN}✅ Python setup complete!${NC}"
echo ""
echo "You can now run the Kafka Self-Healing application:"
echo "python3 -m src.kafka_self_healing.main --config examples/config_testing.yaml"
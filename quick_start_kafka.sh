#!/bin/bash

# Quick Kafka Cluster Setup for Testing
# Simple script to get Kafka running locally for testing the self-healing app

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Quick Kafka Cluster Setup${NC}"
echo "=================================="

# Check if Docker is running
echo -e "${YELLOW}Checking Docker...${NC}"
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker is not running${NC}"
    echo "Please start Docker Desktop and try again"
    echo ""
    echo "On macOS:"
    echo "1. Open Docker Desktop application"
    echo "2. Wait for it to start (Docker icon in menu bar)"
    echo "3. Run this script again"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"

# Start the Kafka cluster
echo -e "${YELLOW}Starting Kafka cluster...${NC}"
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Check if services are running
echo -e "${YELLOW}Checking service status...${NC}"

# Check Zookeeper
if docker exec test-zookeeper bash -c "echo 'ruok' | nc localhost 2181" | grep -q "imok" 2>/dev/null; then
    echo -e "${GREEN}✅ Zookeeper is ready${NC}"
else
    echo -e "${RED}❌ Zookeeper is not ready${NC}"
fi

# Check Kafka brokers
if docker exec test-kafka1 kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; then
    echo -e "${GREEN}✅ Kafka Broker 1 is ready (port 9092)${NC}"
else
    echo -e "${RED}❌ Kafka Broker 1 is not ready${NC}"
fi

if docker exec test-kafka2 kafka-broker-api-versions --bootstrap-server localhost:9093 &>/dev/null; then
    echo -e "${GREEN}✅ Kafka Broker 2 is ready (port 9093)${NC}"
else
    echo -e "${RED}❌ Kafka Broker 2 is not ready${NC}"
fi

# Check MailHog (for testing notifications)
if curl -s http://localhost:8025 &>/dev/null; then
    echo -e "${GREEN}✅ MailHog is ready (http://localhost:8025)${NC}"
else
    echo -e "${YELLOW}⚠️  MailHog might not be ready yet${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Kafka cluster is running!${NC}"
echo ""
echo "Services available:"
echo "• Kafka Broker 1: localhost:9092"
echo "• Kafka Broker 2: localhost:9093" 
echo "• Zookeeper: localhost:2181"
echo "• MailHog UI: http://localhost:8025"
echo ""
echo "Next steps:"
echo "1. Install Python dependencies: pip3 install -r requirements.txt"
echo "2. Test the self-healing app: python3 -m src.kafka_self_healing.main --config examples/config_testing.yaml"
echo "3. Stop cluster when done: docker-compose -f docker-compose.test.yml down"
echo ""
echo "To view logs: docker-compose -f docker-compose.test.yml logs -f"
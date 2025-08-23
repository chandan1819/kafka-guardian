# 🎯 Demo Commands Reference

## Quick Command Reference for Live Demo

### Terminal 1: Main Demo Terminal
```bash
# 1. Start the complete system
./run_kafka_test.sh start

# 2. If you need to restart just the cluster
./run_kafka_test.sh setup

# 3. Stop everything
./run_kafka_test.sh stop
```

### Terminal 2: Status and Testing
```bash
# Check service status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test connectivity
nc -zv localhost 9092  # Kafka Broker 1
nc -zv localhost 9093  # Kafka Broker 2
nc -zv localhost 2181  # Zookeeper

# Simulate failure
docker stop test-kafka1

# Check status after failure
docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"

# Restart failed service
docker start test-kafka1

# Verify recovery
docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
```

### Terminal 3: Log Monitoring
```bash
# Watch real-time application logs
tail -f logs/application.log

# Watch audit logs
tail -f logs/audit.log

# Check recent logs
tail -20 logs/application.log
```

### Terminal 4: Email Notifications
```bash
# Open MailHog UI in browser
open http://localhost:8025

# Check emails via API
curl -s http://localhost:8025/api/v1/messages | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'📧 Total email alerts: {len(data)}')
for email in data:
    print(f'Subject: {email.get(\"Subject\", \"No Subject\")}')
"

# Clear all emails (for clean demo)
curl -X DELETE http://localhost:8025/api/v1/messages
```

## Advanced Demo Commands

### Multiple Failure Scenarios
```bash
# Stop Zookeeper (critical failure)
docker stop test-zookeeper

# Stop both Kafka brokers
docker stop test-kafka1 test-kafka2

# Stop all services
docker stop test-kafka1 test-kafka2 test-zookeeper test-mailhog

# Restart all services
docker start test-zookeeper test-kafka1 test-kafka2 test-mailhog
```

### Configuration Demo
```bash
# Show configuration
cat config_local_test.yaml

# Show monitoring settings
grep -A 10 "monitoring:" config_local_test.yaml

# Show recovery settings
grep -A 10 "recovery:" config_local_test.yaml

# Show notification settings
grep -A 10 "notification:" config_local_test.yaml
```

### System Information
```bash
# Show system status
./run_kafka_test.sh status

# Show Docker logs
docker logs test-kafka1
docker logs test-kafka2
docker logs test-zookeeper

# Show system resources
docker stats --no-stream
```

## Demo Flow Commands

### Phase 1: Setup (Copy-paste ready)
```bash
# Verify prerequisites
docker info && echo "✅ Docker OK"
python3 -c "import yaml, psutil; print('✅ Python deps OK')"
chmod +x run_kafka_test.sh && echo "✅ Script ready"
```

### Phase 2: Start System (Copy-paste ready)
```bash
# Start complete system
./run_kafka_test.sh start
```

### Phase 3: Verify Status (Copy-paste ready)
```bash
# Check all services
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test connectivity
echo "Testing Kafka connectivity..."
nc -zv localhost 9092 && echo "✅ Kafka Broker 1 OK"
nc -zv localhost 9093 && echo "✅ Kafka Broker 2 OK"
nc -zv localhost 2181 && echo "✅ Zookeeper OK"
```

### Phase 4: Monitor Logs (Copy-paste ready)
```bash
# Start log monitoring (run in separate terminal)
tail -f logs/application.log
```

### Phase 5: Simulate Failure (Copy-paste ready)
```bash
echo "=== SIMULATING PRODUCTION FAILURE ==="
echo "Current status:"
docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"

echo "Stopping Kafka Broker 1..."
docker stop test-kafka1

echo "Status after failure:"
docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
```

### Phase 6: Check Notifications (Copy-paste ready)
```bash
# Check email notifications
curl -s http://localhost:8025/api/v1/messages | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(f'📧 Total email alerts: {len(data)}')
    for i, email in enumerate(data, 1):
        print(f'{i}. Subject: {email.get(\"Subject\", \"No Subject\")}')
        print(f'   From: {email.get(\"From\", {}).get(\"Mailbox\", \"\")}')
except:
    print('No emails yet or MailHog not accessible')
"
```

### Phase 7: Demonstrate Recovery (Copy-paste ready)
```bash
echo "=== DEMONSTRATING RECOVERY ==="
echo "Restarting failed broker..."
docker start test-kafka1

echo "Waiting for service to be healthy..."
sleep 10

echo "Recovery complete:"
docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
```

### Phase 8: Cleanup (Copy-paste ready)
```bash
# Stop all services
./run_kafka_test.sh stop

# Verify cleanup
docker ps | grep test- || echo "✅ All test containers stopped"
```

## Troubleshooting Commands

### If Demo Fails
```bash
# Check Docker status
docker info

# Check port conflicts
lsof -i :9092 :9093 :2181 :8025

# Restart Docker Desktop
osascript -e 'quit app "Docker"' && sleep 5 && open -a Docker

# Force cleanup
docker-compose -f docker-compose.test.yml down -v
docker system prune -f

# Check Python environment
python3 -c "import sys; print(sys.path)"
pip list | grep -E "(yaml|psutil|pytest)"
```

### Reset Demo Environment
```bash
# Complete reset
./run_kafka_test.sh stop
rm -rf logs/*
docker system prune -f
./run_kafka_test.sh start
```

## One-Liner Demo Commands

```bash
# Complete demo in one terminal
./run_kafka_test.sh start && sleep 30 && docker stop test-kafka1 && sleep 10 && docker start test-kafka1

# Quick status check
docker ps --format "table {{.Names}}\t{{.Status}}" | grep test-

# Quick connectivity test
for port in 9092 9093 2181; do nc -zv localhost $port && echo "✅ Port $port OK" || echo "❌ Port $port FAIL"; done

# Quick log check
tail -5 logs/application.log | grep -E "(ERROR|WARN|INFO)"
```

## Demo Timing

- **Setup**: 2-3 minutes
- **Status Check**: 1 minute  
- **Failure Simulation**: 2 minutes
- **Recovery Demo**: 2 minutes
- **Q&A**: 5-10 minutes
- **Cleanup**: 1 minute

**Total Demo Time**: 15-20 minutes
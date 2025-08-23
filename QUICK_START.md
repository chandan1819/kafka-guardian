# 🚀 Quick Start - Kafka Self-Healing System Testing

## Prerequisites
- **Docker Desktop** must be installed and running
- **Python 3.8+** (you have Python 3.9.6 ✅)
- **Dependencies** already installed ✅

## 🎯 One-Command Setup and Run

```bash
./run_kafka_test.sh start
```

This single command will:
1. ✅ Check Docker is running
2. 🚀 Start Kafka cluster (2 brokers + Zookeeper + MailHog)
3. 🧪 Test connectivity and configuration
4. 🔄 Run the Kafka Self-Healing System

## 📋 Available Commands

```bash
# Complete setup and run
./run_kafka_test.sh start

# Just setup Kafka cluster (don't run the app)
./run_kafka_test.sh setup

# Test application without starting cluster
./run_kafka_test.sh test

# Check system status
./run_kafka_test.sh status

# Stop and cleanup everything
./run_kafka_test.sh stop

# Show help
./run_kafka_test.sh help
```

## 🔧 What You Get

### Services Running:
- **Kafka Broker 1**: `localhost:9092`
- **Kafka Broker 2**: `localhost:9093`
- **Zookeeper**: `localhost:2181`
- **MailHog** (Email testing): `http://localhost:8025`

### Configuration:
- **Config file**: `config_local_test.yaml`
- **Log directory**: `logs/`
- **Monitoring interval**: 30 seconds
- **Recovery attempts**: 3 with exponential backoff

## 🚨 If Docker Isn't Running

1. **Start Docker Desktop**:
   ```bash
   open -a Docker
   ```

2. **Wait for Docker to start** (whale icon in menu bar)

3. **Run the setup again**:
   ```bash
   ./run_kafka_test.sh start
   ```

## 🧪 Testing the Self-Healing

Once running, you can test the self-healing by:

1. **Stopping a Kafka broker**:
   ```bash
   docker stop test-kafka1
   ```

2. **Watch the logs** - the system should detect the failure and attempt recovery

3. **Check MailHog** at `http://localhost:8025` for email notifications

4. **Restart the broker** to see recovery:
   ```bash
   docker start test-kafka1
   ```

## 📊 Monitoring

- **Application logs**: `logs/kafka_self_healing.log`
- **Docker logs**: `docker-compose -f docker-compose.test.yml logs -f`
- **Container status**: `docker-compose -f docker-compose.test.yml ps`

## 🛑 Stopping Everything

```bash
./run_kafka_test.sh stop
```

Or press `Ctrl+C` when the application is running.

## 🔍 Troubleshooting

### Docker Issues
```bash
# Check Docker status
docker info

# Restart Docker Desktop
# Close Docker Desktop and reopen it
```

### Port Conflicts
```bash
# Check what's using the ports
lsof -i :9092
lsof -i :9093
lsof -i :2181

# Stop conflicting services or change ports in docker-compose.test.yml
```

### Python Issues
```bash
# Test imports
python3 -c "import yaml, psutil, pytest; print('Dependencies OK')"

# Check Python path
python3 -c "import sys; print(sys.path)"
```

## 📝 Next Steps

1. **Run the system**: `./run_kafka_test.sh start`
2. **Monitor the logs** in `logs/kafka_self_healing.log`
3. **Test failure scenarios** by stopping/starting containers
4. **Check email notifications** at `http://localhost:8025`
5. **Modify configuration** in `config_local_test.yaml` as needed

---

**Ready to test? Just run:** `./run_kafka_test.sh start` 🚀
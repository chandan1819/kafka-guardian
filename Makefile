# Kafka Self-Healing System Makefile

.PHONY: help install test test-unit test-e2e test-performance test-all clean setup-dev lint format security-scan docker-up docker-down

# Default target
help:
	@echo "Kafka Self-Healing System - Available targets:"
	@echo ""
	@echo "  install          - Install dependencies"
	@echo "  setup-dev        - Set up development environment"
	@echo "  test             - Run all tests"
	@echo "  test-unit        - Run unit tests only"
	@echo "  test-e2e         - Run end-to-end tests only"
	@echo "  test-performance - Run performance benchmarks"
	@echo "  test-all         - Run comprehensive test suite"
	@echo "  lint             - Run code linting"
	@echo "  format           - Format code"
	@echo "  security-scan    - Run security scans"
	@echo "  docker-up        - Start test cluster"
	@echo "  docker-down      - Stop test cluster"
	@echo "  clean            - Clean up test artifacts"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt
	pip install pytest pytest-cov pytest-html pytest-xdist psutil requests
	pip install black flake8 bandit safety mypy

# Set up development environment
setup-dev: install
	mkdir -p test_logs test_reports
	chmod +x scripts/run_tests.sh
	chmod +x tests/failure_simulation.py
	@echo "Development environment set up successfully"

# Run all tests (unit + integration)
test:
	./scripts/run_tests.sh

# Run unit tests only
test-unit:
	pytest tests/ \
		--ignore=tests/test_e2e.py \
		--cov=src/kafka_self_healing \
		--cov-report=html:test_reports/coverage_html \
		--cov-report=xml:test_reports/coverage.xml \
		--cov-report=term-missing \
		--html=test_reports/unit_tests.html \
		--self-contained-html \
		--junitxml=test_reports/unit_tests.xml \
		-v

# Run end-to-end tests only
test-e2e: docker-up
	pytest tests/test_e2e.py \
		--html=test_reports/e2e_tests.html \
		--self-contained-html \
		--junitxml=test_reports/e2e_tests.xml \
		-v -s
	$(MAKE) docker-down

# Run performance benchmarks
test-performance: docker-up
	python tests/benchmark.py \
		--config tests/test_config_e2e.yaml \
		--output test_reports/benchmark_results.json \
		--report test_reports/benchmark_report.txt
	$(MAKE) docker-down

# Run comprehensive test suite
test-all:
	./scripts/run_tests.sh --with-benchmarks

# Start Docker test cluster
docker-up:
	docker-compose -f docker-compose.test.yml up -d
	@echo "Waiting for cluster to be ready..."
	@timeout=120; elapsed=0; \
	while [ $$elapsed -lt $$timeout ]; do \
		if docker exec test-zookeeper bash -c "echo 'ruok' | nc localhost 2181" | grep -q "imok" 2>/dev/null; then \
			if docker exec test-kafka1 kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; then \
				if docker exec test-kafka2 kafka-broker-api-versions --bootstrap-server localhost:9093 >/dev/null 2>&1; then \
					echo "Test cluster is ready"; \
					exit 0; \
				fi; \
			fi; \
		fi; \
		sleep 5; \
		elapsed=$$((elapsed + 5)); \
		echo -n "."; \
	done; \
	echo "Test cluster failed to start"; \
	exit 1

# Stop Docker test cluster
docker-down:
	docker-compose -f docker-compose.test.yml down -v

# Code linting
lint:
	flake8 src/ tests/ --max-line-length=100 --ignore=E203,W503
	mypy src/kafka_self_healing --ignore-missing-imports

# Code formatting
format:
	black src/ tests/ --line-length=100
	isort src/ tests/ --profile black

# Security scanning
security-scan:
	bandit -r src/ -f txt
	safety check

# Clean up test artifacts
clean:
	rm -rf test_reports/ test_logs/ .pytest_cache/ .coverage
	rm -rf src/kafka_self_healing.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true

# Failure simulation targets
simulate-kafka1-failure:
	python tests/failure_simulation.py --scenario kafka1_failure --duration 60

simulate-kafka2-failure:
	python tests/failure_simulation.py --scenario kafka2_failure --duration 60

simulate-zookeeper-failure:
	python tests/failure_simulation.py --scenario zookeeper_failure --duration 60

simulate-network-partition:
	python tests/failure_simulation.py --scenario network_partition --duration 90

simulate-cascading-failure:
	python tests/failure_simulation.py --scenario cascading_failure --duration 180

simulate-chaos-testing:
	python tests/failure_simulation.py --scenario chaos_testing --duration 300

# Development helpers
dev-setup: setup-dev
	@echo "Installing pre-commit hooks..."
	pip install pre-commit
	pre-commit install

run-local:
	python -m src.kafka_self_healing.main --config tests/test_config_e2e.yaml

# CI/CD helpers
ci-test: test-unit test-e2e

ci-full: test-all security-scan

# Documentation generation (if needed)
docs:
	@echo "Generating documentation..."
	mkdir -p docs/
	python -m pydoc -w src.kafka_self_healing
	mv *.html docs/ 2>/dev/null || true

# Package building
build:
	python setup.py sdist bdist_wheel

# Installation from source
install-dev:
	pip install -e .

# Quick health check
health-check:
	python -c "import src.kafka_self_healing; print('Package imports successfully')"
	python -c "from src.kafka_self_healing.main import SelfHealingSystem; print('Main module loads successfully')"

# Show test coverage
coverage-report:
	coverage report -m
	coverage html
	@echo "Coverage report generated in htmlcov/"

# Run specific test file
test-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make test-file FILE=tests/test_example.py"; \
	else \
		pytest $(FILE) -v; \
	fi

# Run tests with specific marker
test-marker:
	@if [ -z "$(MARKER)" ]; then \
		echo "Usage: make test-marker MARKER=slow"; \
	else \
		pytest -m $(MARKER) -v; \
	fi

# Performance profiling
profile:
	python -m cProfile -o profile_output.prof -m src.kafka_self_healing.main --config tests/test_config_e2e.yaml
	@echo "Profile saved to profile_output.prof"
	@echo "View with: python -m pstats profile_output.prof"
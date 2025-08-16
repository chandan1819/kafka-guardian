# Multi-stage Dockerfile for Kafka Guardian
FROM python:3.11-slim as builder

# Set build arguments
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r /tmp/requirements.txt

# Copy source code
COPY src/ /app/src/
COPY setup.py pyproject.toml README.md LICENSE /app/

# Install the application
WORKDIR /app
RUN pip install -e .

# Production stage
FROM python:3.11-slim as production

# Set labels for metadata
LABEL maintainer="Chandan Kumar <chandan1819@example.com>" \
      org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.name="kafka-guardian" \
      org.label-schema.description="Autonomous monitoring and self-healing system for Apache Kafka clusters" \
      org.label-schema.url="https://github.com/chandan1819/kafka-guardian" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/chandan1819/kafka-guardian" \
      org.label-schema.vendor="Chandan Kumar" \
      org.label-schema.version=$VERSION \
      org.label-schema.schema-version="1.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    KAFKA_GUARDIAN_CONFIG_PATH="/etc/kafka-guardian/config.yaml" \
    KAFKA_GUARDIAN_LOG_LEVEL="INFO"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    dumb-init \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r kafka-guardian && \
    useradd -r -g kafka-guardian -d /app -s /bin/bash kafka-guardian

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create necessary directories
RUN mkdir -p /etc/kafka-guardian \
             /var/log/kafka-guardian \
             /opt/kafka-guardian/plugins \
             /app && \
    chown -R kafka-guardian:kafka-guardian /etc/kafka-guardian \
                                          /var/log/kafka-guardian \
                                          /opt/kafka-guardian \
                                          /app

# Copy application files
COPY --chown=kafka-guardian:kafka-guardian examples/config_docker.yaml /etc/kafka-guardian/config.yaml.template
COPY --chown=kafka-guardian:kafka-guardian scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --chown=kafka-guardian:kafka-guardian scripts/healthcheck.sh /usr/local/bin/healthcheck.sh

# Make scripts executable
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/healthcheck.sh

# Switch to non-root user
USER kafka-guardian
WORKDIR /app

# Expose ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

# Set entrypoint
ENTRYPOINT ["dumb-init", "--", "/usr/local/bin/docker-entrypoint.sh"]

# Default command
CMD ["kafka-guardian", "--config", "/etc/kafka-guardian/config.yaml"]

# Development stage
FROM production as development

# Switch back to root for development tools
USER root

# Install development dependencies
RUN apt-get update && apt-get install -y \
    vim \
    less \
    htop \
    strace \
    tcpdump \
    && rm -rf /var/lib/apt/lists/*

# Install development Python packages
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install -r /tmp/requirements-dev.txt

# Switch back to kafka-guardian user
USER kafka-guardian

# Override entrypoint for development
ENTRYPOINT ["dumb-init", "--"]
CMD ["bash"]
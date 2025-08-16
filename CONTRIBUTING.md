# Contributing to Kafka Guardian

Thank you for your interest in contributing to Kafka Guardian! This document provides guidelines and information for contributors.

## 🤝 Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose
- Git
- A Kafka cluster for testing (can be local via Docker)

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/your-username/kafka-guardian.git
   cd kafka-guardian
   ```

2. **Set up Development Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   
   # Install pre-commit hooks
   pre-commit install
   ```

3. **Start Test Environment**
   ```bash
   docker-compose -f docker-compose.test.yml up -d
   ```

4. **Run Tests**
   ```bash
   pytest tests/
   ```

## 📋 Development Workflow

### Branch Naming Convention

- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Test improvements

### Commit Message Format

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(monitoring): add Prometheus metrics support
fix(recovery): handle timeout in service restart
docs(readme): update installation instructions
test(integration): add end-to-end recovery tests
```

## 🧪 Testing Guidelines

### Test Structure

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Integration tests with external systems
├── e2e/           # End-to-end tests
├── performance/   # Performance and load tests
└── fixtures/      # Test data and fixtures
```

### Writing Tests

1. **Unit Tests**
   ```python
   import pytest
   from unittest.mock import Mock, patch
   from kafka_guardian.monitoring import MonitoringService

   class TestMonitoringService:
       def test_health_check_success(self):
           # Test implementation
           pass
   ```

2. **Integration Tests**
   ```python
   import pytest
   from kafka_guardian.integration_test_base import IntegrationTestBase

   class TestKafkaIntegration(IntegrationTestBase):
       def test_kafka_broker_monitoring(self):
           # Test with real Kafka instance
           pass
   ```

3. **Test Coverage**
   - Aim for >90% code coverage
   - Include edge cases and error conditions
   - Test both success and failure scenarios

### Running Tests

```bash
# All tests
pytest

# Specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# With coverage
pytest --cov=src --cov-report=html

# Performance tests
python tests/performance/benchmark.py
```

## 📝 Documentation Guidelines

### Documentation Types

1. **Code Documentation**
   - Use docstrings for all public functions and classes
   - Follow Google docstring format
   - Include type hints

2. **User Documentation**
   - Update relevant documentation in `docs/`
   - Include examples and use cases
   - Keep language clear and concise

3. **API Documentation**
   - Document all public APIs
   - Include request/response examples
   - Specify error conditions

### Documentation Example

```python
def check_node_health(self, node_config: NodeConfig) -> NodeStatus:
    """Check the health of a Kafka node.
    
    Args:
        node_config: Configuration for the node to check
        
    Returns:
        NodeStatus object containing health information
        
    Raises:
        ConnectionError: If unable to connect to the node
        TimeoutError: If the health check times out
        
    Example:
        >>> config = NodeConfig(node_id="kafka-1", host="localhost", port=9092)
        >>> status = monitoring_service.check_node_health(config)
        >>> print(status.is_healthy)
        True
    """
```

## 🔧 Code Style Guidelines

### Python Style

- Follow [PEP 8](https://pep8.org/)
- Use [Black](https://black.readthedocs.io/) for code formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Use [flake8](https://flake8.pycqa.org/) for linting

### Code Quality Tools

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Security scanning
bandit -r src/
```

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.10.1
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/flake8
    rev: 4.0.1
    hooks:
      - id: flake8
```

## 🐛 Bug Reports

### Before Submitting

1. Check existing issues to avoid duplicates
2. Test with the latest version
3. Gather relevant information

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Configure system with '...'
2. Run command '...'
3. See error

**Expected behavior**
What you expected to happen.

**Environment:**
- OS: [e.g. Ubuntu 20.04]
- Python version: [e.g. 3.9.7]
- Kafka Guardian version: [e.g. 1.2.3]
- Kafka version: [e.g. 2.8.0]

**Configuration:**
```yaml
# Your configuration (remove sensitive data)
```

**Logs:**
```
# Relevant log entries
```

**Additional context**
Any other context about the problem.
```

## 💡 Feature Requests

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
A clear description of what the problem is.

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Alternative solutions or features you've considered.

**Use case**
Describe your specific use case and how this feature would help.

**Additional context**
Any other context, mockups, or examples.
```

## 🔌 Plugin Development

### Creating a Plugin

1. **Choose Plugin Type**
   - Monitoring Plugin
   - Recovery Plugin
   - Notification Plugin

2. **Implement Interface**
   ```python
   from kafka_guardian.plugins import MonitoringPlugin
   
   class MyMonitoringPlugin(MonitoringPlugin):
       def check_health(self, node_config):
           # Implementation
           pass
   ```

3. **Add Tests**
   ```python
   class TestMyMonitoringPlugin:
       def test_health_check(self):
           # Test implementation
           pass
   ```

4. **Update Documentation**
   - Add plugin to documentation
   - Include configuration examples
   - Document any dependencies

## 📦 Release Process

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH`
- Major: Breaking changes
- Minor: New features (backward compatible)
- Patch: Bug fixes (backward compatible)

### Release Checklist

1. Update version in `setup.py` and `__init__.py`
2. Update `CHANGELOG.md`
3. Run full test suite
4. Update documentation
5. Create release PR
6. Tag release after merge
7. Publish to PyPI
8. Update Docker images

## 🏆 Recognition

Contributors are recognized in:
- `CONTRIBUTORS.md` file
- Release notes
- Project documentation

## 📞 Getting Help

- **GitHub Discussions**: For questions and general discussion
- **GitHub Issues**: For bug reports and feature requests
- **Email**: kafka-guardian-dev@your-org.com
- **Slack**: #kafka-guardian-dev (invite required)

## 📚 Resources

- [Python Style Guide](https://pep8.org/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Git Best Practices](https://git-scm.com/book/en/v2)

Thank you for contributing to Kafka Guardian! 🎉
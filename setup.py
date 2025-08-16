#!/usr/bin/env python3
"""Setup script for Kafka Guardian."""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
def read_requirements(filename):
    """Read requirements from file."""
    with open(filename, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="kafka-guardian",
    version="1.0.0",
    author="Chandan Kumar",
    author_email="chandan1819@example.com",
    description="Autonomous monitoring and self-healing system for Apache Kafka clusters",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/chandan1819/kafka-guardian",
    project_urls={
        "Bug Tracker": "https://github.com/chandan1819/kafka-guardian/issues",
        "Documentation": "https://github.com/chandan1819/kafka-guardian/blob/main/docs/",
        "Source Code": "https://github.com/chandan1819/kafka-guardian",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements("requirements.txt"),
    extras_require={
        "dev": read_requirements("requirements-dev.txt"),
        "test": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "pytest-asyncio>=0.18.0",
            "pytest-mock>=3.0",
        ],
        "docs": [
            "sphinx>=4.0",
            "sphinx-rtd-theme>=1.0",
            "myst-parser>=0.17",
        ],
    },
    entry_points={
        "console_scripts": [
            "kafka-guardian=kafka_self_healing.main:main",
            "kafka-guardian-config=kafka_self_healing.config:main",
        ],
    },
    include_package_data=True,
    package_data={
        "kafka_self_healing": [
            "config/*.yaml",
            "templates/*.j2",
            "schemas/*.json",
        ],
    },
    zip_safe=False,
    keywords=[
        "kafka",
        "monitoring",
        "self-healing",
        "automation",
        "devops",
        "reliability",
        "cluster-management",
        "apache-kafka",
        "zookeeper",
        "observability",
    ],
)
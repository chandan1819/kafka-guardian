#!/bin/bash
# Quick deployment script for Kafka Guardian

set -e

echo "🚀 Kafka Guardian - Quick GitHub Deployment"
echo "=========================================="

# Make the main deployment script executable
chmod +x deploy_to_github.sh

# Run the deployment
./deploy_to_github.sh

echo ""
echo "✅ Deployment completed!"
echo ""
echo "If you encounter authentication issues, try:"
echo "1. Set up SSH key: ssh-keygen -t ed25519 -C 'chandan1819@example.com'"
echo "2. Add to GitHub: cat ~/.ssh/id_ed25519.pub"
echo "3. Or use personal access token instead of password"
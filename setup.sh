#!/bin/bash

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI not found. Please install it first: https://cli.github.com/manual/installation"
    exit 1
fi

# Check if user is logged in to GitHub CLI
if ! gh auth status &> /dev/null; then
    echo "You are not logged in to GitHub CLI. Please login first with: gh auth login"
    exit 1
fi

# Get GitHub username and token
GITHUB_USERNAME=$(gh api user | jq -r .login)
GITHUB_TOKEN=$(gh auth token)

if [ -z "$GITHUB_USERNAME" ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "Failed to get GitHub username or token. Please make sure you're logged in to GitHub CLI."
    exit 1
fi

# Set repository name
REPO_NAME="bugfixgpt-ecommerce"
echo "Creating repository: $GITHUB_USERNAME/$REPO_NAME"

# Check if the repository already exists
if gh repo view $GITHUB_USERNAME/$REPO_NAME &> /dev/null; then
    echo "Repository $GITHUB_USERNAME/$REPO_NAME already exists."
    read -p "Do you want to use the existing repository? (y/n): " use_existing
    if [ "$use_existing" != "y" ]; then
        read -p "Enter a new repository name: " new_repo_name
        REPO_NAME=$new_repo_name
        echo "Creating repository: $GITHUB_USERNAME/$REPO_NAME"
        gh repo create $REPO_NAME --public --description "BugFixGPT Phase 4: E-commerce API Microservices" --confirm
    fi
else
    # Create a new repository
    gh repo create $REPO_NAME --public --description "BugFixGPT Phase 4: E-commerce API Microservices" --confirm
fi

# Create .env file
echo "Creating .env file with GitHub credentials"
cat > .env << EOF
GITHUB_TOKEN=$GITHUB_TOKEN
GITHUB_REPO_OWNER=$GITHUB_USERNAME
GITHUB_REPO_NAME=$REPO_NAME
LLM_API_ENDPOINT=https://api.rabbithole.cred.club
LLM_API_KEY=sk-w_Ce6_0_09uJzezAOWTCIw
LLM_MODEL=gpt-4o
USE_MOCK=false
EOF

# Create directories for logs and backups
mkdir -p logs backups
echo "Created logs and backups directories"

# Export environment variables for the current session
export GITHUB_TOKEN=$GITHUB_TOKEN
export GITHUB_REPO_OWNER=$GITHUB_USERNAME
export GITHUB_REPO_NAME=$REPO_NAME
export LLM_API_ENDPOINT=https://api.rabbithole.cred.club
export LLM_API_KEY=sk-w_Ce6_0_09uJzezAOWTCIw
export LLM_MODEL=gpt-4o
export USE_MOCK=false

echo "Setup completed successfully!"
echo ""
echo "Repository: $GITHUB_USERNAME/$REPO_NAME"
echo "Environment variables have been set for the current session and saved to .env file"
echo ""
echo "To start the system, run:"
echo "docker compose up --build"
echo ""
echo "To monitor logs, run:"
echo "docker compose logs -f log-analyzer" 
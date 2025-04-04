# Phase 4: BugFixGPT for Large-Scale API Services

This directory contains the implementation of Phase 4 of the BugFixGPT project, which focuses on extending BugFixGPT to handle larger, more complex codebases with high-scale APIs.

## Architecture

The Phase 4 implementation consists of an e-commerce platform with multiple microservices:

1. **API Gateway**: Routes requests to the appropriate microservices
2. **Product Service**: Manages product catalog
3. **Order Service**: Handles order processing
4. **User Service**: Manages user accounts
5. **Payment Service**: Processes payments
6. **Inventory Service**: Tracks product inventory

Additionally, the BugFixGPT components are integrated:

- **Log Scraper**: Monitors service logs for errors
- **Log Analyzer**: Analyzes errors and generates fixes using LLM (GPT-4o/Claude)

## Intentional Bugs

The codebase contains intentional bugs to demonstrate BugFixGPT's capabilities:

### API Gateway Issues:
- Missing check for service existence in timeout configuration
- Incorrect handling of binary responses
- Improper error handling for connection issues

### Product Service Issues:
- MongoDB ObjectId serialization problems
- No pagination for large datasets
- Case sensitivity issues in search
- Invalid field updates

## Running the System

### Prerequisites
- Docker and Docker Compose
- GitHub CLI (`gh`) installed and logged in
- GitHub repository for the code fixes

### Setup
1. Create a GitHub repository for the project:
   ```
   gh repo create bugfixgpt-ecommerce --public
   ```

2. Set environment variables:
   ```bash
   export GITHUB_TOKEN=$(gh auth token)
   export GITHUB_REPO_OWNER=$(gh api user | jq -r .login)
   export GITHUB_REPO_NAME=bugfixgpt-ecommerce
   export LLM_MODEL=gpt-4o  # or claude-3-7-sonnet
   ```

3. Start the system:
   ```bash
   cd phase4
   docker-compose up --build
   ```

## Testing the System

Once the system is running, you can trigger the bugs by making requests to the API Gateway:

1. **API Gateway Timeout Bug**:
   ```bash
   curl 'http://localhost:8000/unknown-service/products'
   ```

2. **ObjectId Serialization Bug**:
   ```bash
   curl 'http://localhost:8000/products/'
   ```

3. **Search Case Sensitivity Bug**:
   ```bash
   curl 'http://localhost:8000/products/category/electronics'
   ```

## Monitoring

You can monitor the logs and see BugFixGPT in action:

```bash
docker-compose logs -f log-analyzer
```

## GitHub Integration

BugFixGPT will automatically create pull requests in your GitHub repository with fixes for the detected bugs.

## Architecture Diagram

```
┌─────────────────┐         ┌──────────────────┐
│                 │         │                  │
│    API Gateway  │◄────────┤   Log Scraper    │
│                 │         │                  │
└────────┬────────┘         └────────┬─────────┘
         │                           │
         ▼                           ▼
┌─────────────────┐         ┌──────────────────┐
│  Microservices  │         │   Log Analyzer   │
│  - Products     │         │    (LLM-based)   │
│  - Orders       │         │                  │
│  - Users        │         └────────┬─────────┘
│  - Payments     │                  │
│  - Inventory    │                  ▼
└────────┬────────┘         ┌──────────────────┐
         │                  │  GitHub PR with  │
         ▼                  │      Fixes       │
┌─────────────────┐         │                  │
│    MongoDB      │         └──────────────────┘
│                 │
└─────────────────┘
``` 
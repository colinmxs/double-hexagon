#!/usr/bin/env bash
# ==========================================================================
# Container entrypoint — bootstraps read-only Git and AWS credentials
# ==========================================================================
set -e

# --- Git: configure read-only PAT for HTTPS clones/fetches ---
if [ -n "$GH_TOKEN" ]; then
  echo "Configuring Git with read-only PAT..."
  git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
  git config --global credential.helper store

  # Also authenticate the GitHub CLI
  echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null || true
  echo "Git + GitHub CLI configured."
fi

# --- AWS: configure credentials (supports session tokens for assumed roles) ---
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "Configuring AWS credentials..."
  mkdir -p ~/.aws

  cat > ~/.aws/credentials <<EOF
[default]
aws_access_key_id = ${AWS_ACCESS_KEY_ID}
aws_secret_access_key = ${AWS_SECRET_ACCESS_KEY}
EOF

  # Append session token if provided (required for assumed roles / temporary creds)
  if [ -n "$AWS_SESSION_TOKEN" ]; then
    echo "aws_session_token = ${AWS_SESSION_TOKEN}" >> ~/.aws/credentials
  fi

  cat > ~/.aws/config <<EOF
[default]
region = ${AWS_DEFAULT_REGION:-us-east-1}
output = json
EOF

  echo "AWS CLI configured (region: ${AWS_DEFAULT_REGION:-us-east-1})."

  # Quick verification
  aws sts get-caller-identity 2>/dev/null && echo "AWS identity verified." || echo "Warning: AWS credentials may be invalid or expired."
fi

# Hand off to the container command (default: sleep infinity)
exec "$@"

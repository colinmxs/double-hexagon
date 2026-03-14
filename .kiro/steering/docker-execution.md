# Docker Container Execution

All shell commands must be executed inside the Docker container `devcontainer-dev-1`.

Prefix every bash command with:
```
docker exec devcontainer-dev-1
```

Do NOT run commands directly on the host. This applies to installs, builds, tests, linting, and any other shell operations.

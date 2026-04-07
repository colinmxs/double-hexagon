# Docker Container Execution

ALL commands must be executed inside the Docker container `double-hexagon-dev`. No exceptions. This includes git, npm, node, python, aws, cdk, vitest, eslint, and any other CLI tool.

Prefix every bash command with:
```
docker exec double-hexagon-dev
```

For commands that need a specific working directory:
```
docker exec -w /workspace/frontend double-hexagon-dev npm run build
```

The workspace is mounted at `/workspace` inside the container.

## If the container is not running

Check first:
```
docker ps --filter name=double-hexagon-dev --format '{{.Names}}'
```

If empty, start it:
```
docker compose up -d
```

If it needs to be rebuilt (e.g. Dockerfile changed):
```
docker compose up -d --build
```

Then resume executing commands inside the container as normal.

## Installing new tools

If a command or tool is missing from the container and it makes sense as a permanent dependency, add it to the `Dockerfile` at the repo root and rebuild:
```
docker compose up -d --build
```

Do not install tools ad-hoc inside the running container with `apt-get` or `npm install -g`. Keep the image the source of truth.

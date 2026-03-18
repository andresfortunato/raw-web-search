# Phase 2: Docker Image + MCP Catalog

## Intent
Create a self-contained Docker image that bundles the MCP server + SearXNG + Redis so users can run everything with one command. Submit to Docker MCP Catalog for discovery.

## Key Decision: Architecture

The Docker image needs to run three things: our Python MCP server, SearXNG, and Redis. Two approaches:

**Option A: Single multi-service image (supervisord)**
- One image, one `docker run` command
- Uses supervisord to manage all three processes
- Simpler for users but harder to maintain

**Option B: Docker Compose profile published to registry**
- Publish our Python server as a Docker image
- Users run our `docker-compose.yml` which pulls all three images
- Cleaner separation but more complex for users

**Recommendation:** Option A for the Docker MCP Catalog (they expect single images). The existing docker-compose.yml stays as the dev/advanced option.

## Tasks

### 2.1: Create Dockerfile
- Multi-stage build: Python deps in build stage, slim runtime image
- Bundle: our Python package + SearXNG config template
- Entrypoint: starts SearXNG + Redis + our MCP server
- Must handle secret key generation at container startup
- MCP communication: stdio (container's stdin/stdout)
- Constraints: don't include Playwright (too heavy, ~500MB), keep base image small

### 2.2: Test Docker image locally
- Build and run the image
- Verify MCP server responds over stdio
- Verify SearXNG starts and searches work
- Verification: `docker run -i raw-web-search` accepts MCP JSON-RPC on stdin

### 2.3: Publish to Docker Hub
- Create Docker Hub account/repo if needed
- Tag and push image
- Verification: `docker pull andresfortunato/raw-web-search` works

### 2.4: Submit to Docker MCP Catalog
- Fork `github.com/docker/mcp-registry`
- Add entry for raw-web-search
- Open PR
- Verification: PR submitted

## Done when
- Dockerfile builds and runs
- Image published to Docker Hub
- PR submitted to Docker MCP Catalog

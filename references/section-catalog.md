# Section catalog

Candidate wiki sections and pages, with guidance on when each earns its place. **Don't include everything** — a focused wiki that matches the repo beats a bloated template. Use `analysis.json` to decide what's actually present.

The goal: someone new to the repo should be able to read top-to-bottom and understand *what it is*, *how it's built*, *how to run it*, and *where to look* for any given concern.

## Overview (almost always include)

- **Introduction** — what the project does, who it's for, headline capabilities. Lead from README and the package manifest.
- **Architecture** — the big picture: major components, how they fit, request/data flow. This is the most important page; include a system-level Mermaid diagram. (For a large repo this can be its own section.)
- **Tech stack** — languages, frameworks, key libraries and *why* they're used. Pull from dependency manifests.
- **Repository layout** — what lives where; map top-level directories to responsibilities. Skip if the repo is tiny.

## Getting started (include if the repo is runnable)

- **Installation & setup** — prerequisites, install steps, environment variables/config.
- **Running locally** — dev server, build, common commands. Ground in scripts from package.json / Makefile / Taskfile.
- **Testing** — how tests are organized and run.

## Architecture & design (include for non-trivial repos)

- **Core concepts / domain model** — the central abstractions and vocabulary.
- **Data model** — schemas, entities, relationships, migrations. Include for anything with a database or persistent state; an ER-style Mermaid diagram helps.
- **Key design decisions** — notable patterns, trade-offs, conventions. Useful when the codebase has opinionated structure.
- **Control / data flow** — trace an important path end-to-end (e.g. a request lifecycle, a job pipeline).

## Frontend (include only if there's a UI)

- **Frontend overview** — framework, app structure, routing.
- **Component architecture** — how components/pages are organized; shared/design-system pieces.
- **State management** — stores, context, data fetching.
- **Styling & assets** — approach to CSS/theming/build of assets.

## Backend (include if there's server-side logic)

- **Backend overview** — services, layering, entry points.
- **Business logic / services** — the core modules and what they own.
- **Middleware / cross-cutting** — auth, logging, error handling, validation.
- **Background jobs / async** — queues, workers, scheduled tasks. Include only if present.

## API reference (include if the repo exposes an API)

- **API overview** — protocol (REST/GraphQL/gRPC/WebSocket), base URLs, conventions.
- **Endpoints / operations** — grouped by resource; method, path, params, responses. For large APIs, split into multiple pages by resource.
- **Authentication & authorization** — how callers authenticate, scopes/roles.
- **Errors & status codes** — error shape and meanings.

## Integrations & infrastructure (include if relevant)

- **External integrations** — third-party services/APIs the project depends on.
- **Configuration** — full config surface, precedence, secrets handling.
- **Build & deployment** — CI/CD, containerization, release process. Ground in workflow files, Dockerfile, etc.
- **Observability** — logging, metrics, tracing, health checks.

## Contributing (optional)

- **Development workflow** — branching, code style, PR process. Usually only if a CONTRIBUTING doc exists.
- **Extending the system** — how to add a common unit of work (a new endpoint, a new component, a new plugin).

---

## Sizing guidance

- **Small repo / single library** → Overview (Introduction, Architecture, Tech stack) + Getting started + maybe API reference. ~5–8 pages.
- **Medium app (frontend + backend)** → add Frontend, Backend, Data model, API reference. ~12–20 pages.
- **Large / multi-service** → consider one Architecture section per service or domain; split the API reference by resource. 20+ pages.

When a single page's scope is clearly too large (e.g. "all endpoints" for a 100-route API), split it into multiple manifest entries *before* dispatching subagents.

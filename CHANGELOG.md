# Changelog

## [1.0.1] - 2026-03-13

### Added

- Release seed now includes:
  - 8 general-tool skills (with missing icons fixed for `docx/xlsx/pptx/pdf`)
  - 6 MCP entries with sanitized secrets
  - prompt templates
  - example project, requirements, conversation, and workflow seed
- Model provider seed now includes `Aliyun Coding Plan` and model list, with key injection via env var
- README upgrade guide from `V1.0.0` to `V1.0.1`

### Changed

- Dragon MCP behavior is now conditional:
  - If `dragon-mcp` is configured and enabled, Yuque async fetch/re-fetch is used
  - Otherwise Yuque URL gracefully degrades to normal URL processing
- Startup scripts now support explicit prod/dev mode and clearer rebuild behavior
- README language files reduced to two (`README.md`, `README.en-US.md`)

## [1.0.0] - 2026-03-13

### Added

- Fully Dockerized deployment mode
- Single bootstrap script for first-time setup
- baseline migration
- Open-source standard docs

### Changed

- Runtime ports moved to isolated release ports
- Backend startup mode switched from local process to container

### Removed

- Personal release artifacts and historical document folder from release branch
- Default MCP routes from public/admin navigation (v1.0)

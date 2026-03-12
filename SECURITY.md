# Security Policy

## Reporting

Please report security issues privately to maintainers before public disclosure.

## Scope

- Hardcoded secrets
- Data leakage
- Authentication and authorization issues
- Dependency vulnerabilities

## Secret Handling

- Never commit `.env` with real credentials
- Rotate `JWT_SECRET_KEY` in production

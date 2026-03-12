# Contributing

## Branching

- Feature/bugfix branches from `main`
- Conventional commit messages recommended

## Local Development

```bash
./scripts/start.sh
```

## Quality Checks

Backend:

```bash
cd backend
PYTHONPATH=. pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run build
```

## Pull Request Checklist

- [ ] Tests pass
- [ ] No personal data or secrets committed
- [ ] Migration included (if schema changed)
- [ ] CHANGELOG updated

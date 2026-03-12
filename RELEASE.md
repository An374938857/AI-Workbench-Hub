# Release Process

## Versioning

- Semantic Versioning: `MAJOR.MINOR.PATCH`

## Release Steps

1. Run full checks (backend + frontend)
2. Validate migration path (`alembic upgrade head`)
3. Update `CHANGELOG.md`
4. Tag release:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Migration Gate

Every release must validate:

- Empty database bootstrap
- Incremental upgrade from previous version

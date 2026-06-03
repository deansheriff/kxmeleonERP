# Versioning

Dotmac ERP uses semantic versioning:

```text
MAJOR.MINOR.PATCH
```

- `fix:`, `bug:`, `hotfix:`, or `patch:` bumps PATCH.
  Example: `1.1.9 -> 1.1.10`
- `feat:` or `feature:` bumps MINOR and resets PATCH.
  Example: `1.1.10 -> 1.2.0`
- `major:`, `breaking:`, or `BREAKING CHANGE` bumps MAJOR and resets MINOR/PATCH.
  Example: `1.2.0 -> 2.0.0`
- Unlabeled changes default to PATCH.

Use the helper script:

```bash
python scripts/bump_version.py "fix: asset list not loading"
python scripts/bump_version.py "feat: add depreciation report"
python scripts/bump_version.py "major: change asset numbering contract"
python scripts/bump_version.py --check
```

The script keeps these files in sync:

- `pyproject.toml`
- `package.json`
- `package-lock.json`
- `.env.example`
- `docker-compose.yml`
- `app/config.py`

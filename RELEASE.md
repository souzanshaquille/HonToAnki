# Release Process

Pushing a `v*` tag triggers GitHub Actions to build all platform binaries and create a GitHub Release.

## Steps

```bash
# 1. Ensure main is up to date
git checkout main
git pull

# 2. Tag the current commit
git tag v0.3.0

# 3. Push the tag (triggers CI build + release)
git push origin v0.3.0
```

Thats it. The workflow at `.github/workflows/release.yml`:

1. Extracts the version from the tag (strips the `v` prefix)
2. Injects it into `pyproject.toml` before building
3. Builds Windows MSI+ZIP, macOS PKG, and Linux deb+rpm in parallel
4. Creates a GitHub Release with auto-generated notes and attaches all artifacts

## What gets published

| Platform | Files |
|----------|-------|
| Windows | `HonToAnki-{version}.msi`, `HonToAnki-{version}.zip` |
| macOS | `HonToAnki-{version}.pkg` |
| Linux | `{version}.deb`, `{version}.rpm` |

## Notes

- The version in `pyproject.toml` is overwritten by the CI during build. Your local `pyproject.toml` is not affected.
- Release notes are auto-generated from commit messages since the last tag. Edit them on the GitHub Releases page if needed.
- If the workflow fails, delete the tag locally and remotely (`git tag -d v0.3.0 && git push origin --delete v0.3.0`), fix the issue, then tag again.

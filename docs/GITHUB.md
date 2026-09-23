# Publishing libbyctl to GitHub

The project is already initialized as a Git repository. To publish it from a machine authenticated to GitHub:

```bash
brew install gh
gh auth login
./scripts/publish-github.sh OWNER/libbyctl public
```

Use `private` instead of `public` if desired.

The script will:

1. Create the repository if it does not already exist.
2. Set the `origin` remote.
3. Ensure the default local branch is `main`.
4. Push the current history to GitHub.

After the remote is known, add the repository URLs back to `pyproject.toml` before publishing to PyPI:

```toml
[project.urls]
Homepage = "https://github.com/OWNER/libbyctl"
Issues = "https://github.com/OWNER/libbyctl/issues"
```

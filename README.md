# Gathering stats about the python/cpython repository

```bash
# Clone the repo
gh repo clone ambv/cpython-stats

# Make a virtualenv
vf new cpython-stats

# Install
cd cpython-stats
poetry install

# Create a .env file
cat >.env
GITHUB_API_TOKEN = ghp_aBCdEFgHIjKLmNOpQRsTUvXYz12345678901
<CTRL-D>

# Import Github PRs
python -m cpython_stats.import_gh_pr

# Import commits from python/cpython Git repo
python -m cpython_stats.import_git_repo
```

---

**DISCLAIMER:** this is provided without support.  Any changes in the
data sources that require modifications to files in this project
are up to you to perform.

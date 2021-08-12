from github import Github

from cpython_stats import import_gh_pr


def test_github_successful_login():
    gh = Github(import_gh_pr.GITHUB_API_TOKEN)
    cpython = gh.get_repo("python/cpython")
    assert cpython.ssh_url == "git@github.com:python/cpython.git"
    assert cpython.stargazers_count > 33_333

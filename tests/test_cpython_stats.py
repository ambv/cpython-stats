from github import Github

from cpython_stats import env
from cpython_stats import annotations


def test_github_successful_login():
    gh = Github(env.GITHUB_API_TOKEN)
    cpython = gh.get_repo("python/cpython")
    assert cpython.ssh_url == "git@github.com:python/cpython.git"
    assert cpython.stargazers_count > 33_333


def test_annotations_unions():
    actual = annotations.maybe_clean_annotation("str | None")
    expected = "Union[str, None]"
    assert actual == expected

    actual = annotations.maybe_clean_annotation("str | int | None")
    expected = "Union[Union[str, int], None]"
    assert actual == expected


def test_annotations_trivial():
    actual = annotations.maybe_clean_annotation("str")
    expected = "str"
    assert actual == expected

    actual = annotations.maybe_clean_annotation(str)
    expected = str
    assert actual == expected


def test_annotations_subscript_list():
    actual = annotations.maybe_clean_annotation("list[str | None]")
    expected = "list[Union[str, None]]"
    assert actual == expected

    actual = annotations.maybe_clean_annotation("List[str | int | None]")
    expected = "List[Union[Union[str, int], None]]"
    assert actual == expected


def test_annotations_subscript_dict():
    actual = annotations.maybe_clean_annotation("typing.Dict[int, str | None]")
    expected = "typing.Dict[int, Union[str, None]]"
    assert actual == expected

    actual = annotations.maybe_clean_annotation("Mapping[int | bool, str | int | None]")
    expected = "Mapping[Union[int, bool], Union[Union[str, int], None]]"
    assert actual == expected

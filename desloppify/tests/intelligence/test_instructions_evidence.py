"""Evidence gatherers feeding the instructions packet."""

from __future__ import annotations

import shutil
import subprocess

from desloppify.intelligence.instructions import evidence


def test_manifests_reads_pyproject_deps(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nrequires-python = ">=3.11"\ndependencies = ["requests>=2", "click"]\n'
        '[project.optional-dependencies]\nfull = ["rich"]\n[project.scripts]\ndemo = "demo:main"\n'
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18"}, "devDependencies": {"vitest": "^1"}, "scripts": {"test": "vitest"}, "engines": {"node": ">=20"}}'
    )
    out = evidence.gather_manifests(tmp_path)
    py = out["pyproject.toml"]
    assert py["python"] == ">=3.11"
    assert py["dependencies"] == ["requests>=2", "click"]
    assert py["optional"] == {"full": ["rich"]}
    assert py["scripts"] == {"demo": "demo:main"}
    js = out["package.json"]
    assert js["dependencies"] == {"react": "^18"}
    assert js["dev_dependencies"] == {"vitest": "^1"}
    assert js["scripts"] == {"test": "vitest"}
    assert js["engines"] == {"node": ">=20"}


def test_manifests_tolerate_bad_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\nbroken = \n")
    (tmp_path / "go.mod").write_text("module demo\n\ngo 1.22\n")
    out = evidence.gather_manifests(tmp_path)
    assert "parse_error" in out["pyproject.toml"]
    assert out["go.mod"]["raw_head"].startswith("module demo")


def test_tooling_reads_ruff_line_length_and_make_targets(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\n[tool.ruff.format]\nquote-style = "double"\n[tool.mypy]\nstrict = true\n'
    )
    (tmp_path / "Makefile").write_text("lint:\n\truff check .\ntests: lint\n\tpytest\n.PHONY: lint\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("jobs:\n  health:\n    runs-on: x\n  lint:\n    runs-on: y\n")
    (tmp_path / ".editorconfig").write_text("root = true\n")
    out = evidence.gather_tooling(tmp_path)
    assert out["settings"] == {"line_length": 100, "quote_style": "double", "mypy_strict": True}
    assert out["make_targets"] == ["lint", "tests"]
    assert out["ci_jobs"] == ["health", "lint"]
    assert ".editorconfig" in out["configs"] and "pyproject.toml" in out["configs"]


def test_layout_counts_dirs_and_zones(tmp_path):
    files = ["src/a.py", "src/pkg/b.py", "tests/test_a.py", "scripts/run.py"]
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n")
    out = evidence.gather_layout(tmp_path, files, lambda f: "test" if f.startswith("tests/") else "production")
    assert out["top_level"] == ["scripts", "src", "tests"]
    assert out["dir_file_counts"]["src"] == 2
    assert out["zone_counts"] == {"production": 3, "test": 1}


def test_naming_census_counts_cases():
    contents = {
        "a.py": "def load_user():\n    pass\ndef getUser():\n    pass\nclass UserRepo:\n    pass\n",
        "tests/test_a.py": "def test_x():\n    pass\n",
    }
    out = evidence.gather_naming_census(contents)
    assert out["function_case"] == {"snake": 2, "camel": 1, "pascal": 0}
    assert out["class_case"] == {"snake": 0, "camel": 0, "pascal": 1}
    assert out["common_prefixes"]["load"] == 1
    assert out["test_file_patterns"] == ["test_*.py"]


def test_comment_style_detects_google_docstrings():
    contents = {
        "a.py": '"""Load things.\n\nArgs:\n    x: the thing\n\nReturns:\n    the loaded thing\n"""\n# why: cache is cold on first call\nx = 1\ny = 2\n',
    }
    out = evidence.gather_comment_style(contents, sample_size=5)
    assert out["docstring_style"] == "google"
    assert out["comment_density_per_100_loc"] > 0
    assert out["samples"][0]["text"] == "why: cache is cold on first call"


def test_error_style_counts_strategies():
    contents = {
        "a.py": "class DemoError(Exception):\n    pass\ndef f():\n    raise DemoError()\n",
        "b.py": "def g():\n    return None\n",
        "c.py": "# rpy2's own class is an ImportError subclass too (LibraryError).\nclass Plain:\n    pass\n",
        "d.ts": "export class HttpError extends Error {}\n",
    }
    out = evidence.gather_error_style(contents)
    assert out["custom_exceptions"] == ["DemoError", "HttpError"]
    assert sum(out["strategies"].values()) >= 1


def test_git_sections_degrade_without_git(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert evidence.gather_git_history(tmp_path) == {"available": False}
    pr = evidence.gather_pr_style(tmp_path)
    assert pr["gh"] == {"available": False}
    assert pr["template"] is None


def test_git_history_reads_real_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("a")
    git("add", "a.txt")
    git("commit", "-q", "-m", "feat: add a\n\nBody line.\n\nCo-Authored-By: X <x@y.z>")
    (tmp_path / "b.txt").write_text("b")
    git("add", "b.txt")
    git("commit", "-q", "-m", "plain subject")
    out = evidence.gather_git_history(tmp_path)
    assert out["available"] is True
    assert out["subjects_sample"] == ["plain subject", "feat: add a"]
    assert out["conventional_commit_ratio"] == 0.5
    assert out["body_ratio"] == 0.5
    assert out["trailers"] == {"Co-Authored-By": 1}
    assert out["merge_commits"] == 0


def test_existing_rules_collects_current_instructions(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("rule one\n")
    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text("# Codebase instructions\n- CI-001 Be terse.\n")
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "rules" / "style.mdc").write_text("cursor rule\n")
    out = evidence.gather_existing_rules(tmp_path)
    assert out["files"]["CLAUDE.md"] == "rule one\n"
    assert out["files"][".cursor/rules/style.mdc"] == "cursor rule\n"
    assert out["current_instructions"].startswith("# Codebase instructions")

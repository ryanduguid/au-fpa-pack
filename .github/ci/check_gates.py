"""Check an aggregate gate job: its needs, their results and removed jobs.

usage: python .github/ci/check_gates.py WORKFLOW GATE [--exempt JOB ...] [--no-results]

Run from the repository root by the gate job of WORKFLOW, with RESULTS set to
toJSON(needs) and, on pull requests, the merge commit checked out with its
parents (fetch-depth: 2). It fails when:

- a needed job did not succeed (skipped with --no-results, where the gate
  applies its own result rules);
- a job in WORKFLOW other than GATE and the exempt jobs is missing from needs;
- on a pull request, a job on the base branch's copy of WORKFLOW (or, for a new
  or renamed file, of the one base workflow holding GATE or its reported name) is gone, and WORKFLOW
  has no comment "# removed-jobs: JOB" naming it (the declaration lives in the
  file, so it cannot change without a new commit and a new run);
- a line at job-key indentation in the jobs block is not a job key it can read.
"""

import json
import os
import re
import string
import subprocess
import sys

ID_START = set(string.ascii_letters + "_")
ID_CHARS = ID_START | set(string.digits + "-")


def job_key(text: str) -> str | None:
    """Return the job id a line (without its indentation) declares, or None if it is not a plain key."""
    quote = text[0] if text[:1] in ("'", '"') else ""
    rest = text[len(quote) :]
    length = 0
    while length < len(rest) and rest[length] in ID_CHARS:
        length += 1
    name, rest = rest[:length], rest[length:]
    if not name or name[0] not in ID_START or not rest.startswith(quote):
        return None
    rest = rest[len(quote) :].lstrip(" \t")
    if not rest.startswith(":") or rest[1:2] not in ("", " ", "\t"):
        return None
    return name


def literal_name(text: str) -> str | None:
    """Read a single-line literal name; unsupported YAML stays unknown."""
    text = text.strip()
    if text.startswith('"'):
        try:
            value, end = json.JSONDecoder().raw_decode(text)
        except ValueError:
            return None
        if isinstance(value, str) and value and not re.search(r"[\r\n]", value):
            tail = text[end:].strip()
            return value if not tail or tail.startswith("#") else None
        return None
    if text.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", text)
        return match[1].replace("''", "'") if match and match[1] else None
    text = re.split(r"\s+#", text, maxsplit=1)[0].strip()
    if (not text or text[0] in "!&*[]{}>|%@`#" or re.search(r":\s|[\r\n]", text)
            or text.lower() in {"null", "true", "false", "~"}
            or re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)):
        return None
    return text


def parse_jobs(text: str) -> tuple[dict[str, str | None], list[str]] | None:
    """Return job ids mapped to possible reported names, plus unreadable job-level lines."""
    parts = text.split("\njobs:\n", 1)
    if len(parts) != 2:
        return None
    names: dict[str, str | None] = {}
    unreadable: list[str] = []
    job = None
    named = False
    unknown = False
    in_name = False
    has_property = False
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip(" \t").startswith("#"):
            continue
        if line[:1] not in ("", " ", "#"):
            break  # the next top-level key ends the jobs block
        if line.startswith("  ") and line[2:3] not in ("", " ", "#"):
            job = job_key(line[2:])
            named = in_name = has_property = False
            if job is None:
                unreadable.append(line)
            else:
                tail = line.split(":", 1)[1].strip()
                unknown = job in names or bool(tail and not tail.startswith("#"))
                names[job] = None if unknown else job
        elif job is not None and line.strip() and not line.lstrip().startswith("#"):
            indent = len(line) - len(line.lstrip(" "))
            if indent < 4 or (not has_property and indent != 4):
                unknown = True
            if line.startswith("    ") and line[4:5] not in ("", " "):
                has_property = True
                key = job_key(line[4:])
                in_name = key == "name"
                if key is None or (in_name and named):
                    unknown = True
                elif in_name:
                    names[job] = literal_name(line.split(":", 1)[1])
                    named = True
            elif in_name:
                unknown = True  # a continued name is outside the single-line reader
            if unknown:
                names[job] = None
    return names, unreadable


def job_ids(text: str) -> set[str]:
    """Return the job ids of a workflow, failing on any job-level line it cannot read."""
    parsed = parse_jobs(text)
    if parsed is None:
        sys.exit("Cannot find the jobs block; the gate check needs updating")
    ids, unreadable = parsed
    if unreadable:
        sys.exit(f"Cannot read the job key {unreadable[0]!r}; the gate check needs updating")
    return set(ids)


def possible_context(name: str | None, context: str) -> bool:
    """Keep possible names using literal branches or the expression's literal ends."""
    if name is None:
        return True
    if "${{" not in name:
        return name == context
    prefix, expression = name.split("${{", 1)
    if "}}" not in expression:
        return True
    expression, suffix = expression.rsplit("}}", 1)
    alternatives = re.fullmatch(
        r"\s*[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*"
        r"\s*(?:==|!=)\s*'(?:[^']|'')*'\s*"
        r"&&\s*'((?:[^']|'')*)'\s*\|\|\s*'((?:[^']|'')*)'\s*", expression,
    )
    if alternatives:
        return any(context == prefix + branch.replace("''", "'") + suffix
                   for branch in alternatives.groups())
    return (len(context) >= len(prefix) + len(suffix)
            and context.startswith(prefix) and context.endswith(suffix))


def base_copy(workflow: str, gate: str, head: str) -> str | None:
    """Return the base branch's copy of WORKFLOW, or of its predecessor, or None if it is new."""
    candidates = {}
    if git("ls-tree", "--name-only", "HEAD^1", "--", workflow).strip():
        candidates[workflow] = git("show", f"HEAD^1:{workflow}")
    context = parse_jobs(head)[0][gate]
    if context is None or "${{" in context:
        sys.exit("Cannot determine the gate context; use a single-line literal name")
    # shortcut: this narrow YAML reader cannot resolve aliases or evaluate expressions.
    # Keep possible matches and reject ambiguity; use a full parser if broader syntax is needed.
    # Match ID and reported context together: preferring an ID collision could select
    # an unrelated workflow and silently lose the protected context's predecessor.
    for path in base_workflow_paths():
        # GitHub reads workflows only from the top level of .github/workflows.
        if path.count("/") == 2 and path.endswith((".yml", ".yaml")):
            text = git("show", f"HEAD^1:{path}")
            parsed = parse_jobs(text)
            if parsed is None or not parsed[0] or parsed[1]:
                sys.exit(f"Cannot read base workflow {path}; the gate check needs updating")
            if gate in parsed[0] or any(possible_context(name, context) for name in parsed[0].values()):
                candidates[path] = text
    if len(candidates) > 1:
        sys.exit(
            f"More than one base workflow can precede {gate}; the gate check needs updating"
        )
    return next(iter(candidates.values()), None)


def workflow_file(argument: str) -> str:
    """Return the path of WORKFLOW, which must name a file directly in .github/workflows."""
    # The path comes from the directory listing, never from the argument itself.
    prefix = ".github/workflows/"
    listing = {entry.name: entry.path for entry in os.scandir(prefix) if entry.is_file()}
    name = argument[len(prefix) :] if argument.startswith(prefix) else ""
    if name not in listing:
        sys.exit(f"{argument} is not a file in .github/workflows")
    return listing[name]


def base_workflow_paths() -> list[str]:
    """Preserve pathname bytes, including CR and LF, before strict UTF-8 decoding."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD^1", "--", ".github/workflows/"],
        capture_output=True, check=True,
    ).stdout
    return listing.decode("utf-8").split("\0")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def main(argv: list[str]) -> None:
    args = [a for a in argv if a != "--no-results"]
    exempt: set[str] = set()
    if "--exempt" in args:
        index = args.index("--exempt")
        args, exempt = args[:index], set(args[index + 1 :])
    workflow, gate = args
    results = json.loads(os.environ["RESULTS"])

    if "--no-results" not in argv:
        failed = sorted(name for name, value in results.items() if value["result"] != "success")
        if failed:
            sys.exit("Jobs did not succeed: " + ", ".join(failed))

    with open(workflow_file(workflow), encoding="utf-8") as handle:
        text = handle.read()
    jobs = job_ids(text)
    if gate not in jobs:
        sys.exit(f"Cannot find {gate} in {workflow}; the gate check needs updating")
    missing = sorted(jobs - {gate} - exempt - set(results))
    if missing:
        sys.exit("Add these jobs to needs: " + ", ".join(missing))

    prefix = "# removed-jobs:"
    declared: set[str] = set()
    for line in text.splitlines():
        if line.strip().startswith(prefix):
            declared.update(name.strip() for name in line.strip()[len(prefix) :].split(","))
    # A declaration naming a job that still exists would waive a later removal.
    live = sorted(declared & jobs)
    if live:
        sys.exit("These removed-jobs declarations name jobs that still exist: " + ", ".join(live))

    # On a pull request HEAD is the merge commit, whose first parent is the base
    # the merge was made against. A missing parent fails the check rather than
    # skipping it; a workflow and gate both new in this pull request have no base.
    base = (
        base_copy(workflow, gate, text) if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" else None
    )
    if base is not None:
        removed = job_ids(base) - jobs
        if removed & declared:
            print(f"Declared removals from {workflow}: {', '.join(sorted(removed & declared))}")
        undeclared = sorted(removed - declared)
        if undeclared:
            sys.exit(
                "These jobs were removed from "
                + workflow
                + ": "
                + ", ".join(undeclared)
                + ". If that is intended, add the comment '# removed-jobs: "
                + ", ".join(undeclared)
                + "' to that file."
            )


if __name__ == "__main__":
    main(sys.argv[1:])

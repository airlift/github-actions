#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RECOMMENDED_SUBJECT_LENGTH = 50
MAX_SUBJECT_LENGTH = 60
RECOMMENDED_DESCRIPTION_LINE_LENGTH = 72
MAX_DESCRIPTION_LINE_LENGTH = 79

REVISION_RANGE_PATTERN = re.compile(r"^origin/[A-Za-z0-9._/-]+\.\.HEAD$")
URL_PATTERN = re.compile(r"(?:https?://|ssh://|git@|www\.)\S+")
TRAILER_PATTERN = re.compile(
    r"^(?:"
    r"Signed-off-by|Co-authored-by|Assisted-by|Reviewed-by|Acked-by|"
    r"Tested-by|Reported-by|Fixes|Refs|Relates-to|Change-Id"
    r"):\s+\S.+$",
    re.IGNORECASE,
)
ATTRIBUTION_PATTERN = re.compile(
    r"^(?:Assisted-by|Co-authored-by):\s*\S.*$",
    re.IGNORECASE,
)
PROHIBITED_ATTRIBUTION_MARKERS = (
    "aider",
    "claude",
    "cline",
    "codex",
    "copilot",
    "cursor",
    "devin",
    "gemini",
    "gpt",
    "windsurf",
)
COMMENT_PREFIX_MARKER = "commit-message-check"
SCISSORS_LINE_SUFFIX = " ------------------------ >8 ------------------------"


@dataclass(frozen=True)
class CommitSubjectViolation:
    commit: str
    subject: str
    length: int


@dataclass(frozen=True)
class CommitDescriptionViolation:
    commit: str
    subject: str
    line_number: int
    length: int
    line: str


@dataclass(frozen=True)
class CommitAttributionViolation:
    commit: str
    subject: str
    line_number: int
    line: str


def run_git(arguments: list[str], input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            check=True,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exception:
        print(f"git {' '.join(arguments)} failed:", file=sys.stderr)
        print(exception.stderr, file=sys.stderr)
        raise SystemExit(exception.returncode) from exception

    return result.stdout


def get_commits(revision_range: str) -> list[str]:
    if REVISION_RANGE_PATTERN.fullmatch(revision_range) is None:
        print(
            "Revision range must match origin/<base-ref>..HEAD with a safe base ref.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    output = run_git(["rev-list", "--reverse", "--no-merges", revision_range])
    return [line for line in output.splitlines() if line]


def get_commit_message(commit: str) -> str:
    return run_git(["show", "-s", "--format=%B", commit])


def get_subject_violations(
    commit: str, message: str
) -> list[CommitSubjectViolation]:
    lines = message.splitlines()
    if not lines or len(lines[0]) <= MAX_SUBJECT_LENGTH:
        return []

    return [
        CommitSubjectViolation(
            commit=commit,
            subject=lines[0],
            length=len(lines[0]),
        )
    ]


def is_wrapping_exempt(line: str, in_code_block: bool) -> bool:
    stripped = line.strip()

    if in_code_block:
        return True
    if not stripped:
        return True
    if stripped.startswith(">"):
        return True
    if TRAILER_PATTERN.fullmatch(stripped):
        return True

    tokens = stripped.split()
    if any(URL_PATTERN.search(token) for token in tokens):
        return is_wrapped_after_removing_unwrappable_tokens(tokens)
    if any(len(token) > MAX_DESCRIPTION_LINE_LENGTH for token in tokens):
        return is_wrapped_after_removing_unwrappable_tokens(tokens)

    return False


def is_wrapped_after_removing_unwrappable_tokens(tokens: list[str]) -> bool:
    wrappable_tokens = [
        token
        for token in tokens
        if (
            not URL_PATTERN.search(token)
            and len(token) <= MAX_DESCRIPTION_LINE_LENGTH
        )
    ]
    return len(" ".join(wrappable_tokens)) <= MAX_DESCRIPTION_LINE_LENGTH


def get_description_violations(
    commit: str, message: str
) -> list[CommitDescriptionViolation]:
    lines = message.splitlines()
    if not lines:
        return []

    subject = lines[0]
    in_code_block = False
    violations = []

    for line_number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        starts_code_fence = stripped.startswith("```") or stripped.startswith("~~~")

        if (
            len(line) > MAX_DESCRIPTION_LINE_LENGTH
            and not starts_code_fence
            and not is_wrapping_exempt(line, in_code_block)
        ):
            violations.append(
                CommitDescriptionViolation(
                    commit=commit,
                    subject=subject,
                    line_number=line_number,
                    length=len(line),
                    line=line,
                )
            )

        if starts_code_fence:
            in_code_block = not in_code_block

    return violations


def get_attribution_violations(
    commit: str, message: str
) -> list[CommitAttributionViolation]:
    lines = message.splitlines()
    if not lines:
        return []

    subject = lines[0]
    in_code_block = False
    violations = []

    for line_number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        starts_code_fence = stripped.startswith("```") or stripped.startswith("~~~")

        if starts_code_fence:
            in_code_block = not in_code_block
            continue
        if in_code_block or stripped.startswith(">"):
            continue

        if ATTRIBUTION_PATTERN.fullmatch(stripped) is None:
            continue

        normalized_line = stripped.casefold()
        if any(
            marker in normalized_line
            for marker in PROHIBITED_ATTRIBUTION_MARKERS
        ):
            violations.append(
                CommitAttributionViolation(
                    commit=commit,
                    subject=subject,
                    line_number=line_number,
                    line=line,
                )
            )

    return violations


def check_commit_message(
    commit: str,
    message: str,
) -> tuple[
    list[CommitSubjectViolation],
    list[CommitDescriptionViolation],
    list[CommitAttributionViolation],
]:
    return (
        get_subject_violations(commit, message),
        get_description_violations(commit, message),
        get_attribution_violations(commit, message),
    )


def check_commit_messages(
    revision_range: str,
) -> tuple[
    list[str],
    list[CommitSubjectViolation],
    list[CommitDescriptionViolation],
    list[CommitAttributionViolation],
]:
    commits = get_commits(revision_range)
    subject_violations = []
    description_violations = []
    attribution_violations = []

    for commit in commits:
        message = get_commit_message(commit)
        (
            commit_subject_violations,
            commit_description_violations,
            commit_attribution_violations,
        ) = check_commit_message(commit, message)
        subject_violations.extend(commit_subject_violations)
        description_violations.extend(commit_description_violations)
        attribution_violations.extend(commit_attribution_violations)

    return (
        commits,
        subject_violations,
        description_violations,
        attribution_violations,
    )


def check_commit_message_file(
    message_file: Path,
) -> tuple[
    list[CommitSubjectViolation],
    list[CommitDescriptionViolation],
    list[CommitAttributionViolation],
]:
    try:
        message = clean_commit_message_file(message_file.read_text())
    except OSError as exception:
        print(
            f"Unable to read commit message file {message_file}: {exception}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exception

    return check_commit_message("commit message", message)


def clean_commit_message_file(message: str) -> str:
    return strip_commit_comments(
        truncate_commit_scissors(message, get_comment_prefix())
    )


def get_comment_prefix() -> str:
    commented_marker = run_git(
        ["stripspace", "--comment-lines"],
        input_text=f"{COMMENT_PREFIX_MARKER}\n",
    )
    marker_suffix = f" {COMMENT_PREFIX_MARKER}\n"
    if not commented_marker.endswith(marker_suffix):
        print(
            "Unable to determine Git's configured comment prefix.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return commented_marker[: -len(marker_suffix)]


def truncate_commit_scissors(message: str, comment_prefix: str) -> str:
    scissors_line = f"{comment_prefix}{SCISSORS_LINE_SUFFIX}"
    lines = message.splitlines(keepends=True)
    for line_number, line in enumerate(lines):
        if line.rstrip("\r\n") == scissors_line:
            return "".join(lines[:line_number])

    return message


def strip_commit_comments(message: str) -> str:
    return run_git(["stripspace", "--strip-comments"], input_text=message)


def print_subject_violations(
    violations: list[CommitSubjectViolation],
) -> None:
    print(
        f"Commit subjects should be at most {RECOMMENDED_SUBJECT_LENGTH} "
        f"characters; this check fails subjects over {MAX_SUBJECT_LENGTH} "
        "characters.",
        file=sys.stderr,
    )
    print(file=sys.stderr)

    for violation in violations:
        print_commit_header(violation.commit, violation.subject)
        print(
            f"  subject: {violation.length} characters",
            file=sys.stderr,
        )
        print(file=sys.stderr)


def print_description_violations(
    violations: list[CommitDescriptionViolation],
) -> None:
    print(
        "Commit descriptions should wrap at "
        f"{RECOMMENDED_DESCRIPTION_LINE_LENGTH} characters; this check fails "
        f"ordinary text over {MAX_DESCRIPTION_LINE_LENGTH} characters.",
        file=sys.stderr,
    )
    print(
        "Long URLs, trailers, quoted text, code blocks, and long unwrappable "
        "tokens are allowed.",
        file=sys.stderr,
    )
    print(file=sys.stderr)

    for violation in violations:
        print_commit_header(violation.commit, violation.subject)
        print(
            f"  line {violation.line_number}: {violation.length} characters",
            file=sys.stderr,
        )
        print(f"  {violation.line}", file=sys.stderr)
        print(file=sys.stderr)


def print_attribution_violations(
    violations: list[CommitAttributionViolation],
) -> None:
    print(
        "AI models and coding tools must not be credited with Assisted-by or "
        "Co-authored-by trailers.",
        file=sys.stderr,
    )
    print("Human attributions using these trailers are allowed.", file=sys.stderr)
    print(file=sys.stderr)

    for violation in violations:
        print_commit_header(violation.commit, violation.subject)
        print(
            f"  line {violation.line_number}: prohibited AI/tool attribution",
            file=sys.stderr,
        )
        print(f"  {violation.line}", file=sys.stderr)
        print(file=sys.stderr)


def print_commit_header(commit: str, subject: str) -> None:
    print(f"{format_commit_reference(commit)} {subject}", file=sys.stderr)


def format_commit_reference(commit: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        return commit[:12]
    return commit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check commit subject length, description wrapping, "
            "and attribution trailers."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "revision_range",
        nargs="?",
        help="Git revision range to check, such as origin/main..HEAD.",
    )
    group.add_argument(
        "--message-file",
        type=Path,
        help="Commit message file to check, as passed to a commit-msg hook.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.message_file is not None:
        (
            subject_violations,
            description_violations,
            attribution_violations,
        ) = check_commit_message_file(args.message_file)
    else:
        (
            commits,
            subject_violations,
            description_violations,
            attribution_violations,
        ) = check_commit_messages(args.revision_range)
        commit_count = len(commits)

    if subject_violations:
        print_subject_violations(subject_violations)
    if description_violations:
        print_description_violations(description_violations)
    if attribution_violations:
        print_attribution_violations(attribution_violations)
    if subject_violations or description_violations or attribution_violations:
        return 1

    if args.message_file is not None:
        print(
            "Checked commit message; subject and description meet length limits "
            "and no prohibited attributions were found."
        )
    else:
        noun = "message" if commit_count == 1 else "messages"
        print(
            f"Checked {commit_count} commit {noun}; subjects and descriptions "
            "meet length limits and no prohibited attributions were found."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

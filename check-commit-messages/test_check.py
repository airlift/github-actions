#!/usr/bin/env python3

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check import (
    PROHIBITED_ATTRIBUTION_MARKERS,
    SCISSORS_LINE_SUFFIX,
    check_commit_message_file,
    get_attribution_violations,
    get_comment_prefix,
    get_description_violations,
    get_subject_violations,
    truncate_commit_scissors,
)


class TestCommitMessages(unittest.TestCase):
    def test_subject_length(self) -> None:
        cases = [
            ("60 characters", "x" * 60, []),
            ("61 characters", "x" * 61, [61]),
        ]

        for name, subject, expected_lengths in cases:
            with self.subTest(name=name):
                violations = get_subject_violations(
                    "abc123",
                    f"{subject}\n\nThis line is wrapped.",
                )
                self.assertEqual(
                    [violation.length for violation in violations],
                    expected_lengths,
                )

    def test_description_wrapping(self) -> None:
        cases = [
            (
                "wrapped description",
                "This line is wrapped.\n"
                "This line is also wrapped before it gets too wide.",
                [],
            ),
            ("79 characters", "x" * 79, []),
            (
                "80 characters",
                "This line is exactly eighty characters long and it should "
                "fail as written here.!",
                [3],
            ),
            (
                "long URL",
                "See https://example.com/path/that/is/long/enough/to/exceed/"
                "the/wrap/limit for context.",
                [],
            ),
            (
                "unwrapped text around a URL",
                "This surrounding prose is still far too long and should not "
                "be hidden behind a long URL. https://example.com/long/url",
                [3],
            ),
            (
                "long unwrappable token",
                "Use com.example.really.long.package.name.with.enough.parts."
                "to.exceed.the.wrap.limit.without.spaces.",
                [],
            ),
            (
                "code block",
                "```\n"
                "This line is ordinary prose in a code block but should not "
                "be checked by wrapping rules.\n"
                "```",
                [],
            ),
            (
                "block quote",
                "> This quoted body line can exceed seventy-nine characters "
                "because wrapping it would alter quoted text.",
                [],
            ),
            (
                "trailer",
                "Signed-off-by: Example Person With A Very Long Name "
                "<example.person.with.a.long.name@example.com>",
                [],
            ),
        ]

        for name, body, expected_lines in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    description_violating_lines(commit_message(body)),
                    expected_lines,
                )

    def test_rejects_prohibited_attribution_markers(self) -> None:
        for marker in PROHIBITED_ATTRIBUTION_MARKERS:
            with self.subTest(marker=marker):
                self.assertEqual(
                    attribution_violating_lines(
                        commit_message(
                            f"Co-authored-by: {marker} <bot@example.com>"
                        )
                    ),
                    [3],
                )

    def test_rejects_assisted_by_case_insensitively(self) -> None:
        self.assertEqual(
            attribution_violating_lines(
                commit_message(
                    "assisted-BY: Internal CoDeX helper <bot@example.com>"
                )
            ),
            [3],
        )

    def test_accepts_human_attributions(self) -> None:
        message = commit_message(
            "Assisted-by: Alex Example <alex@example.com>\n"
            "Co-authored-by: Taylor Example <taylor@example.com>"
        )
        self.assertEqual(attribution_violating_lines(message), [])

    def test_accepts_examples_that_are_not_attribution_trailers(self) -> None:
        messages = [
            commit_message(
                "```\nCo-authored-by: ChatGPT <bot@example.com>\n```"
            ),
            commit_message("> Co-authored-by: ChatGPT <bot@example.com>"),
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(attribution_violating_lines(message), [])

    def test_checks_commit_message_file(self) -> None:
        with patch("check.get_comment_prefix", return_value="#"):
            with tempfile.NamedTemporaryFile(
                mode="w+",
                encoding="utf-8",
            ) as message_file:
                message_file.write(
                    f"{'x' * 61}\n\n"
                    "This line is exactly eighty characters long and it should "
                    "fail as written here.!\n"
                    "Co-authored-by: Codex <bot@example.com>\n"
                    "# This comment is intentionally long enough to fail if "
                    "commit template comments are validated.\n"
                    "# ------------------------ >8 ------------------------\n"
                    "This verbose diff line is intentionally long enough to "
                    "fail if content after the scissors line is validated.\n"
                )
                message_file.flush()

                (
                    subject_violations,
                    description_violations,
                    attribution_violations,
                ) = check_commit_message_file(Path(message_file.name))

        self.assertEqual(
            [violation.length for violation in subject_violations],
            [61],
        )
        self.assertEqual(
            [violation.line_number for violation in description_violations],
            [3],
        )
        self.assertEqual(
            [violation.line_number for violation in attribution_violations],
            [4],
        )

    def test_keeps_scissors_line_with_different_comment_prefix(self) -> None:
        message = (
            "Add useful check\n\n"
            f"x{SCISSORS_LINE_SUFFIX}\n"
            "This content remains part of the commit message.\n"
        )

        self.assertEqual(truncate_commit_scissors(message, "#"), message)

    def test_reads_configured_comment_prefix(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.commentString",
                "GIT_CONFIG_VALUE_0": "//",
            },
        ):
            self.assertEqual(get_comment_prefix(), "//")

    def test_truncates_scissors_line_with_configured_comment_prefix(self) -> None:
        message = (
            "Add useful check\n\n"
            f"//{SCISSORS_LINE_SUFFIX}\n"
            "This content is excluded from the commit message.\n"
        )

        self.assertEqual(
            truncate_commit_scissors(message, "//"),
            "Add useful check\n\n",
        )


def commit_message(body: str) -> str:
    return f"Add useful check\n\n{body}"


def description_violating_lines(message: str) -> list[int]:
    violations = get_description_violations("abc123", message)
    return [violation.line_number for violation in violations]


def attribution_violating_lines(message: str) -> list[int]:
    violations = get_attribution_violations("abc123", message)
    return [violation.line_number for violation in violations]


if __name__ == "__main__":
    unittest.main()

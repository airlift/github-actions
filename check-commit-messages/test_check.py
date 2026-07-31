#!/usr/bin/env python3

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check import (
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
        self.assertSubjectAccepted("X" * 60)
        self.assertSubjectLengthViolation("X" * 61, expected_length=61)

    def test_subject_style(self) -> None:
        self.assertSubjectAccepted("Add useful check")
        self.assertSubjectAccepted("123 useful checks")
        self.assertSubjectStyleViolation(
            "add useful check",
            starts_with_lowercase=True,
        )
        self.assertSubjectStyleViolation(
            "Add useful check.",
            ends_with_period=True,
        )
        self.assertSubjectStyleViolation(
            "add useful check.",
            starts_with_lowercase=True,
            ends_with_period=True,
        )

    def test_rejects_common_past_tense_subject_starts(self) -> None:
        self.assertSubjectCorrection(
            "Added commit hook",
            "Add commit hook",
        )
        self.assertSubjectCorrection(
            "Bumped checkout version",
            "Bump checkout version",
        )
        self.assertSubjectCorrection(
            "Changed error message",
            "Change error message",
        )
        self.assertSubjectCorrection(
            "Converted workflow to Python",
            "Convert workflow to Python",
        )
        self.assertSubjectCorrection(
            "Created release action",
            "Create release action",
        )
        self.assertSubjectCorrection(
            "Disabled stale checks",
            "Disable stale checks",
        )
        self.assertSubjectCorrection(
            "Documented local setup",
            "Document local setup",
        )
        self.assertSubjectCorrection(
            "Enabled grouped updates",
            "Enable grouped updates",
        )
        self.assertSubjectCorrection(
            "Fixed commit parsing",
            "Fix commit parsing",
        )
        self.assertSubjectCorrection(
            "Implemented subject validation",
            "Implement subject validation",
        )
        self.assertSubjectCorrection(
            "Improved error output",
            "Improve error output",
        )
        self.assertSubjectCorrection(
            "Migrated action inputs",
            "Migrate action inputs",
        )
        self.assertSubjectCorrection(
            "Moved shared helper",
            "Move shared helper",
        )
        self.assertSubjectCorrection(
            "Refactored checker output",
            "Refactor checker output",
        )
        self.assertSubjectCorrection(
            "Removed old hook",
            "Remove old hook",
        )
        self.assertSubjectCorrection(
            "Renamed workflow job",
            "Rename workflow job",
        )
        self.assertSubjectCorrection(
            "Replaced local checker",
            "Replace local checker",
        )
        self.assertSubjectCorrection(
            "Reverted cache change",
            "Revert cache change",
        )
        self.assertSubjectCorrection(
            "Updated dependency pin",
            "Update dependency pin",
        )
        self.assertSubjectCorrection(
            "Upgraded Python version",
            "Upgrade Python version",
        )

    def test_accepts_other_subject_starts(self) -> None:
        self.assertSubjectAccepted("Fixes #123")
        self.assertSubjectAccepted("Adding support")
        self.assertSubjectAccepted("Fixed-point arithmetic")

    def test_description_wrapping(self) -> None:
        self.assertDescriptionAccepted(
            "This line is wrapped.\n"
            "This line is also wrapped before it gets too wide."
        )
        self.assertDescriptionAccepted("x" * 79)
        self.assertDescriptionWrappingViolation(
            "This line is exactly eighty characters long and it should "
            "fail as written here.!"
        )
        self.assertDescriptionAccepted(
            "See https://example.com/path/that/is/long/enough/to/exceed/"
            "the/wrap/limit for context."
        )
        self.assertDescriptionWrappingViolation(
            "This surrounding prose is still far too long and should not "
            "be hidden behind a long URL. https://example.com/long/url"
        )
        self.assertDescriptionAccepted(
            "Use com.example.really.long.package.name.with.enough.parts."
            "to.exceed.the.wrap.limit.without.spaces."
        )
        self.assertDescriptionAccepted(
            "```\n"
            "This line is ordinary prose in a code block but should not "
            "be checked by wrapping rules.\n"
            "```"
        )
        self.assertDescriptionAccepted(
            "> This quoted body line can exceed seventy-nine characters "
            "because wrapping it would alter quoted text."
        )
        self.assertDescriptionAccepted(
            "Signed-off-by: Example Person With A Very Long Name "
            "<example.person.with.a.long.name@example.com>"
        )

    def test_rejects_prohibited_attribution_markers(self) -> None:
        self.assertAttributionViolation(
            "Co-authored-by: Aider <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: Cline <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: OpenAI Codex <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: GitHub Copilot <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: Cursor Agent <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: Devin AI <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: gemini-code-assist[bot] "
            "<176961590+gemini-code-assist[bot]@users.noreply.github.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: ChatGPT <bot@example.com>"
        )
        self.assertAttributionViolation(
            "Co-authored-by: Windsurf Cascade <bot@example.com>"
        )

    def test_rejects_assisted_by_case_insensitively(self) -> None:
        self.assertAttributionViolation(
            "assisted-BY: OpenAI CoDeX <bot@example.com>"
        )

    def test_accepts_human_attributions(self) -> None:
        self.assertAttributionAccepted(
            "Assisted-by: Alex Example <alex@example.com>\n"
            "Co-authored-by: Taylor Example <taylor@example.com>"
        )

    def test_accepts_examples_that_are_not_attribution_trailers(self) -> None:
        self.assertAttributionAccepted(
            "```\nCo-authored-by: ChatGPT <bot@example.com>\n```"
        )
        self.assertAttributionAccepted(
            "> Co-authored-by: ChatGPT <bot@example.com>"
        )

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
                    "Co-authored-by: OpenAI Codex <bot@example.com>\n"
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

    def assertSubjectAccepted(self, subject: str) -> None:
        self.assertEqual(
            get_subject_violations(
                "abc123",
                f"{subject}\n\nThis line is wrapped.",
            ),
            [],
        )

    def assertSubjectLengthViolation(
        self,
        subject: str,
        expected_length: int,
    ) -> None:
        violations = get_subject_violations(
            "abc123",
            f"{subject}\n\nThis line is wrapped.",
        )
        self.assertEqual(
            [(violation.subject, violation.length) for violation in violations],
            [(subject, expected_length)],
        )

    def assertSubjectStyleViolation(
        self,
        subject: str,
        *,
        starts_with_lowercase: bool = False,
        ends_with_period: bool = False,
    ) -> None:
        violations = get_subject_violations("abc123", subject)
        self.assertEqual(
            [
                (
                    violation.subject,
                    violation.starts_with_lowercase,
                    violation.ends_with_period,
                    violation.suggested_imperative,
                )
                for violation in violations
            ],
            [(subject, starts_with_lowercase, ends_with_period, None)],
        )

    def assertSubjectCorrection(
        self,
        invalid_subject: str,
        valid_subject: str,
    ) -> None:
        violations = get_subject_violations("abc123", invalid_subject)
        self.assertEqual(
            [
                (
                    violation.subject,
                    violation.starts_with_lowercase,
                    violation.ends_with_period,
                    violation.suggested_imperative,
                )
                for violation in violations
            ],
            [(invalid_subject, False, False, valid_subject.split(maxsplit=1)[0])],
        )
        self.assertSubjectAccepted(valid_subject)

    def assertDescriptionAccepted(self, body: str) -> None:
        self.assertEqual(
            get_description_violations("abc123", commit_message(body)),
            [],
        )

    def assertDescriptionWrappingViolation(self, body: str) -> None:
        violations = get_description_violations("abc123", commit_message(body))
        self.assertEqual(
            [
                (
                    violation.line_number,
                    violation.length,
                    violation.line,
                )
                for violation in violations
            ],
            [(3, len(body), body)],
        )

    def assertAttributionAccepted(self, body: str) -> None:
        self.assertEqual(
            get_attribution_violations("abc123", commit_message(body)),
            [],
        )

    def assertAttributionViolation(self, body: str) -> None:
        violations = get_attribution_violations("abc123", commit_message(body))
        self.assertEqual(
            [
                (
                    violation.line_number,
                    violation.line,
                )
                for violation in violations
            ],
            [(3, body)],
        )


def commit_message(body: str) -> str:
    return f"Add useful check\n\n{body}"


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3

import unittest

from check import (
    PROHIBITED_ATTRIBUTION_MARKERS,
    get_attribution_violations,
    get_description_violations,
    get_subject_violations,
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

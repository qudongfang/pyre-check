# Copyright (c) 2016-present, Facebook, Inc.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-unsafe

import textwrap
import unittest
from typing import Dict, List, Optional
from unittest.mock import call, patch

from .. import UserError, errors
from ..ast import UnstableAST
from ..errors import (
    Errors,
    PartialErrorSuppression,
    SkippingGeneratedFileException,
    _suppress_errors,
)


class ErrorsTest(unittest.TestCase):
    def test_from_json(self) -> None:
        self.assertEqual(
            Errors.from_json('[{ "path": "test.py", "key": "value" }]'),
            Errors([{"path": "test.py", "key": "value"}]),
        )
        with self.assertRaises(UserError):
            Errors.from_json('[{ "path": "test.py", "key": "value" }')

    @patch.object(errors.Path, "read_text", return_value="")
    @patch.object(errors.Path, "write_text")
    def test_suppress(self, path_write_text, path_read_text) -> None:
        # Test run on multiple files.
        with patch(f"{errors.__name__}._suppress_errors", return_value="<transformed>"):
            Errors(
                [
                    {
                        "path": "path.py",
                        "line": 1,
                        "concise_description": "Error [1]: description",
                    },
                    {
                        "path": "other.py",
                        "line": 2,
                        "concise_description": "Error [2]: description",
                    },
                ]
            ).suppress()
            path_read_text.assert_has_calls([call(), call()])
            path_write_text.assert_has_calls(
                [call("<transformed>"), call("<transformed>")]
            )

        with patch(f"{errors.__name__}._suppress_errors", side_effect=UnstableAST()):
            with self.assertRaises(PartialErrorSuppression) as context:
                Errors(
                    [
                        {
                            "path": "path.py",
                            "line": 1,
                            "concise_description": "Error [1]: description",
                        },
                        {
                            "path": "other.py",
                            "line": 2,
                            "concise_description": "Error [2]: description",
                        },
                    ]
                ).suppress()
            self.assertEqual(
                set(context.exception.unsuppressed_paths), {"path.py", "other.py"}
            )

    def assertSuppressErrors(
        self,
        errors: Dict[int, List[Dict[str, str]]],
        input: str,
        expected_output: str,
        *,
        custom_comment: Optional[str] = None,
        max_line_length: Optional[int] = None,
        truncate: bool = False,
        unsafe: bool = False,
    ) -> None:
        def _normalize(input: str) -> str:
            return textwrap.dedent(input).strip().replace("FIXME", "pyre-fixme")

        self.assertEqual(
            _suppress_errors(
                _normalize(input),
                errors,
                custom_comment,
                max_line_length,
                truncate,
                unsafe,
            ),
            _normalize(expected_output),
        )

    def test_suppress_errors(self) -> None:
        self.assertSuppressErrors(
            {},
            """
            def foo() -> None: pass
            """,
            """
            def foo() -> None: pass
            """,
        )

        # Basic error suppression
        self.assertSuppressErrors(
            {1: [{"code": "1", "description": "description"}]},
            """
            def foo() -> None: pass
            """,
            """
            # FIXME[1]: description
            def foo() -> None: pass
            """,
        )

        # Indentation is correct.
        self.assertSuppressErrors(
            {2: [{"code": "1", "description": "description"}]},
            """
            def foo() -> None:
                pass
            """,
            """
            def foo() -> None:
                # FIXME[1]: description
                pass
            """,
        )

        # We skip generated files.
        with self.assertRaises(SkippingGeneratedFileException):
            _suppress_errors("@" "generated", {})

        # Custom message.
        self.assertSuppressErrors(
            {1: [{"code": "1", "description": "description"}]},
            """
            def foo() -> None: pass
            """,
            """
            # FIXME[1]: T1234
            def foo() -> None: pass
            """,
            custom_comment="T1234",
        )

        # Existing Comment
        self.assertSuppressErrors(
            {2: [{"code": "1", "description": "description"}]},
            """
            # comment
            def foo() -> None: pass
            """,
            """
            # comment
            # FIXME[1]: description
            def foo() -> None: pass
            """,
        )

        # Multiple Errors
        self.assertSuppressErrors(
            {
                1: [{"code": "1", "description": "description"}],
                2: [{"code": "2", "description": "description"}],
            },
            """
            def foo() -> None:
                pass
            """,
            """
            # FIXME[1]: description
            def foo() -> None:
                # FIXME[2]: description
                pass
            """,
        )

        # Multiple Errors
        self.assertSuppressErrors(
            {
                1: [
                    {"code": "1", "description": "description"},
                    {"code": "2", "description": "description"},
                ]
            },
            """
            def foo() -> None: pass
            """,
            """
            # FIXME[1]: description
            # FIXME[2]: description
            def foo() -> None: pass
            """,
        )

        # Line length limit
        self.assertSuppressErrors(
            {1: [{"code": "1", "description": "description"}]},
            """
            def foo() -> None: pass
            """,
            """
            # FIXME[1]:
            #  description
            def foo() -> None: pass
            """,
            max_line_length=20,
        )

        # Remove unused ignores.
        self.assertSuppressErrors(
            {1: [{"code": "0", "description": "description"}]},
            """
            # FIXME[0]: ignore
            def foo() -> None: pass
            """,
            """
            def foo() -> None: pass
            """,
        )
        self.assertSuppressErrors(
            {1: [{"code": "0", "description": "description"}]},
            """
            # FIXME[0]: ignore
            #  over multple lines
            def foo() -> None: pass
            """,
            """
            def foo() -> None: pass
            """,
        )
        self.assertSuppressErrors(
            {1: [{"code": "0", "description": "description"}]},
            """
            # FIXME[0]: ignore
            #  over multple lines
            # FIXME[1]: description
            def foo() -> None: pass
            """,
            """
            # FIXME[1]: description
            def foo() -> None: pass
            """,
        )
        self.assertSuppressErrors(
            {1: [{"code": "0", "description": "description"}]},
            """
            def foo() -> None: pass  # FIXME[0]: ignore
            """,
            """
            def foo() -> None: pass
            """,
        )

        # Truncate long comments.
        self.assertSuppressErrors(
            {1: [{"code": "1", "description": "description"}]},
            """
            def foo() -> None: pass
            """,
            """
            # FIXME[1]: descr...
            def foo() -> None: pass
            """,
            max_line_length=25,
            truncate=True,
        )

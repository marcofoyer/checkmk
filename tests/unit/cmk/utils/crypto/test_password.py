#!/usr/bin/env python3
# Copyright (C) 2022 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from typing import Any

import pytest

from cmk.utils.crypto.password import Password, PasswordPolicy


@pytest.mark.parametrize(
    "password",
    [
        "",
        "test 😹",
        "long" * 100,
    ],
)
def test_valid_password(password: str) -> None:
    Password(password)


def test_invalid_password() -> None:
    with pytest.raises(ValueError, match="null byte"):
        Password("foo\0bar")


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (Password("😹"), Password("😹"), True),
        (Password("     "), Password(" "), False),
        (Password(""), "", False),
        (Password("123"), 123, False),
    ],
)
def test_password_eq(a: Password, b: Any, expected: bool) -> None:
    assert (a == b) == expected


OK = PasswordPolicy.Result.OK
TooShort = PasswordPolicy.Result.TooShort
TooSimple = PasswordPolicy.Result.TooSimple


@pytest.mark.parametrize(
    "password,min_len,min_grp,expected",
    [
        ("", 0, 0, OK),
        ("", None, None, OK),
        ("cmk", 3, 1, OK),
        ("cmk", 4, 1, TooShort),
        ("", None, 1, TooSimple),
        ("abc123", None, 3, TooSimple),
        ("abc123", 10, 3, TooShort),  # too short takes precedence
        ("aB1!", 4, 4, OK),
    ],
)
def test_password_policy(
    password: str, min_len: int, min_grp: int, expected: PasswordPolicy.Result
) -> None:
    assert Password(password).verify_policy(PasswordPolicy(min_len, min_grp)) == expected

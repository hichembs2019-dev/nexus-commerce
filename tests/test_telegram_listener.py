import pytest

from src.integrations.telegram_listener import parse_callback_data


def test_parses_approve_callback_data():
    assert parse_callback_data("approve:123") == ("approve", 123)


def test_parses_reject_callback_data():
    assert parse_callback_data("reject:7") == ("reject", 7)


@pytest.mark.parametrize(
    "bad_data",
    ["approve", "approve:", "approve:abc", "maybe:123", "", "approve:123:extra"],
)
def test_rejects_malformed_callback_data(bad_data):
    with pytest.raises(ValueError):
        parse_callback_data(bad_data)

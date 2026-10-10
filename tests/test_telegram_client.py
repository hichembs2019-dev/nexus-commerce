from src.integrations.telegram_client import MockTelegramClient


def test_send_approval_request_records_the_proposal_and_summary_and_returns_a_message_id():
    client = MockTelegramClient()

    message_id = client.send_approval_request(42, "summary text")

    assert client.sent == [(42, "summary text")]
    assert message_id


def test_each_send_gets_a_distinct_message_id():
    client = MockTelegramClient()

    id1 = client.send_approval_request(1, "a")
    id2 = client.send_approval_request(2, "b")

    assert id1 != id2

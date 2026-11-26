import pytest
from tools.sms_reply_budget import short_sms_reply
from tools.retell_api_chat import agent_texts, ChatReviewRequired


@pytest.mark.parametrize('text,allowed', [
    ('a' * 198, True), ('a' * 199, False),
    ('^' * 198, True), ('\u2019' * 198, True),
    ('\U0001f600' * 99, True), ('\U0001f600' * 100, False),
    ('a' + '\U0001f600' * 98 + 'b', True),
    ('\ud800', False), ('\udfff', False), ('', False), ('  ', False), (None, False),
])
def test_conservative_utf16_bound_includes_astral_and_gsm_extensions(text, allowed):
    assert short_sms_reply(text) is allowed


def test_completion_join_includes_separators_and_never_truncates():
    messages = [{'role': 'agent', 'message_id': 'a', 'content': 'x' * 99},
                {'role': 'agent', 'message_id': 'b', 'content': 'y' * 99}]
    with pytest.raises(ChatReviewRequired, match='budget'):
        agent_texts(messages)
    messages[1]['content'] = 'y' * 98
    assert [m.content for m in agent_texts(messages)] == ['x' * 99, 'y' * 98]

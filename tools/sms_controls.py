"""Shared carrier control-message classification before any AI handoff."""
from tools.retell_sms import recipient_opted_out

CONTROLS = {'STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT', 'REVOKE',
            'OPTOUT', 'OPT OUT', 'START', 'UNSTOP', 'YES', 'HELP', 'INFO'}


def is_control(data):
    body = str(data.get('Body') or '').strip().upper().rstrip('.!?')
    return (bool(data.get('OptOutType')) or body in CONTROLS
            or recipient_opted_out([{'role': 'user', 'content': data.get('Body')}]))


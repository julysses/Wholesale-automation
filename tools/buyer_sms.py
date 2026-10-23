"""Dedicated buyer transport. No fallback, credential changes or implicit retries."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from config.settings import settings
from tools.facebook_consent import normalize_us_phone

FOOTER='Reply STOP to opt out or HELP for help.'


def _texas_now():
    return datetime.now(ZoneInfo('America/Chicago'))


def route():
    return {'account_sid':settings.twilio_account_sid,'service_sid':settings.buyer_sms_service_sid,
        'campaign_sid':settings.buyer_sms_campaign_sid,'from_number':settings.buyer_sms_from_number,'brand':settings.buyer_sms_brand}


def configuration_hold():
    r=route()
    if not settings.sms_live_enabled or not settings.buyer_sms_live_enabled:return 'buyer_sms_route_unavailable'
    if not settings.twilio_auth_token or not settings.twilio_webhook_base_url.startswith('https://'):return 'buyer_sms_route_unavailable'
    for field,prefix in [('account_sid','AC'),('service_sid','MG'),('campaign_sid','CM')]:
        if not re.fullmatch(prefix+'[0-9a-fA-F]{32}',r[field]):return 'buyer_sms_route_unavailable'
    if not re.fullmatch(r'\+1\d{10}',r['from_number']) or not r['brand'].strip() or len(r['brand'])>100 or '\n' in r['brand']:
        return 'buyer_sms_route_unavailable'
    if r['service_sid']==settings.twilio_messaging_service_sid or r['from_number']==settings.twilio_from_number:
        return 'buyer_sms_route_unavailable'
    return ''


def preflight(destination,body):
    hold=configuration_hold()
    if hold:return hold
    try:destination=normalize_us_phone(destination)
    except ValueError:return 'invalid_buyer_phone'
    if settings.sms_allowed_recipients and destination not in {s.strip() for s in settings.sms_allowed_recipients.split(',') if s.strip()}:
        return 'sms_recipient_not_allowed'
    now=_texas_now()
    if not settings.tcpa_allowed_start_hour<=now.hour<settings.tcpa_allowed_end_hour:return 'outside_sending_hours'
    if settings.sms_weekend_blocked and now.weekday()>=5:return 'weekend_sending_disabled'
    if not body.startswith(settings.buyer_sms_brand+': ') or not body.endswith(FOOTER) or len(body)>1600:
        return 'buyer_sms_copy_requires_review'
    return ''


def readiness(db):
    hold=configuration_hold()
    if not hold:
        try:
            result=db.rpc('buyer_sms_route_status',{'p_route':route()}).execute().data
            if not isinstance(result,dict) or result.get('approved') is not True:hold='buyer_sms_route_unavailable'
        except Exception:hold='buyer_sms_readiness_unconfirmed'
    return {'available':not bool(hold),'reason':hold,'brand':settings.buyer_sms_brand if not hold else '',
        'footer':FOOTER,'max_length':1600,'daily_recipient_limit':1}


def send(db,operator,reference,destination,body,sender_route):
    """One new reservation, one one-way authorization, at most one SDK create call."""
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
    from twilio.base.exceptions import TwilioRestException
    def outcome(status,sid=None):
        return db.rpc('record_buyer_sms_outcome',{'p_id':reference,'p_phone':destination,'p_sid':sid,'p_status':status}).execute().data
    known_sid=None
    try:
        # Build the non-retrying client before consuming the authorization latch.
        client=Client(sender_route['account_sid'],settings.twilio_auth_token,
            http_client=TwilioHttpClient(timeout=5,max_retries=0))
        permit=db.rpc('authorize_buyer_sms_submission',{'p_id':reference,'p_operator':operator}).execute().data
        if not isinstance(permit,dict) or permit.get('id')!=reference or type(permit.get('authorized')) is not bool:
            raise ValueError('Buyer SMS authorization unconfirmed')
        if permit['authorized'] is not True:return {**permit,'claimed':False}
        # Do not change the reviewed text after the immutable reservation.
        result=client.messages.create(body=body,to=destination,from_=sender_route['from_number'],
            messaging_service_sid=sender_route['service_sid'],
            status_callback=settings.twilio_webhook_base_url.rstrip('/')+'/webhooks/buyer-twilio/status?message_id='+reference)
        if not re.fullmatch(r'SM[0-9a-fA-F]{32}',str(result.sid)):raise ValueError('Provider SID unconfirmed')
        known_sid=result.sid
        return outcome('accepted',known_sid)
    except TwilioRestException as exc:
        if exc.status==400 and exc.code in {21610,30630}:
            return db.rpc('record_buyer_sms_optout_rejection',{'p_id':reference,'p_phone':destination,'p_code':exc.code}).execute().data
        return outcome('accepted',known_sid) if known_sid else outcome('unknown')
    except Exception:
        # A verified callback may already have committed delivery while create timed
        # out. SQL preserves that evidence rather than regressing it to unknown.
        return outcome('accepted',known_sid) if known_sid else outcome('unknown')

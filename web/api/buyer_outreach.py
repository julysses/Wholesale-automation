"""One-way buyer email dispatch; existing inquiry-only SMS route stays unavailable."""
from uuid import NAMESPACE_URL, UUID, uuid5
import html
import re
import logging

from fastapi import HTTPException
from config.settings import settings
from tools.buyer_intelligence_engine import build_deal_email, build_deal_sms

logger = logging.getLogger(__name__)


def _receipt(value, reference):
    if (not isinstance(value,dict) or value.get('id')!=reference or type(value.get('claimed')) is not bool
        or value.get('status') not in {'submitting','accepted','delivered','failed','skipped','held','unknown'}):
        raise ValueError('Outreach receipt is unconfirmed')
    return value


def dispatch(db, operator, req, channel):
    from tools.email_client import EmailClient
    if not operator:
        raise HTTPException(401,'Sign in to send outreach')
    if not req.request_id or not req.buyer_ids or len(req.buyer_ids)>25:
        raise HTTPException(422,'Use a stable request ID and between 1 and 25 buyer IDs')
    ids=list(dict.fromkeys(req.buyer_ids))
    try:
        for identity in ids:
            if str(UUID(identity))!=identity:raise ValueError()
    except ValueError:
        raise HTTPException(422,'Invalid buyer ID')
    counts={key:0 for key in ['sent_count','failed_count','skipped_count','dry_run_count','log_failed_count','unknown_count','unattempted_count']}
    outcomes=[]
    for index, buyer_id in enumerate(ids):
        reference=str(uuid5(NAMESPACE_URL,f'wholesaleos:buyer-outreach:{req.request_id}:{channel}:{buyer_id}'))
        try:
            rows=db.table('buyers').select('*').eq('id',buyer_id).limit(1).execute().data or []
            buyer=rows[0] if rows else {}
            destination=str(buyer.get('email' if channel=='email' else 'phone') or '').strip()
            if channel=='email':destination=destination.lower()
            name=f"{buyer.get('first_name','')} {buyer.get('last_name','')}".strip()
            client=EmailClient() if channel=='email' else None
            hold=''
            if channel=='sms':
                body=req.custom_message or build_deal_sms(buyer_name=name,zip_code=req.zip_code,price=req.price,
                    property_type=req.property_type,beds=req.beds,baths=req.baths)
                subject=''; plain=body
                hold='buyer_sms_route_unavailable'
            else:
                subject,body=build_deal_email(buyer_name=name,property_address=req.property_address,zip_code=req.zip_code,price=req.price,arv=req.arv,
                    assignment_fee=req.assignment_fee,property_type=req.property_type,beds=req.beds,baths=req.baths,condition=req.condition,
                    sender_name=settings.agency_contact_name or "Alex",agency_name=settings.agency_name or "Texas Wholesale Solutions")
                if req.custom_subject:subject=req.custom_subject
                plain=req.custom_message or html.unescape(re.sub(r"<[^>]+>","",body))
                if req.custom_message:body='<p>'+html.escape(req.custom_message).replace('\n','<br>\n')+'</p>'
                if not settings.email_live_enabled:hold='email_sending_disabled'
                elif not getattr(client,'_configured',False):hold='email_credentials_missing'
                elif settings.email_allowed_recipients and destination not in {x.strip().lower() for x in settings.email_allowed_recipients.split(',') if x.strip()}:
                    hold='email_recipient_not_allowed'
        except Exception:
            counts['unattempted_count']+=len(ids)-index
            outcomes.extend({'buyer_id':identity,'status':'unattempted','reason':'buyer_read_unavailable'} for identity in ids[index:])
            break
        payload={'destination':destination,'subject':subject,'body':body,'plain':plain,'deal_id':req.deal_id or None}
        try:
            receipt=_receipt(db.rpc('claim_buyer_outreach',{'p_id':reference,'p_request':str(req.request_id),
                'p_operator':operator,'p_buyer':buyer_id,'p_channel':channel,'p_payload':payload,'p_hold':hold}).execute().data,reference)
        except Exception:
            counts['unknown_count']+=1;counts['unattempted_count']+=len(ids)-index-1
            outcomes.append({'buyer_id':buyer_id,'message_id':reference,'status':'unknown','reason':'claim_response_unconfirmed'})
            outcomes.extend({'buyer_id':identity,'status':'unattempted'} for identity in ids[index+1:])
            break
        if receipt['claimed']:
            # SQL never grants a buyer SMS dispatch. Fail closed if the protocol changes.
            if channel!='email' or receipt['status']!='submitting':
                receipt={'id':reference,'claimed':False,'status':'unknown','reason':'unexpected_dispatch_claim'}
            else:
                submitted=False
                try:
                    accepted=client.send(destination,subject,plain,html_body=body,message_id=reference)
                    submitted=client.message_id is not None
                    receipt=_receipt(db.rpc('finish_buyer_outreach',{'p_id':reference,'p_operator':operator,
                        'p_status':'accepted' if accepted else 'unknown' if submitted else 'skipped',
                        'p_reason':'provider_acceptance_review' if accepted else 'submission_unconfirmed' if submitted else 'sender_blocked'}).execute().data,reference)
                except Exception:
                    counts['log_failed_count']+=1
                    receipt={'id':reference,'claimed':False,'status':'unknown','reason':'result_response_unconfirmed'}
                    logger.warning('Buyer outreach outcome unconfirmed for %s',reference)
        state=receipt['status']
        outcomes.append({'buyer_id':buyer_id,'message_id':reference,'status':state,
            'reason':receipt.get('reason'),'provider_message_id':receipt.get('provider_message_id'),'provider_submission_id':receipt.get('provider_submission_id')})
        if state in {'submitting','unknown'}:
            counts['unknown_count']+=1;counts['unattempted_count']+=len(ids)-index-1
            outcomes.extend({'buyer_id':identity,'status':'unattempted'} for identity in ids[index+1:])
            break
        if state=='held':
            counts['unattempted_count']+=len(ids)-index
            outcomes.extend({'buyer_id':identity,'status':'unattempted'} for identity in ids[index+1:])
            break
        counts[{'accepted':'sent_count','delivered':'sent_count','failed':'failed_count','skipped':'skipped_count'}[state]]+=1
    assert sum(counts[key] for key in ['sent_count','failed_count','skipped_count','dry_run_count','unknown_count','unattempted_count'])==len(ids)
    return {'status':'partial' if counts['unknown_count'] or counts['unattempted_count'] or counts['log_failed_count'] else 'complete',
        'request_id':str(req.request_id),'recipient_count':len(ids),'outcomes':outcomes,**counts}

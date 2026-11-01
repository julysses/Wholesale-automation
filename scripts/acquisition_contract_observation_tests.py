"""Disposable signed contract observations in the shared immutable evidence ledger."""
import json
import hashlib
import hmac
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID
from acquisition_contract_discovery_tests import ContractDiscoveryTests
from acquisition_contract_document_tests import DOCUMENT, DRAFT, SECOND
from test_acquisition_workspace import ROOT, PG, main, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal
from tools.acquisition_contract_attestation import ContractVerificationSigningKey, build_contract_scan_attestation

MIGRATION=ROOT/'frontend/supabase/migrations/20261031234409_acquisition_contract_observations.sql'
KEY='99300000-0000-4000-8000-000000000001'
OBS='ae000000-0000-4000-8000-000000000001'
FIELDS=('p_id','p_workspace','p_contract','p_version','p_purpose','p_artifact','p_actor','p_session','p_key','p_observation','p_signature')

class ContractObservationCases:
    def contract_key_scope(self):
        self.sql(f"INSERT INTO private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose,reviewed_by,approval_ref,valid_from,valid_until) VALUES('{WORKSPACE}','{KEY}','purchase_contract','{ADMIN}','{SECOND}',clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour')")

    def prepare_observation_fixture(self):
        self.document();self.attestation_fixture();self.contract_key_scope()

    def signed_contract(self, request=OBS, actor=ADMIN, signing_purposes=None, **changes):
        state=self.document_state()
        now=datetime.now(timezone.utc)
        key=ContractVerificationSigningKey(UUID(KEY),UUID(WORKSPACE),bytes.fromhex('ab'*32),frozenset(signing_purposes or {'purchase_contract'}),
            'ClamAV 1.4.3/12345/Thu Oct 29 00:00:00 2026','synthetic-v1',now-timedelta(hours=1),now+timedelta(hours=1))
        receipt=dict(status='scan_observed',workspace_id=WORKSPACE,contract_id=DRAFT,contract_version=1,artifact_id=DOCUMENT,purpose='purchase_contract',
            sha256=state['expected_sha256'],byte_size=state['expected_byte_size'],media_type=state['media_type'],retain_until=state['retain_until'],
            retention_policy_id=state['retention_policy_id'],checked_at=state['checked_at'],registry_checked_at=state['checked_at'],scan_checked_at=state['checked_at'],
            scanner='clamav-instream-v1',scanner_version=key.scanner_version,scan_policy_version=key.scan_policy_version,scan_status='no_detection',
            verifier_version='acquisition-contract-document-bytes-v1',registry_verifier_version='acquisition-contract-document-registry-v1',
            verification_persisted=False,scan_persisted=False,preview_authorized=False,legal_review_approved=False,execution_authorized=False)
        receipt.update(changes)
        return build_contract_scan_attestation(receipt,request_id=UUID(request),actor_id=UUID(actor),session_id=UUID(actor),key=key,clock=lambda:now)

    def record_contract_scan(self, args, actor=ADMIN, fail=False, **kwargs):
        result=self.sql('SELECT public.record_contract_document_verification('+','.join(literal(str(args[k])) for k in FIELDS)+')',user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_observation_exact_concurrent_retry_and_preserved_history(self):
        args=self.signed_contract()
        with ThreadPoolExecutor(max_workers=3) as pool: receipts=list(pool.map(lambda _:self.record_contract_scan(args),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in receipts),1)
        for row in receipts:
            self.assertEqual((row['contract_id'],row['contract_version'],row['purpose']),(DRAFT,1,'purchase_contract'))
            self.assertTrue(row['observation_persisted'])
            self.assertTrue(all(row[k] is False for k in ('preview_authorized','legal_review_approved','execution_authorized')))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_verifications WHERE contract_id IS NOT NULL'),'1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_evidence_verification' AND entity_id='{OBS}'"),'1')
        self.record_contract_scan(args|{'p_signature':'0'*64},fail=True)
        self.revoke_document();self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.assertTrue(self.record_contract_scan(args)['duplicate'])
        self.record_contract_scan(self.signed_contract(request=SECOND),fail=True)

    def test_contract_observation_scope_roles_sessions_and_raw_mutations(self):
        args=self.signed_contract()
        for change in ({'p_workspace':WORKSPACE_B},{'p_contract':SECOND},{'p_version':2},{'p_purpose':'title_report'},
                       {'p_artifact':SECOND},{'p_actor':OTHER},{'p_session':OTHER},{'p_signature':'0'*64}):
            self.record_contract_scan(args|change,fail=True)
        for change in ({'actor':OTHER},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.record_contract_scan(args,fail=True,**change)
        self.member(target=CALLER,role='acquisition_caller');self.record_contract_scan(args,actor=CALLER,fail=True)
        self.member();self.record_contract_scan(self.signed_contract(actor=OPERATOR),actor=OPERATOR,fail=True)
        self.record_contract_scan(args)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_verifications WHERE contract_id IS NOT NULL',user=OTHER),'0')
        for role in ('authenticated','anon','service_role'):
            for command in ('UPDATE acquisition_evidence_verifications SET contract_version=2','DELETE FROM acquisition_evidence_verifications','TRUNCATE acquisition_evidence_verifications',
                            'SELECT * FROM private.acquisition_contract_verification_key_scopes'):
                self.sql(command,user=ADMIN,role=role,fail=True)
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.record_contract_scan(args,fail=True)

    def test_contract_observation_requires_separate_current_key_scope(self):
        args=self.signed_contract()
        self.sql('DELETE FROM private.acquisition_contract_verification_key_scopes')
        self.record_contract_scan(args,fail=True)
        self.contract_key_scope()
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.record_contract_scan(args,fail=True)
        self.sql("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=NULL,valid_until=clock_timestamp()-interval '1 second'")
        self.record_contract_scan(args,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_verifications WHERE contract_id IS NOT NULL'),'0')

    def test_contract_observation_detected_bytes_block_mail_alias(self):
        # Register a mail artifact using exactly the contract bytes. No fake campaign
        # is used for the contract; the independent mail alias has its real campaign.
        self.evidence_register(request=SECOND,digest='b'*64)
        self.record_observation(self.signed_observation(request=SECOND,artifact=SECOND))
        self.assertFalse(self.evidence_scan_state(artifact=SECOND)['quarantined'])
        self.record_contract_scan(self.signed_contract(scan_status='detected'))
        self.assertTrue(self.evidence_scan_state(artifact=SECOND)['quarantined'])
        self.record_contract_scan(self.signed_contract(request='ae000000-0000-4000-8000-000000000002'))
        self.assertTrue(self.evidence_scan_state(artifact=SECOND)['quarantined'])

    def test_contract_observation_rejects_invalid_signed_values(self):
        original=self.signed_contract()
        for change in ({'byte_size':True},{'byte_size':124},{'sha256':'0'*64},{'media_type':'text/plain'},
                       {'scan_status':'clean'},{'extra':'not allowed'}, {'scanner_version':'unreviewed'},
                       {'checked_at':(datetime.now(timezone.utc)-timedelta(seconds=121)).isoformat()}):
            args=dict(original)
            args['p_observation']=json.dumps(json.loads(args['p_observation'])|change,sort_keys=True,separators=(',',':'))
            message='acquisition-contract-document-attestation-v1\n'+'\n'.join(str(args[k]) for k in FIELDS[:9])+'\n'+args['p_observation']
            args['p_signature']=hmac.new(bytes.fromhex('ab'*32),message.encode(),hashlib.sha256).hexdigest()
            self.record_contract_scan(args,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_verifications WHERE contract_id IS NOT NULL'),'0')

    def wait_contract_scan(self, change):
        args=self.signed_contract()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,
            '-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0)); END $$;\n\\echo locked\n")
            holder.stdin.flush()
            self.assertTrue(select.select([holder.stdout],[],[],5)[0]);self.assertEqual(holder.stdout.readline().strip(),'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.record_contract_scan,args,fail=True)
                try:
                    end=time.monotonic()+5;waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.record_contract_document_verification%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0','Observation must wait before authority changes')
                    change()
                finally:
                    holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_verifications WHERE contract_id IS NOT NULL'),'0')
        finally:
            holder.communicate('\\q\n',timeout=5)

    def test_contract_observation_wait_rechecks_membership(self):
        self.wait_contract_scan(lambda:self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE user_id='{ADMIN}'"))

    def test_contract_observation_wait_rechecks_key_scope(self):
        self.wait_contract_scan(lambda:self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()'))


class ContractObservationTests(ContractObservationCases, ContractDiscoveryTests):
    def setUp(self):
        super().setUp()
        self.attestation_fixture();self.record_observation(self.signed_observation())
        before=self.sql("SELECT jsonb_agg(to_jsonb(v)) FROM acquisition_evidence_verifications v")
        audits=self.sql('SELECT count(*) FROM audit_logs')
        self.sql(MIGRATION.read_text())
        self.assertEqual(self.sql("SELECT jsonb_agg(to_jsonb(v)-'contract_id'-'contract_version'-'contract_purpose') FROM acquisition_evidence_verifications v"),before)
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),audits)
        self.contract_key_scope()

if __name__=='__main__':
    raise SystemExit(main(ContractObservationTests,test_names=[n for n in ContractObservationCases.__dict__ if n.startswith('test_contract_observation_')]))

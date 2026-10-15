"""Stream the official Dallas current ownership archive once for a notice batch.
Index matches are discovery only; no lead, owner, active-sale or tracing certification.
"""
import argparse
import csv
from datetime import date, datetime, timezone
import io
import json
from pathlib import Path
import re
import zipfile
if __package__:
    from .tax_roll import digest, file_hash, validate_zip
else:
    from tax_roll import digest, file_hash, validate_zip

INFO_FIELDS = 'ACCOUNT_NUM APPRAISAL_YR DIVISION_CD BIZ_NAME OWNER_NAME1 OWNER_NAME2 EXCLUDE_OWNER OWNER_ADDRESS_LINE1 OWNER_ADDRESS_LINE2 OWNER_ADDRESS_LINE3 OWNER_ADDRESS_LINE4 OWNER_CITY OWNER_STATE OWNER_ZIPCODE OWNER_COUNTRY STREET_NUM STREET_HALF_NUM FULL_STREET_NAME BLDG_ID UNIT_ID PROPERTY_CITY PROPERTY_ZIPCODE MAPSCO NBHD_CD LEGAL1 LEGAL2 LEGAL3 LEGAL4 LEGAL5 DEED_TXFR_DATE GIS_PARCEL_ID PHONE_NUM LMA IMA'.split()
MULTI_FIELDS = 'APPRAISAL_YR ACCOUNT_NUM OWNER_SEQ_NUM OWNER_NAME OWNERSHIP_PCT'.split()
STREET_TYPES = {'ROAD':'RD','STREET':'ST','LANE':'LN','DRIVE':'DR','COURT':'CT','BOULEVARD':'BLVD','AVENUE':'AVE','CIRCLE':'CIR','TRAIL':'TRL','PLACE':'PL','PARKWAY':'PKWY','EXPRESSWAY':'EXPY','NORTH':'N','SOUTH':'S','EAST':'E','WEST':'W'}

def address_key(value):
    text = str(value or '').upper().replace('#', ' UNIT ')
    text = re.sub(r'\b(?:APT|APARTMENT|SUITE|STE)\b', 'UNIT', text)
    text = re.sub(r'\bTEXAS\b', 'TX', text)
    text = re.sub(r'\bEXPRESS\s+WAY\b', 'EXPY', text)
    text = re.sub(r'\b(\d{5})-\d{4}\b', r'\1', text)
    text = re.sub(r'\b(\d{5})\d{4}\b$', r'\1', text)
    words = re.sub(r'[^A-Z0-9/]+', ' ', text).split()
    words = [STREET_TYPES.get(word, word) for word in words]
    # Never match city-only titles or addresses without postal identity.
    if not words or not words[0][0].isdigit() or len(words)<5 or words[-2]!='TX' or not re.fullmatch(r'\d{5}',words[-1]):
        return None
    return ' '.join(words)

def situs(row):
    parts = [row['STREET_NUM'], row['STREET_HALF_NUM'], row['FULL_STREET_NAME']]
    if row['BLDG_ID']: parts += ['BLDG', row['BLDG_ID']]
    if row['UNIT_ID']: parts += ['UNIT', row['UNIT_ID']]
    # The district appends this county annotation to some municipality labels.
    city = re.sub(r'\s+\(DALLAS CO\)$', '', row['PROPERTY_CITY'])
    parts += [city, 'TX', row['PROPERTY_ZIPCODE']]
    return ' '.join(part.strip() for part in parts if part.strip())

def rows(z, name, headers):
    with z.open(name) as stream:
        reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', errors='strict', newline=''))
        if reader.fieldnames != headers: raise ValueError('Unreviewed appraisal schema')
        for row in reader:
            if None in row or any(value is None for value in row.values()): raise ValueError('Malformed appraisal row')
            yield {key:value.strip() for key,value in row.items()}

def match_archive(archive, records, appraisal_year):
    targets = {address_key(record['raw'].get('indexed_address')) for record in records}
    targets.discard(None)
    matched = {key:[] for key in targets}; count=0; account_ids=set()
    with zipfile.ZipFile(archive) as z:
        validate_zip(z)
        if 'ACCOUNT_INFO.CSV' not in z.namelist() or 'MULTI_OWNER.CSV' not in z.namelist(): raise ValueError('Missing current appraisal tables')
        for row in rows(z,'ACCOUNT_INFO.CSV',INFO_FIELDS):
            count+=1
            if count>2_000_000: raise ValueError('Appraisal row bound exceeded')
            # The official archive includes account IDs with a literal plus sign.
            if row['APPRAISAL_YR']!=str(appraisal_year) or not re.fullmatch(r'[A-Z0-9+]{1,30}',row['ACCOUNT_NUM']): raise ValueError('Appraisal identity/year mismatch')
            key=address_key(situs(row))
            if key not in targets: continue
            if row['ACCOUNT_NUM'] in account_ids: raise ValueError('Duplicate matching appraisal account')
            account_ids.add(row['ACCOUNT_NUM'])
            # Mailing addresses and phone fields are deliberately omitted from discovery output.
            excluded=row['EXCLUDE_OWNER'].upper() not in ('','N','NO','0')
            matched[key].append({'account_id':row['ACCOUNT_NUM'],'situs':situs(row),
                'owner_name':None if excluded else row['OWNER_NAME1'], 'additional_owner_name':None if excluded else row['OWNER_NAME2'],
                'owner_excluded':excluded,'legal_description':[row[f'LEGAL{i}'] for i in range(1,6)],
                'gis_parcel_id':row['GIS_PARCEL_ID'],'owners':[]})
        by_id={row['account_id']:row for group in matched.values() for row in group}
        multi_count=0
        for row in rows(z,'MULTI_OWNER.CSV',MULTI_FIELDS):
            multi_count+=1
            if multi_count>2_000_000 or row['APPRAISAL_YR']!=str(appraisal_year): raise ValueError('Multi-owner identity/year mismatch')
            account=by_id.get(row['ACCOUNT_NUM'])
            if account and not account['owner_excluded']:
                account['owners'].append({'name':row['OWNER_NAME'],'ownership_pct':row['OWNERSHIP_PCT']})
    result=[]
    for record in records:
        key=address_key(record['raw'].get('indexed_address')); candidates=matched.get(key,[]); holds=[]
        if key is None: holds.append('complete_index_address_missing')
        elif not candidates: holds.append('appraisal_situs_unmatched')
        elif len(candidates)>1: holds.append('ambiguous_appraisal_accounts')
        if any(row['owner_excluded'] for row in candidates): holds.append('appraisal_owner_excluded')
        # Every index match still needs the complete notice and independent legal/owner/current-sale evidence.
        result.append({'document_id':record['source_record_id'],'source_url':record['source_url'],
            'appraisal_candidates':candidates,'holds':holds,'identity_verified':False,'current_status_verified':False,'trace_eligible':False})
    return {'accounts_scanned':count,'notices':result}

def run(archive, download_receipt, index_manifest, output, day):
    stamp=date.fromisoformat(day);receipt=json.loads(Path(download_receipt).read_text());manifest=json.loads(Path(index_manifest).read_text())
    if receipt.get('source_page')!='https://www.dallascad.org/DataProducts.aspx' or receipt.get('sha256')!=file_hash(archive): raise ValueError('Unbound official archive')
    asof=date.fromisoformat(receipt['source_as_of'])
    if not 0<=(stamp-asof).days<=1: raise ValueError('Appraisal source is stale or future')
    if manifest.get('source_key')!='tx-dallas-pre_foreclosure' or manifest.get('records_sha256')!=digest(manifest.get('records')): raise ValueError('County inventory hash mismatch')
    records=manifest['records']
    if not 1<=len(records)<=500 or len({r['source_record_id'] for r in records})!=len(records): raise ValueError('Invalid county inventory')
    for record in records:
        if not re.fullmatch(r'\d{1,30}',record['source_record_id']) or record['source_url']!='https://dallas.tx.publicsearch.us/doc/'+record['source_record_id']: raise ValueError('Wrong county document')
    # Year is read from the reviewed public download link, not inferred from the calendar.
    link=receipt.get('download_url','');found=re.search(r'DCAD(\d{4})_CURRENT\.zip',link,re.I)
    if not found or not link.startswith('https://www.dallascad.org/ViewPDFs.aspx?'): raise ValueError('Unreviewed current-ownership link')
    result=match_archive(archive,records,int(found[1]))
    summary={'county':'Dallas','documents':len(records),'accounts_scanned':result['accounts_scanned'],
        'unique_situs_matches':sum(len(n['appraisal_candidates'])==1 for n in result['notices']),
        'exception_documents':sum(bool(n['holds']) for n in result['notices']),'trace_eligible':0}
    report={'processor':'dallas-appraisal-batch/1.0','processed_at':datetime.now(timezone.utc).isoformat(),'day':day,
        'source_as_of':receipt['source_as_of'],'archive_sha256':receipt['sha256'],'inventory_sha256':file_hash(index_manifest),
        'summary':summary,'notices':result['notices'],'verification_granted':False,'dispatch_authorized':False}
    output=Path(output);output.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=output/'report.json.tmp';temp.write_text(json.dumps(report,indent=2));temp.chmod(0o600);temp.replace(output/'report.json')
    packet={'processor':report['processor'],'run_id':manifest['run_id'],'batch_index':manifest['batch_index'],
        'records_sha256':manifest['records_sha256'],'archive_sha256':receipt['sha256'],'report_sha256':digest(report),
        'source_as_of':receipt['source_as_of'],'processed_at':report['processed_at'],
        'items':[{'document_id':n['document_id'],'match_count':len(n['appraisal_candidates']),'held':bool(n['holds'])} for n in result['notices']],
        'verification_granted':False,'dispatch_authorized':False,'outreach_authorized':False}
    temp=output/'receipt.json.tmp';temp.write_text(json.dumps(packet,indent=2));temp.chmod(0o600);temp.replace(output/'receipt.json')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','download_receipt','index_manifest','output','day'):p.add_argument(name)
    a=p.parse_args();print(json.dumps(run(a.archive,a.download_receipt,a.index_manifest,a.output,a.day)))

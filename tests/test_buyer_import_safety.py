import io
from tools.buyer_csv_parser import parse_buyer_csv


def test_contact_details_never_grant_import_consent():
    result=parse_buyer_csv(io.StringIO('Grantee,Property Address,Phone,Email\nQA LLC,100 Test St,2145550123,qa@example.test\n'))
    assert len(result.buyers)==1
    assert result.buyers[0]['phone']=='+12145550123'
    assert result.buyers[0]['sms_opt_in'] is False
    assert result.buyers[0]['email_opt_in'] is False


def test_group_ownership_is_from_parser_not_ambiguous_display_name_matching():
    result=parse_buyer_csv(io.StringIO('Grantee,Property Address\nQA LLC,100 Test St\nQA LLC,101 Test St\nOther LLC,102 Test St\n'))
    assert len(result.groups)==2
    assert result.groups[0]['buyer'] is result.buyers[0]
    assert [row['property_address'] for row in result.groups[0]['transactions']]==['100 Test St','101 Test St']
    assert [row['property_address'] for row in result.groups[1]['transactions']]==['102 Test St']


def test_duplicate_purchase_rows_do_not_inflate_new_buyer_signals():
    line='QA LLC,100 Test St,2026-10-01,100000\n'
    result=parse_buyer_csv(io.StringIO('Grantee,Property Address,Sale Date,Sale Price\n'+line+line))
    assert result.log['rows_imported']==2
    assert len(result.transactions)==2
    assert result.buyers[0]['properties_owned']==1
    assert result.buyers[0]['repeat_buyer'] is False


def test_missing_financing_information_is_not_cash_evidence():
    result=parse_buyer_csv(io.StringIO('Grantee,Property Address\nQA LLC,100 Test St\n'))
    assert result.buyers[0]['cash_buyer'] is False
    assert result.transactions[0]['cash_transaction'] is False


def test_negative_and_malformed_prices_are_not_converted_to_positive_values():
    for price in ['-$100000','(100000)','100abc','1.2.3','NaN']:
        result=parse_buyer_csv(io.StringIO('Grantee,Property Address,Sale Price\nQA LLC,100 Test St,'+price+'\n'))
        assert result.errors and result.buyers==[]

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('delivery_keychain',Path(__file__).parents[1]/'collectors/deliver_keychain.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class KeychainDeliveryTests(unittest.TestCase):
 def test_mixed_sources_never_read_credentials(self):
  with tempfile.TemporaryDirectory() as temp:
   for i,key in enumerate(['tx-dallas-tax_delinquent','tx-collin-tax_delinquent']):
    (Path(temp)/f'batch-{i:04}.json').write_text(json.dumps({'source_key':key}))
   with patch.object(module.subprocess,'run') as run:
    with self.assertRaises(ValueError):module.deliver(temp)
    run.assert_not_called()
 def test_missing_credential_never_dispatches(self):
  with tempfile.TemporaryDirectory() as temp:
   (Path(temp)/'batch-0000.json').write_text(json.dumps({'source_key':'tx-dallas-tax_delinquent'}))
   with patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')) as run:
    with self.assertRaises(RuntimeError):module.deliver(temp)
    self.assertEqual(run.call_count,1)
 def test_only_rehearsal_destination_and_secret_absent_from_arguments(self):
  with tempfile.TemporaryDirectory() as temp:
   (Path(temp)/'batch-0000.json').write_text(json.dumps({'source_key':'tx-dallas-tax_delinquent'}))
   with patch.object(module.subprocess,'run',side_effect=[SimpleNamespace(returncode=0,stdout='SYNTHETIC_TOKEN\n'),SimpleNamespace(returncode=0)]) as run:
    self.assertEqual(module.deliver(temp),0)
    args=run.call_args.args[0]
    self.assertEqual(args[-1],module.REHEARSAL_PROJECT)
    self.assertNotIn('SYNTHETIC_TOKEN',' '.join(args))
    self.assertEqual(run.call_args.kwargs['env']['INGEST_KEY_ID'],'tx-dallas-tax_delinquent')

if __name__=='__main__':unittest.main()

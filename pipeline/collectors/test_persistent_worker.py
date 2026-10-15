import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timedelta, timezone

spec = importlib.util.spec_from_file_location('worker', Path(__file__).with_name('persistent_worker.py'))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
NOW = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)

class WorkerTests(unittest.TestCase):
    def test_restart_does_not_recollect_or_redeliver_accepted_jobs(self):
        with TemporaryDirectory() as tmp:
            calls=[]
            def collect(c,p): p.mkdir(parents=True);calls.append(('collect',c))
            def send(p): calls.append(('send',p.name))
            w.tick(tmp,NOW,collect,send);w.tick(tmp,NOW+timedelta(minutes=1),collect,send)
            self.assertEqual(len(calls),4)
            self.assertEqual(len(w.tick(tmp,NOW,collect,send)['exceptions']),0)

    def test_uncertain_delivery_is_held_without_automatic_retries(self):
        with TemporaryDirectory() as tmp:
            paths=[];collections=[]
            def collect(c,p): p.mkdir(parents=True);collections.append(c)
            def send(p): paths.append(str(p));raise RuntimeError('secret must not be logged')
            w.tick(tmp,NOW,collect,send)
            w.tick(tmp,NOW+timedelta(minutes=6),collect,send)
            result=w.tick(tmp,NOW+timedelta(minutes=17),collect,send)
            self.assertEqual(len(collections),2);self.assertEqual(len(paths),2)
            self.assertEqual(len(result['exceptions']),2)
            self.assertNotIn('secret',Path(tmp,'status.json').read_text())
            w.tick(tmp,NOW+timedelta(hours=1),collect,send);self.assertEqual(len(paths),2)

    def test_crash_in_collection_holds_incomplete_files(self):
        with TemporaryDirectory() as tmp:
            db=w.connect(Path(tmp));db.execute("INSERT INTO jobs VALUES('2026-10-14','Dallas','collecting',0,0,NULL)");db.commit();db.close()
            collected=[]
            result=w.tick(tmp,NOW,lambda c,p:collected.append(c),lambda p:None)
            self.assertEqual(collected,['Collin'])
            self.assertEqual(result['exceptions'][0]['reason'],'collection_interrupted')

    def test_chicago_schedule_and_next_day(self):
        with TemporaryDirectory() as tmp:
            before=NOW.replace(hour=10)
            self.assertEqual(w.tick(tmp,before)['jobs'],[])
            calls=[]
            collect=lambda c,p:calls.append(c)
            w.tick(tmp,NOW,collect,lambda p:None)
            result=w.tick(tmp,NOW+timedelta(days=1),collect,lambda p:None)
            self.assertEqual(len(calls),4);self.assertEqual(len(result['jobs']),4)

if __name__=='__main__': unittest.main()

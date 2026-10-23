import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import {coverageSchema, coverageErrors as reconcile} from '../../frontend/supabase/functions/daily-list-ingest/coverage.mjs';
const ajv = new Ajv({allErrors:true,strict:true});
addFormats(ajv);
const validate = ajv.compile(coverageSchema);
export const coverageErrors = (p,c,url,now) => reconcile(p,c,url,now,validate);

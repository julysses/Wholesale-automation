import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import Ajv from 'ajv';
const read = name => JSON.parse(readFileSync(new URL(`../../config/acquisition/inbound/${name}`, import.meta.url), 'utf8'));
const tools = read('tools.draft.json');
const cases = read('tool-contract-cases.json');
const ajv = new Ajv({ allErrors: true, strict: true });
const schemas = new Map(tools.map(tool => [tool.name, ajv.compile(tool.parameters)]));
for (const scenario of cases) {
  test(`inbound tool contract: ${scenario.id}`, () => {
    const validate = schemas.get(scenario.name);
    assert.ok(validate);
    assert.equal(validate(scenario.args), scenario.valid, JSON.stringify(validate.errors));
  });
}
test('review draft has no real target, extra capability, provider credentials or automatic retry', () => {
  assert.deepEqual(tools.map(t => t.name).sort(), ['lookup_property', 'record_contact_restriction', 'request_callback', 'request_human', 'submit_seller_intake']);
  for (const tool of tools) {
    assert.equal(tool.type, 'custom');
    assert.equal(new URL(tool.url).hostname, 'acquisition.example.invalid');
    assert.equal(new URL(tool.url).pathname, '/webhooks/retell/acquisition/tools');
    assert.equal(tool.method, 'POST');
    assert.equal(tool.args_at_root, false);
    assert.equal(tool.max_retry, 0);
    assert.equal(tool.timeout_ms, 15000);
    assert.equal(tool.parameters.additionalProperties, false);
    assert.equal(tool.headers, undefined);
    assert.equal(tool.query_params, undefined);
  }
});

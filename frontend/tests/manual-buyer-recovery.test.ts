import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({ api: vi.fn(), actor: '00000000-0000-4000-8000-000000000001' }));
vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), apiFetch: state.api }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { user: { id: state.actor } } }, error: null }) } } }));
import { ApiError } from '@/lib/api';
import { createManualBuyer, pendingManualBuyer, recoverManualBuyer } from '@/lib/manualBuyer';

const buyer = { first_name: 'Synthetic', last_name: 'Buyer', min_price: 0, max_price: 250000 };
const onPending = vi.fn();
const saved = (id: string, current_exists = true) => ({ id, state: 'saved', saved: true, buyer_id: id, current_exists,
  buyer: { id, first_name: buyer.first_name, last_name: buyer.last_name, sms_opt_in: false, email_opt_in: false } });
const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear(); state.actor = '00000000-0000-4000-8000-000000000001';
  state.api.mockImplementation(async (_path, init) => response(saved(JSON.parse(init.body).request_id)));
});
afterEach(() => vi.restoreAllMocks());

it('persists a stable draft before POST and sends no consent flags', async () => {
  state.api.mockImplementationOnce(async (_path, init) => {
    const posted = JSON.parse(init.body); const draft = await pendingManualBuyer();
    expect(draft?.request_id).toBe(posted.request_id);
    expect(posted.buyer.min_price).toBe(0);
    expect(posted.buyer).not.toHaveProperty('sms_opt_in');
    expect(posted.buyer).not.toHaveProperty('email_opt_in');
    return response(saved(posted.request_id));
  });
  expect((await createManualBuyer(buyer, onPending)).saved).toBe(true);
  expect(await pendingManualBuyer()).toBeNull();
});

it('recovers an unknown save by resending exactly the same reference and original data', async () => {
  state.api.mockRejectedValueOnce(new Error('lost response'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow('lost response');
  const first = state.api.mock.calls[0][1].body;
  await expect(createManualBuyer({ ...buyer, company: 'changed' }, onPending)).rejects.toThrow('original save');
  expect(state.api).toHaveBeenCalledTimes(1);
  await createManualBuyer((await pendingManualBuyer())!.buyer, onPending);
  expect(state.api.mock.calls[1][1].body).toBe(first);
  expect(await pendingManualBuyer()).toBeNull();
});

it('checks a retained saved receipt without repeating a write, including a deleted buyer', async () => {
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const draft = (await pendingManualBuyer())!;
  state.api.mockResolvedValueOnce(response(saved(draft.request_id, false)));
  expect((await recoverManualBuyer(false, onPending))?.current_exists).toBe(false);
  expect(state.api.mock.calls[1]).toEqual([`/api/buyers/manual/${draft.request_id}`, undefined]);
  expect(await pendingManualBuyer()).toBeNull();
});

it('keeps the reference and original details when a read has no confirmed result', async () => {
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const draft = (await pendingManualBuyer())!;
  state.api.mockResolvedValueOnce(response({ id: draft.request_id, state: 'pending', saved: false }));
  expect((await recoverManualBuyer(false, onPending))?.state).toBe('pending');
  expect(await pendingManualBuyer()).toEqual(draft);
});

it('releases a reference only after durable cancellation is acknowledged', async () => {
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const draft = (await pendingManualBuyer())!;
  state.api.mockRejectedValueOnce(new Error('cancel unconfirmed'));
  await expect(recoverManualBuyer(true, onPending)).rejects.toThrow('cancel unconfirmed');
  expect(await pendingManualBuyer()).toEqual(draft);
  state.api.mockResolvedValueOnce(response({ id: draft.request_id, state: 'canceled', saved: false }));
  await recoverManualBuyer(true, onPending);
  expect(state.api.mock.calls[2]).toEqual([`/api/buyers/manual/${draft.request_id}/cancel`, { method: 'POST' }]);
  expect(await pendingManualBuyer()).toBeNull();
});

it('recovers a committed save instead of deleting it when stopping loses the race', async () => {
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const draft = (await pendingManualBuyer())!;
  state.api.mockResolvedValueOnce(response(saved(draft.request_id)));
  expect((await recoverManualBuyer(true, onPending))?.saved).toBe(true);
  expect(state.api.mock.calls.every(([, init]) => init?.method !== 'DELETE')).toBe(true);
});

it.each(['wrong-id', 'consent-true', 'missing-buyer'])('holds an uncertain receipt (%s)', async variant => {
  state.api.mockImplementationOnce(async (_path, init) => {
    const value = saved(JSON.parse(init.body).request_id);
    if (variant === 'wrong-id') value.id = '00000000-0000-4000-8000-000000000099';
    if (variant === 'consent-true') value.buyer.sms_opt_in = true;
    if (variant === 'missing-buyer') return response({ ...value, buyer: null });
    return response(value);
  });
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  expect(await pendingManualBuyer()).not.toBeNull();
});

it('does not send if durable browser recovery storage is unavailable', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable'); });
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow('storage unavailable');
  expect(state.api).not.toHaveBeenCalled();
});

it('does not expose another signed-in operator draft', async () => {
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const original = await pendingManualBuyer();
  state.actor = '00000000-0000-4000-8000-000000000002';
  expect(await pendingManualBuyer()).toBeNull();
  state.actor = '00000000-0000-4000-8000-000000000001';
  expect(await pendingManualBuyer()).toEqual(original);
});

it('permits correction after a fresh 422, but a later 422 cannot disprove an earlier save', async () => {
  state.api.mockRejectedValueOnce(new ApiError('invalid', 422));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow('invalid');
  expect(await pendingManualBuyer()).toBeNull();
  state.api.mockRejectedValueOnce(new Error('lost'));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  const draft = await pendingManualBuyer();
  state.api.mockRejectedValueOnce(new ApiError('later validation', 422));
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow('later validation');
  expect(await pendingManualBuyer()).toEqual(draft);
});

it('rejects invalid recovery data, nonfinite money and invented consent before writing', async () => {
  await expect(createManualBuyer({ ...buyer, min_price: NaN }, onPending)).rejects.toThrow();
  await expect(createManualBuyer({ ...buyer, sms_opt_in: true }, onPending)).rejects.toThrow();
  sessionStorage.setItem(`hilltop.pending-manual-buyer.v1.${state.actor}`, '{broken');
  await expect(createManualBuyer(buyer, onPending)).rejects.toThrow();
  expect(state.api).not.toHaveBeenCalled();
});

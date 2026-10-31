import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SellerChallenge } from './SellerChallenge';
afterEach(() => { cleanup(); delete window.turnstile; });
it('binds verification to inquiry, clears expired token, and removes obsolete widget', async () => {
  const renderWidget = vi.fn<(element: HTMLElement, options: Record<string, unknown>) => string>().mockReturnValue('widget-1'); const remove = vi.fn(); const onToken = vi.fn();
  window.turnstile = { render: renderWidget, remove };
  const view = render(<SellerChallenge siteKey="public-key" inquiryId="synthetic-id" onToken={onToken} />);
  await waitFor(() => expect(renderWidget).toHaveBeenCalledTimes(1));
  const options = renderWidget.mock.calls[0]![1] as Record<string, unknown>;
  expect(options.action).toBe('acquisition_offer'); expect(options.cData).toBe('synthetic-id');
  act(() => (options.callback as (token: string) => void)('verified-token'));
  expect(onToken).toHaveBeenLastCalledWith('verified-token');
  act(() => (options['expired-callback'] as () => void)());
  expect(onToken).toHaveBeenLastCalledWith(null);
  view.unmount(); expect(remove).toHaveBeenCalledWith('widget-1');
  act(() => (options.callback as (token: string) => void)('stale-token'));
  expect(onToken).toHaveBeenLastCalledWith(null);
});

import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AppointmentBookingDialog } from '../src/components/appointments/AppointmentBookingDialog';
import { AppointmentActions } from '../src/components/appointments/AppointmentActions';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('../src/lib/api', () => ({ apiFetch: mocks.api }));
beforeEach(() => { mocks.api.mockReset(); });
afterEach(cleanup);
const reply = (data: unknown) => ({ json: async () => data });
const props = { leadId: 'lead-test', address: 'Controlled property', onClose: vi.fn(), onSaved: vi.fn() };
function fill() {
  fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2099-01-02' } });
  fireEvent.change(screen.getByLabelText('Appointment time'), { target: { value: '10:00' } });
}
test('uncertain booking locks details and retries the same durable reference', async () => {
  mocks.api.mockRejectedValueOnce(new Error('Acknowledgement lost')).mockResolvedValueOnce(reply({ id: 'saved', calendar_sync: 'not_supported' }));
  render(<AppointmentBookingDialog {...props} />); fill();
  fireEvent.click(screen.getByRole('button', { name: 'Save appointment' }));
  await screen.findByText(/Acknowledgement lost/);
  expect(screen.getByLabelText('Appointment date')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry same booking' }));
  await screen.findByText(/Appointment saved/);
  expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual(JSON.parse(mocks.api.mock.calls[1][1].body));
  expect(screen.getByText(/Add this booking to your calendar manually/)).toBeInTheDocument();
});
test('rapid clicks send only one booking while acknowledgement is pending', async () => {
  let finish!: (value: unknown) => void;
  mocks.api.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<AppointmentBookingDialog {...props} />); fill();
  const button = screen.getByRole('button', { name: 'Save appointment' });
  fireEvent.click(button); fireEvent.click(button);
  expect(mocks.api).toHaveBeenCalledTimes(1);
  finish(reply({ id: 'saved', calendar_sync: 'not_configured' }));
  await screen.findByText(/Appointment saved/);
});
test('past dates do not submit an appointment', async () => {
  render(<AppointmentBookingDialog {...props} />);
  fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2000-01-01' } });
  fireEvent.change(screen.getByLabelText('Appointment time'), { target: { value: '10:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save appointment' }));
  await screen.findByText('Choose a future date and time.');
  expect(mocks.api).not.toHaveBeenCalled();
});
test('future appointments cannot be marked completed or no-show', () => {
  render(<AppointmentActions appointment={{ id: 'appt', status: 'scheduled', scheduled_at: '2099-01-01T10:00:00Z' }} onSaved={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Complete' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'No-show' })).toBeDisabled();
});
test('stale status failure stays visible and never reports a successful update', async () => {
  const saved = vi.fn(); mocks.api.mockRejectedValue(new Error('Booking status changed. Refresh.'));
  render(<AppointmentActions appointment={{ id: 'appt', status: 'scheduled', scheduled_at: '2000-01-01T10:00:00Z' }} onSaved={saved} />);
  fireEvent.click(screen.getByRole('button', { name: 'Complete' }));
  await screen.findByRole('alert'); expect(saved).not.toHaveBeenCalled();
  expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual({ expected_status: 'scheduled', status: 'completed' });
});

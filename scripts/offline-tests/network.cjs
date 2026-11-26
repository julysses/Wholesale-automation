// Loaded before the test runner and inherited by Node child processes.
const net = require('node:net');
const dgram = require('node:dgram');
const deny = () => { throw new Error('Offline test boundary: mock all network providers'); };
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  // Only the dedicated disposable-cluster runner sets this exact target.
  const raw = process.env.SMS_TEST_ADMIN_URL;
  if (process.env.WHOLESALE_LOCAL_POSTGRES === '1' && raw) {
    const target = new URL(raw);
    if (target.hostname === '127.0.0.1' && target.pathname === '/wholesale_sms_test'
        && args[1] === target.hostname && String(args[0]) === target.port) {
      return connect.apply(this, args);
    }
  }
  return deny();
};
dgram.Socket.prototype.connect = deny;
dgram.Socket.prototype.send = deny;
globalThis.fetch = deny;

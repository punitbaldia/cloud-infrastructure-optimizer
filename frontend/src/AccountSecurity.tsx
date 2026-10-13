import { useState, type FormEvent } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api } from './api';

export default function AccountSecurity() {
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [changed, setChanged] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (password !== confirmation) {
      setError('The new passwords do not match.');
      return;
    }
    if (password === current) {
      setError('Choose a different new password.');
      return;
    }
    setBusy(true);
    try {
      await api('/auth/password', 'POST', { current_password: current, new_password: password });
      sessionStorage.removeItem('cloudwise-token');
      setCurrent('');
      setPassword('');
      setConfirmation('');
      setChanged(true);
      // The parent clears cached authenticated data and returns to the login screen.
      sessionStorage.setItem('cloudwise-notice', 'Password changed. Sign in with your new password.');
      window.dispatchEvent(new Event('auth-expired'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the password.');
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel padded">
    <h2><ShieldCheck size={19} className="security-icon"/> Account security</h2>
    <p className="muted">Choose a personal password. Changing it signs out every active session.</p>
    <form onSubmit={submit} className="password-form">
      <label>Current password
        <input type="password" autoComplete="current-password" required maxLength={200}
          value={current} onChange={e => setCurrent(e.target.value)}/>
      </label>
      <label>New password
        <input type="password" autoComplete="new-password" required minLength={12} maxLength={200}
          aria-describedby="password-help" value={password} onChange={e => setPassword(e.target.value)}/>
      </label>
      <label>Confirm new password
        <input type="password" autoComplete="new-password" required minLength={12} maxLength={200}
          value={confirmation} onChange={e => setConfirmation(e.target.value)}/>
      </label>
      <p id="password-help" className="muted">Use at least 12 characters. Your new password replaces the original setup password.</p>
      {error && <div role="alert" className="error">{error}</div>}
      {changed && <p role="status">Password changed. Sign in again.</p>}
      <button type="submit" className="primary" disabled={busy}>
        {busy ? 'Changing password…' : 'Change password'}
      </button>
    </form>
  </section>;
}

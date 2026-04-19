import { useState } from 'react';
import { api, ApiError } from '../api';

export function LoginView({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      await api.post('/api/auth/login', { password });
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--bg-base)',
    }}>
      <form onSubmit={submit} style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 8, padding: 32, width: 360,
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700,
          letterSpacing: 'var(--tracking-tight)',
        }}>
          Unit3<span style={{ color: 'var(--blue)' }}>Dup</span>
        </div>
        <div style={{
          fontSize: 12, color: 'var(--fg-3)',
          fontFamily: 'var(--font-mono)',
        }}>Enter password to continue</div>
        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '10px 12px', fontSize: 13,
            color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
          }}
        />
        {error && (
          <div style={{
            fontSize: 12, color: 'var(--red)',
            fontFamily: 'var(--font-mono)',
          }}>{error}</div>
        )}
        <button
          type="submit"
          disabled={!password || loading}
          style={{
            background: password && !loading ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: '#fff', padding: '10px 14px',
            borderRadius: 6, fontSize: 13, fontWeight: 600,
            cursor: password && !loading ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >{loading ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  );
}

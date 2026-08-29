/**
 * Who is signed in, and the Google button that changes it.
 *
 * Google Identity Services is loaded from a script tag rather than bundled,
 * because Google requires it to be served from their origin — a vendored copy
 * stops working when they rotate keys or change the flow. Loaded lazily, so a
 * deployment with no client id configured never fetches it at all.
 *
 * The credential Google hands back is posted straight to the backend and
 * nothing is trusted from it here. The frontend cannot verify a signature, so
 * anything it read out of that token would be a guess presented as a fact; the
 * identity rendered in the header comes back from `/auth/me` after the server
 * has checked it.
 */

import { useCallback, useEffect, useState } from 'react';

import { auth, AuthConfig, Identity } from '@/lib/api';

const GSI_SRC = 'https://accounts.google.com/gsi/client';

const SIGNED_OUT: Identity = { signed_in: false, email: '', name: '', picture: '' };

function loadGsi(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if (document.querySelector(`script[src="${GSI_SRC}"]`)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = GSI_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Google sign-in could not be loaded'));
    document.head.appendChild(script);
  });
}

export function useAuth() {
  const [identity, setIdentity] = useState<Identity>(SIGNED_OUT);
  const [config, setConfig] = useState<AuthConfig>({ enabled: false, client_id: '' });
  /*
   * `loading` starts true so the header does not flash "Sign in" at someone who
   * is already signed in. One frame of the wrong answer is worse here than a
   * moment of nothing, because it invites a pointless click.
   */
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cfg, me] = await Promise.all([auth.config(), auth.me()]);
        if (cancelled) return;
        setConfig(cfg);
        setIdentity(me);
      } catch {
        // A backend that cannot answer leaves this signed out. Sign-in is not
        // required to use the app, so failing quietly is right.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async () => {
    if (!config.enabled) return;
    await loadGsi();
    const google = (window as unknown as { google?: any }).google;
    if (!google) return;

    google.accounts.id.initialize({
      client_id: config.client_id,
      callback: async (response: { credential: string }) => {
        const me = await auth.signIn(response.credential);
        setIdentity(me);
      },
    });
    google.accounts.id.prompt();
  }, [config]);

  const signOut = useCallback(async () => {
    await auth.signOut();
    setIdentity(SIGNED_OUT);
    const google = (window as unknown as { google?: any }).google;
    // Without this Google re-offers the same account silently on the next
    // prompt, so "sign out" would not let someone switch accounts.
    google?.accounts?.id?.disableAutoSelect?.();
  }, []);

  return { identity, config, loading, signIn, signOut };
}

export default useAuth;

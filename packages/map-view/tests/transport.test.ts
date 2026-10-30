import { describe, expect, it, vi } from 'vitest';
import { createTransport, HttpTransport, PostMessageTransport, RemoteError } from '../src/transport';
import en from '../src/i18n/en.json';
import ko from '../src/i18n/ko.json';

describe('transports', () => {
  it('HTTP sends the token header and unwraps results and errors', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: async () => ({ result: { ok: 1 } }) })
      .mockResolvedValueOnce({ json: async () => ({ error: { code: -32002, message: 'not git' } }) });
    vi.stubGlobal('fetch', fetchMock);
    const t = new HttpTransport('tok');
    expect(await t.call('diff.count', { since: 'HEAD' })).toEqual({ ok: 1 });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/diff.count');
    expect(fetchMock.mock.calls[0][1].headers['X-Thrubase-Token']).toBe('tok');
    await expect(t.call('diff.count')).rejects.toMatchObject({ code: -32002 });
    vi.unstubAllGlobals();
  });

  it('postMessage pairs responses with requests and relays host events', async () => {
    const posted: any[] = [];
    const t = new PostMessageTransport({ postMessage: (m) => posted.push(m), getState: () => null, setState: () => {} }, window);
    const p = t.call('trail.current');
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'response', id: posted[0].id, result: 42 } }));
    expect(await p).toBe(42);
    const q = t.call('map.build');
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'response', id: posted[1].id, error: { code: -32001, message: 'x' } } }));
    await expect(q).rejects.toBeInstanceOf(RemoteError);
    const onLocate = vi.fn();
    t.listen({ onLocate });
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'locate', file: 'a.py', line: 7 } }));
    expect(onLocate).toHaveBeenCalledWith('a.py', 7);
  });

  it('createTransport keeps the token out of the address bar', () => {
    window.history.replaceState(null, '', '/?token=abc');
    const t = createTransport(window);
    expect(t.host).toBe('web');
    expect(window.location.search).toBe('');
    expect(window.sessionStorage.getItem('thrubase-token')).toBe('abc');
  });

  it('UI strings exist in both languages', () => {
    expect(Object.keys(ko).sort()).toEqual(Object.keys(en).sort());
  });
});

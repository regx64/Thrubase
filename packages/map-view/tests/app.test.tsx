import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../src/App';
import { FakeCore } from './fake';

async function startClimb(core: FakeCore) {
  render(<App transport={core} />);
  await screen.findByRole('button', { name: /Start climb/ });
  fireEvent.click(screen.getByRole('button', { name: /Start climb/ }));
  await screen.findByText('Question 1?');
}

describe('App', () => {
  it('climbs to the summit through every checkpoint state', async () => {
    const core = new FakeCore('web');
    await startClimb(core);
    // Segment 1: wrong then right -> hint, passed.
    fireEvent.click(screen.getByRole('radio', { name: /main_b/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await screen.findByText('Look again at lines 10–15.');
    fireEvent.click(screen.getByRole('radio', { name: /main_a/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await screen.findByText('Because.');
    expect(screen.getAllByText('Passed').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    // Segment 2: locate by clicking a line number in the code (web).
    await screen.findByText('Question 2?');
    await screen.findByRole('button', { name: 'Line 22' });
    fireEvent.click(screen.getByRole('button', { name: 'Line 22' }));
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await screen.findByText('Because.');
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    // Segment 3: wrong twice -> revealed (Unsure).
    await screen.findByText('Question 3?');
    for (let i = 0; i < 2; i++) {
      fireEvent.click(screen.getByRole('radio', { name: /run_a/ }));
      fireEvent.click(screen.getByRole('button', { name: 'Check' }));
      await waitFor(() => expect(core.attempts['t1:3:s']).toBe(i + 1));
    }
    await screen.findByText('Because.');
    expect(screen.getAllByText('Unsure').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    // Detours are optional: the summit comes next.
    await screen.findByText('Summit reached');
    expect(screen.getByText('Worth another look')).toBeInTheDocument();
    expect(document.querySelector('.tb-review')?.textContent).toContain('run');
  });

  it('skip moves on and is reviewed at the summit', async () => {
    const core = new FakeCore('web');
    await startClimb(core);
    for (const q of ['Question 1?', 'Question 2?', 'Question 3?']) {
      await screen.findByText(q);
      fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    }
    await screen.findByText('Summit reached');
    expect(screen.getAllByText('Skipped').length).toBe(3);
  });

  it('answers locate questions from editor clicks in VS Code', async () => {
    const core = new FakeCore('vscode');
    await startClimb(core);
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await screen.findByText('Question 2?');
    expect(screen.getByText('Click the line in the editor')).toBeInTheDocument();
    expect(document.querySelector('.tb-code')).toBeNull();
    act(() => core.events.forEach((e) => e.onLocate?.('app/m2.py', 22)));
    await screen.findByText('Because.');
    expect(core.calls.some(([m, p]) => m === 'checkpoint.answer' && p.answer === 22)).toBe(true);
    // The evidence opens in the editor.
    expect(core.opened.at(-1)).toEqual(['app/m2.py', 10]);
  });

  it('shows the no-changes notice for a diff climb without changes', async () => {
    const core = new FakeCore('web');
    core.diffError = -32003;
    render(<App transport={core} />);
    await screen.findByRole('button', { name: /Start climb/ });
    fireEvent.click(screen.getByRole('tab', { name: 'Diff climb' }));
    fireEvent.click(screen.getByRole('button', { name: /Start climb/ }));
    await screen.findByText('No changes to climb');
  });

  it('switches between English and Korean', async () => {
    const core = new FakeCore('web');
    render(<App transport={core} />);
    await screen.findByRole('button', { name: /Start climb/ });
    fireEvent.click(screen.getByRole('button', { name: 'Language' }));
    await screen.findByRole('button', { name: /등반 시작/ });
    expect(screen.getByRole('tab', { name: '변경 등반' })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('ko');
  });

  it('starts a diff climb when the host asks (status bar)', async () => {
    const core = new FakeCore('vscode');
    render(<App transport={core} />);
    await screen.findByRole('button', { name: /Start climb/ });
    act(() => core.events.forEach((e) => e.onStartClimb?.('diff')));
    await screen.findByText('Question 1?');
    expect(core.calls.some(([m, p]) => m === 'trail.build' && p.kind === 'diff')).toBe(true);
  });
});

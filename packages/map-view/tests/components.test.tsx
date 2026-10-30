import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SegmentCard } from '../src/climb/SegmentCard';
import { Summit } from '../src/climb/Summit';
import { TrailList } from '../src/climb/TrailList';
import { computeContours, TerrainMap } from '../src/terrain/TerrainMap';
import { EmptyState, StatusBadge, StatusBarItem, Tabs, TextInput, Tooltip } from '../src/ui';

describe('TrailList', () => {
  it('numbers main segments, indents detours and marks the current row', () => {
    const onSelect = vi.fn();
    render(
      <TrailList
        current={2}
        onSelect={onSelect}
        segments={[
          { order: 1, title: 'main', file: 'a.py', status: 'passed' },
          { order: 2, title: 'load', file: 'b.py' },
          { order: 3, title: 'side', file: 'c.py', detour: true },
          { order: 4, title: 'run', file: 'd.py', status: 'weak' },
        ]}
      />,
    );
    const rows = screen.getAllByRole('button');
    expect(rows[1]).toHaveAttribute('aria-current', 'step');
    expect(rows[2].textContent).toContain('detour');
    expect(rows[3].textContent).toContain('3');
    expect(screen.getByRole('img', { name: 'Unsure' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Passed' })).toBeInTheDocument();
    fireEvent.click(rows[3]);
    expect(onSelect).toHaveBeenCalledWith(4);
  });
});

describe('SegmentCard', () => {
  it('shows code with highlighted lines and clickable line numbers (web)', () => {
    const onLineClick = vi.fn();
    render(
      <SegmentCard order={1} total={12} title="main" file="a.py" lines={[3, 4]} guide={null} code={'a\nb\nc'} startLine={2}
        highlight={[3, 4]} onLineClick={onLineClick} />,
    );
    expect(screen.getByText(/Add an LLM key/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Line 3' }));
    expect(onLineClick).toHaveBeenCalledWith(3);
    expect(document.querySelectorAll('.tb-code-hl')).toHaveLength(2);
    expect(document.querySelector('.tb-guide-nokey')?.className).not.toContain('danger');
  });

  it('omits code in VS Code and shows a guide when there is one', () => {
    render(<SegmentCard order={2} total={12} title="load" file="b.py" lines={[1, 9]} guide="Watch the loop." />);
    expect(screen.getByText('Watch the loop.')).toBeInTheDocument();
    expect(document.querySelector('.tb-code')).toBeNull();
  });
});

describe('basic components', () => {
  it('StatusBadge pairs icon and word', () => {
    render(<><StatusBadge status="skipped" /><StatusBadge status="current" lang="ko" /></>);
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    expect(screen.getByText('현재')).toBeInTheDocument();
    expect(document.querySelector('.tb-icon-debug-step-over')).not.toBeNull();
  });

  it('Tabs switch with clicks and arrow keys', () => {
    const onChange = vi.fn();
    render(<Tabs items={[{ id: 'full', label: 'Full climb' }, { id: 'diff', label: 'Diff climb' }]} onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Full climb' }), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('diff');
    expect(screen.getByRole('tab', { name: 'Diff climb' })).toHaveAttribute('aria-selected', 'true');
  });

  it('TextInput errors are a sentence with an icon, not color alone', () => {
    render(<TextInput label="Endpoint" error="Could not reach this endpoint." />);
    expect(screen.getByLabelText('Endpoint')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Could not reach this endpoint.')).toBeInTheDocument();
    expect(document.querySelector('.tb-field-note-error .tb-icon-warning')).not.toBeNull();
  });

  it('Tooltip opens on focus', () => {
    render(<Tooltip text="src/app/very/long/path.py"><button type="button">path</button></Tooltip>);
    expect(screen.getByRole('tooltip', { hidden: true })).not.toBeVisible();
    fireEvent.focus(screen.getByRole('button'));
    expect(screen.getByRole('tooltip')).toBeVisible();
  });

  it('EmptyState variants', () => {
    render(<EmptyState variant="analyzing" title="Building the terrain map" body="Reading 214 Python files. Nothing is run." />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(document.querySelector('.tb-icon-spin')).not.toBeNull();
  });

  it('StatusBarItem copy', () => {
    render(<StatusBarItem count={7} />);
    expect(screen.getByRole('button')).toHaveTextContent('Climb 7 changes');
    expect(screen.getByRole('button')).toHaveAttribute('title', 'Thrubase: climb the uncommitted changes');
  });

  it('Summit lists what is worth another look', () => {
    const onOpen = vi.fn();
    render(<Summit review={[{ order: 3, title: 'run', file: 'r.py', line: 4, status: 'weak' }]} onOpen={onOpen} />);
    expect(screen.getByText('Summit reached')).toBeInTheDocument();
    fireEvent.click(screen.getByText('run'));
    expect(onOpen).toHaveBeenCalledWith(3);
  });
});

describe('TerrainMap', () => {
  it('renders an accessible canvas and computes contours', () => {
    const nodes = Array.from({ length: 30 }, (_, i) => ({ id: `n${i}`, x: 0.3 + (i % 5) * 0.08, y: 0.3 + Math.floor(i / 5) * 0.08, h: (i % 7) / 6 }));
    render(<TerrainMap nodes={nodes} trail={['n1', 'n2']} label="Terrain map of demo" width={300} height={200} />);
    expect(screen.getByRole('img', { name: 'Terrain map of demo' })).toBeInTheDocument();
    const contours = computeContours(nodes);
    expect(contours.length).toBeGreaterThan(0);
    expect(contours.length).toBeLessThanOrEqual(6);
  });
});

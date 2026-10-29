import { contourDensity } from 'd3-contour';
import { select } from 'd3-selection';
import { zoom as d3zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3-zoom';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import type { Status } from '../types';

export interface TerrainNode {
  id: string;
  label?: string;
  x: number;
  y: number;
  /** altitude 0..1 */
  h?: number;
  role?: 'entry' | 'summit' | 'isolated';
  status?: Status;
  /** shown on hover */
  file?: string;
}

export interface TerrainMapProps {
  nodes: TerrainNode[];
  /** node ids in climbing order */
  trail?: string[];
  /** number of trail legs already passed */
  passedUntil?: number;
  current?: string;
  width?: number;
  height?: number;
  label?: string;
  onNodeClick?: (node: TerrainNode) => void;
  /** smaller labels and no legend (VS Code sidebar) */
  compact?: boolean;
}

const CONTOUR_STEPS = [0.07, 0.11, 0.16, 0.22, 0.3, 0.4];
const GRID = 200;
const MARGIN = 24;

interface Palette {
  ink: string;
  inkMuted: string;
  accent: string;
  weak: string;
  sunken: string;
  font: string;
}

function readPalette(el: HTMLElement): Palette {
  const css = getComputedStyle(el);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    ink: v('--ink', '#1d1d22'),
    inkMuted: v('--ink-muted', '#5c5c68'),
    accent: v('--accent', '#1e3a8a'),
    weak: v('--weak', '#8a5b00'),
    sunken: v('--surface-sunken', '#f5f5f7'),
    font: v('--font-mono', 'monospace'),
  };
}

type Ring = [number, number][];

/** Contours weighted by altitude, outermost (contour-1) first, in unit coordinates. */
export function computeContours(nodes: TerrainNode[]): Ring[][][] {
  const pts = nodes.filter((n) => (n.h ?? 0) > 0.05);
  if (pts.length < 3) return [];
  const density = contourDensity<TerrainNode>()
    .x((d) => d.x * GRID)
    .y((d) => d.y * GRID)
    .weight((d) => (d.h ?? 0) ** 2)
    .size([GRID, GRID])
    .cellSize(2)
    .bandwidth(GRID * 0.035);
  const contours = density(pts);
  if (!contours.length) return [];
  const max = Math.max(...contours.map((c) => c.value));
  const levels = CONTOUR_STEPS.map((_, i) => max * ((i + 1) / (CONTOUR_STEPS.length + 1)));
  const byLevel = density.thresholds(levels)(pts);
  return byLevel.slice(0, CONTOUR_STEPS.length).map((c) =>
    c.coordinates.map((poly) => poly.map((ring) => ring.map(([x, y]) => [x / GRID, y / GRID] as [number, number]))),
  );
}

const reducedMotion = () =>
  typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function TerrainMap({
  nodes, trail = [], passedUntil = 0, current, width, height, label, onNodeClick, compact,
}: TerrainMapProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: width ?? 640, h: height ?? 420 });
  const [hover, setHover] = useState<{ node: TerrainNode; x: number; y: number } | null>(null);
  const view = useRef({ k: 1, x: 0, y: 0 });
  const target = useRef({ k: 1, x: 0, y: 0 });
  const velocity = useRef({ k: 0, x: 0, y: 0 });
  const frame = useRef(0);
  const zoomRef = useRef<ZoomBehavior<HTMLCanvasElement, unknown>>();
  const contours = useMemo(() => computeContours(nodes), [nodes]);
  const index = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  useEffect(() => {
    if (width && height) {
      setSize({ w: width, h: height });
      return;
    }
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.max(200, Math.round(entry.contentRect.width));
      setSize({ w, h: height ?? Math.max(240, Math.round(w * 0.62)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [width, height]);

  const toScreen = (n: { x: number; y: number }) => {
    const s = Math.min(size.w, size.h) - MARGIN * 2;
    const ox = (size.w - s) / 2;
    const oy = (size.h - s) / 2;
    const { k, x, y } = view.current;
    return [ox + n.x * s * k + x, oy + n.y * s * k + y] as const;
  };

  const draw = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext?.('2d');
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== size.w * dpr) {
      canvas.width = size.w * dpr;
      canvas.height = size.h * dpr;
    }
    const p = readPalette(canvas);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);

    // Contours: height is told by lightness (ink at growing opacity), never by hue.
    let prev = 0;
    contours.forEach((level, i) => {
      ctx.beginPath();
      for (const poly of level) {
        for (const ring of poly) {
          ring.forEach((pt, j) => {
            const [sx, sy] = toScreen({ x: pt[0], y: pt[1] });
            if (j === 0) ctx.moveTo(sx, sy);
            else ctx.lineTo(sx, sy);
          });
          ctx.closePath();
        }
      }
      ctx.fillStyle = p.ink;
      ctx.globalAlpha = Math.max(0, CONTOUR_STEPS[i] - prev) * 0.6;
      ctx.fill('evenodd');
      ctx.globalAlpha = CONTOUR_STEPS[i];
      ctx.strokeStyle = p.ink;
      ctx.lineWidth = 1;
      ctx.stroke();
      prev = CONTOUR_STEPS[i];
    });
    ctx.globalAlpha = 1;

    // Trail: passed legs solid ink-muted, remaining legs dashed accent.
    const pts = trail.map((id) => index.get(id)).filter((n): n is TerrainNode => !!n).map(toScreen);
    for (let i = 1; i < pts.length; i++) {
      const passed = i <= passedUntil;
      ctx.beginPath();
      ctx.moveTo(pts[i - 1][0], pts[i - 1][1]);
      ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.setLineDash(passed ? [] : [5, 4]);
      ctx.strokeStyle = passed ? p.inkMuted : p.accent;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    ctx.setLineDash([]);

    const k = view.current.k;
    const r = Math.min(4, Math.max(1.5, 2 * Math.sqrt(k)));
    const labels: [TerrainNode, number, number][] = [];
    for (const n of nodes) {
      const [sx, sy] = toScreen(n);
      if (sx < -10 || sy < -10 || sx > size.w + 10 || sy > size.h + 10) continue;
      const faded = n.status === 'weak' || n.status === 'skipped' || n.role === 'isolated';
      ctx.globalAlpha = faded ? 0.4 : 1;
      if (n.role === 'entry') {
        ctx.fillStyle = p.sunken;
        ctx.strokeStyle = p.ink;
        ctx.lineWidth = 1.5;
        ctx.fillRect(sx - 4, sy - 4, 8, 8);
        ctx.strokeRect(sx - 4, sy - 4, 8, 8);
        labels.push([n, sx, sy]);
      } else if (n.role === 'summit') {
        ctx.fillStyle = p.accent;
        ctx.beginPath();
        ctx.arc(sx, sy, r + 2.5, 0, Math.PI * 2);
        ctx.fill();
        labels.push([n, sx, sy]);
      } else {
        ctx.fillStyle = p.ink;
        ctx.fillRect(sx - r / 2, sy - r / 2, r, r);
      }
      if (n.status === 'weak') {
        ctx.globalAlpha = 1;
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = p.weak;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(sx, sy, r + 5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      } else if (n.role === 'isolated') {
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = p.inkMuted;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(sx, sy, r + 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    ctx.globalAlpha = 1;
    if (current) {
      const n = index.get(current);
      if (n) {
        const [sx, sy] = toScreen(n);
        ctx.strokeStyle = p.accent;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sx, sy, r + 6, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    // Only entries and summits are labelled (code-small, ink at 600); summits first, then by
    // altitude, skipping labels that would overlap one already drawn.
    ctx.font = `600 ${compact ? 10 : 11}px ${p.font}`;
    ctx.fillStyle = p.ink;
    ctx.textBaseline = 'middle';
    const placed: [number, number, number, number][] = [];
    labels
      .filter(([n]) => !compact || n.role === 'summit')
      .sort(([a], [b]) => (a.role === 'summit' ? 0 : 1) - (b.role === 'summit' ? 0 : 1) || (b.h ?? 0) - (a.h ?? 0))
      .forEach(([n, sx, sy]) => {
        if (!n.label) return;
        const w = ctx.measureText(n.label).width;
        const box: [number, number, number, number] = [sx + 8, sy - 7, sx + 8 + w, sy + 7];
        if (box[2] > size.w - 2) {
          box[0] = sx - 8 - w;
          box[2] = sx - 8;
        }
        if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) return;
        placed.push(box);
        ctx.fillText(n.label, box[0], sy);
      });
  };

  // Spring toward the zoom target (critically damped); instant with reduced motion.
  const animate = () => {
    cancelAnimationFrame(frame.current);
    const step = () => {
      const v = view.current;
      const t = target.current;
      const vel = velocity.current;
      if (reducedMotion()) {
        view.current = { ...t };
        draw();
        return;
      }
      const stiffness = 0.22;
      const damping = 0.62;
      let moving = false;
      for (const key of ['k', 'x', 'y'] as const) {
        vel[key] = (vel[key] + (t[key] - v[key]) * stiffness) * damping;
        v[key] += vel[key];
        if (Math.abs(t[key] - v[key]) > (key === 'k' ? 1e-4 : 0.05) || Math.abs(vel[key]) > 1e-3) moving = true;
      }
      if (!moving) view.current = { ...t };
      draw();
      if (moving) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const behavior = d3zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.5, 24])
      .on('zoom', (event: { transform: ZoomTransform }) => {
        target.current = { k: event.transform.k, x: event.transform.x, y: event.transform.y };
        animate();
      });
    zoomRef.current = behavior;
    select(canvas).call(behavior);
    return () => {
      select(canvas).on('.zoom', null);
      cancelAnimationFrame(frame.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, trail, passedUntil, current, size, contours]);

  const nearest = (mx: number, my: number): TerrainNode | null => {
    let best: TerrainNode | null = null;
    let bestD = 64;
    for (const n of nodes) {
      const [sx, sy] = toScreen(n);
      const d = (sx - mx) ** 2 + (sy - my) ** 2;
      if (d < bestD) {
        bestD = d;
        best = n;
      }
    }
    return best;
  };

  const local = (e: { clientX: number; clientY: number }) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top] as const;
  };

  const onKeyDown = (e: KeyboardEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const behavior = zoomRef.current;
    if (!canvas || !behavior) return;
    const sel = select(canvas);
    const pan = 40;
    const moves: Record<string, () => void> = {
      ArrowLeft: () => behavior.translateBy(sel, pan, 0),
      ArrowRight: () => behavior.translateBy(sel, -pan, 0),
      ArrowUp: () => behavior.translateBy(sel, 0, pan),
      ArrowDown: () => behavior.translateBy(sel, 0, -pan),
      '+': () => behavior.scaleBy(sel, 1.25),
      '=': () => behavior.scaleBy(sel, 1.25),
      '-': () => behavior.scaleBy(sel, 0.8),
      '0': () => behavior.transform(sel, zoomIdentity),
    };
    const move = moves[e.key];
    if (move) {
      e.preventDefault();
      move();
    }
  };

  return (
    <div ref={wrapRef} className={compact ? 'tb-terrain tb-terrain-compact' : 'tb-terrain'}>
      <canvas
        ref={canvasRef}
        className="tb-terrain-canvas"
        style={{ width: size.w, height: size.h }}
        role="img"
        aria-label={label ?? 'Terrain map'}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onMouseMove={(e) => {
          const [mx, my] = local(e);
          const n = nearest(mx, my);
          setHover(n ? { node: n, x: mx, y: my } : null);
        }}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          const [mx, my] = local(e);
          const n = nearest(mx, my);
          if (n) onNodeClick?.(n);
        }}
      />
      {hover && (
        <div className="tb-tooltip tb-terrain-tooltip" role="tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <span className="tb-mono">{hover.node.label ?? hover.node.id}</span>
          {hover.node.file && <span className="tb-tooltip-file">{hover.node.file}</span>}
        </div>
      )}
    </div>
  );
}

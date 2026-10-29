import { useCallback, useEffect, useMemo, useState } from 'react';
import { LangProvider, translate } from './i18n';
import { TerrainMap, type TerrainNode } from './terrain/TerrainMap';
import type { Transport } from './transport';
import { segmentKey, type Lang, type Progress, type Status, type TerrainMapData, type Trail } from './types';
import { EmptyState } from './ui';

/** The small terrain map in the VS Code sidebar: follows the climb in the panel. */
export function MapOnly({ transport, lang }: { transport: Transport; lang: Lang }) {
  const [map, setMap] = useState<TerrainMapData | null>(null);
  const [climb, setClimb] = useState<{ trail: Trail; progress: Progress } | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setClimb(await transport.call<{ trail: Trail; progress: Progress } | null>('trail.current'));
    } catch {
      /* nothing to follow yet */
    }
  }, [transport]);

  useEffect(() => {
    transport.call<TerrainMapData>('map.build').then(setMap, () => setFailed(true));
    void refresh();
    const off = transport.listen({ onRefresh: () => void refresh() });
    transport.ready?.();
    return off;
  }, [transport, refresh]);

  const nodes = useMemo<TerrainNode[]>(() => {
    if (!map) return [];
    const status = new Map<string, Status>();
    climb?.trail.segments.forEach((s) => {
      const st = climb.progress.segments[segmentKey(s)]?.status;
      if (st && st !== 'todo') s.nodes.forEach((n) => status.set(n, st));
    });
    return map.nodes.map((n) => ({
      id: n.id, x: n.x, y: n.y, h: n.h, role: n.role ?? undefined, status: status.get(n.id),
      label: n.qualname === '<module>' ? n.file : n.qualname, file: `${n.file}:${n.start_line}`,
    }));
  }, [map, climb]);

  const main = climb?.trail.segments.filter((s) => !s.detour) ?? [];
  const currentOrder = climb?.progress.current;
  const current = main.find((s) => s.order === currentOrder)?.nodes[0];
  const passed = Math.max(0, main.findIndex((s) => s.order === currentOrder));
  const t = (k: string, p?: Record<string, string | number>) => translate(lang, k, p);

  return (
    <LangProvider lang={lang}>
      <div className="tb-app tb-host-vscode tb-mapview">
        {failed ? (
          <EmptyState variant="unsupported" title={t('empty.unsupported.title')} />
        ) : !map ? (
          <EmptyState variant="analyzing" title={t('empty.analyzing.title')} body={t('empty.analyzing.body_unknown')} />
        ) : (
          <TerrainMap
            nodes={nodes}
            trail={main.map((s) => s.nodes[0])}
            passedUntil={currentOrder == null ? main.length : passed}
            current={current}
            label={t('map.label', { name: map.repo.name })}
            compact
            onNodeClick={(n) => {
              const node = map.nodes.find((x) => x.id === n.id);
              if (node) transport.openFile?.(node.file, node.start_line, node.end_line);
            }}
          />
        )}
      </div>
    </LangProvider>
  );
}

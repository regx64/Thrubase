import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckpointCard } from './climb/CheckpointCard';
import { SegmentCard } from './climb/SegmentCard';
import { Summit } from './climb/Summit';
import { TrailList, type TrailSegment } from './climb/TrailList';
import { LangProvider, translate } from './i18n';
import { TerrainMap, type TerrainNode } from './terrain/TerrainMap';
import { RemoteError, type Transport } from './transport';
import {
  segmentKey,
  type AnswerResult,
  type CodeExcerpt,
  type InitializeResult,
  type Lang,
  type Progress,
  type Segment,
  type Status,
  type TerrainMapData,
  type Trail,
} from './types';
import { Button, EmptyState, Icon, Tabs } from './ui';

const NO_SUPPORTED_LANGUAGE = -32001;
const NOT_A_GIT_REPOSITORY = -32002;
const NO_CHANGES = -32003;

type Screen = 'analyzing' | 'map' | 'climbing' | 'summit' | 'unsupported' | 'error';
type Kind = 'full' | 'diff';

interface CheckpointView {
  state: 'idle' | 'hint' | 'passed' | 'revealed';
  selected?: string;
  line?: number;
  wrong?: string;
  hint?: string;
  explanation?: string;
  answer?: string;
}

export interface AppProps {
  transport: Transport;
  initialLang?: Lang;
}

const IDLE: CheckpointView = { state: 'idle' };

export function segmentStatus(progress: Progress | null, s: Segment): Status {
  return (progress?.segments[segmentKey(s)]?.status as Status | undefined) ?? 'todo';
}

function checkpointDone(progress: Progress | null, s: Segment, cpId: string): boolean {
  const slot = cpId.slice(cpId.lastIndexOf(':') + 1);
  const st = progress?.segments[segmentKey(s)]?.checkpoints[slot]?.state;
  return st === 'passed' || st === 'revealed' || st === 'skipped';
}

export function App({ transport, initialLang = 'en' }: AppProps) {
  const [lang, setLang] = useState<Lang>(initialLang);
  const t = useCallback((key: string, params?: Record<string, string | number>) => translate(lang, key, params), [lang]);
  const [screen, setScreen] = useState<Screen>('analyzing');
  const [, setInfo] = useState<InitializeResult | null>(null);
  const [map, setMap] = useState<TerrainMapData | null>(null);
  const [trail, setTrail] = useState<Trail | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [kind, setKind] = useState<Kind>('full');
  const [focus, setFocus] = useState<number | null>(null);
  const [cpIndex, setCpIndex] = useState(0);
  const [view, setView] = useState<CheckpointView>(IDLE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>('');
  const [notice, setNotice] = useState<{ title: string; body: string } | null>(null);
  const [stage, setStage] = useState<{ stage: string; done: number; total: number } | null>(null);
  const [guides, setGuides] = useState<Record<number, string | null>>({});
  const [code, setCode] = useState<Record<number, CodeExcerpt>>({});
  const viewRef = useRef(view);
  viewRef.current = view;
  const pendingLocate = useRef<number | null>(null);

  useEffect(() => transport.onNotification((method, params) => {
    if (method === '$/progress') setStage(params as { stage: string; done: number; total: number });
  }), [transport]);

  const fail = useCallback((e: unknown) => {
    if (e instanceof RemoteError && e.code === NO_SUPPORTED_LANGUAGE) {
      setScreen('unsupported');
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
    setScreen('error');
  }, []);

  const loadMap = useCallback(async () => {
    setScreen('analyzing');
    const m = await transport.call<TerrainMapData>('map.build');
    setMap(m);
    return m;
  }, [transport]);

  const resume = useCallback((tr: Trail, pr: Progress) => {
    setTrail(tr);
    setProgress(pr);
    setKind(tr.kind);
    setFocus(pr.current ?? tr.segments[0]?.order ?? null);
    setCpIndex(0);
    setView(IDLE);
    setScreen(pr.current == null ? 'summit' : 'climbing');
  }, []);

  const boot = useCallback(async () => {
    try {
      const init = await transport.call<InitializeResult>('initialize', { lang: initialLang, clientVersion: '0.1.0' });
      setInfo(init);
      setLang(init.lang ?? initialLang);
      await loadMap();
      const cur = await transport.call<{ trail: Trail; progress: Progress } | null>('trail.current');
      if (cur && cur.progress.current != null) resume(cur.trail, cur.progress);
      else setScreen('map');
    } catch (e) {
      fail(e);
    }
  }, [transport, initialLang, loadMap, resume, fail]);

  useEffect(() => {
    void boot();
  }, [boot]);

  const start = useCallback(async (k: Kind = kind, since?: string) => {
    setBusy(true);
    setNotice(null);
    try {
      if (!map) await loadMap();
      const tr = await transport.call<Trail>('trail.build', since ? { kind: k, since } : { kind: k });
      setGuides({});
      setCode({});
      resume(tr, tr.progress!);
    } catch (e) {
      if (e instanceof RemoteError && (e.code === NO_CHANGES || e.code === NOT_A_GIT_REPOSITORY)) {
        const key = e.code === NO_CHANGES ? 'nochanges' : 'notgit';
        setNotice({ title: t(`empty.${key}.title`), body: t(`empty.${key}.body`) });
        setScreen('map');
      } else {
        fail(e);
      }
    } finally {
      setBusy(false);
    }
  }, [kind, map, loadMap, transport, resume, fail, t]);

  const startRef = useRef(start);
  startRef.current = start;
  const locateActive = useRef(false);

  useEffect(() => {
    const off = transport.listen({
      onStartClimb: (k, since) => {
        setKind(k);
        void startRef.current(k, since);
      },
      onSelectSegment: (order) => {
        setFocus(order);
        setCpIndex(0);
        setView(IDLE);
        setScreen('climbing');
      },
      onLocate: (_file, line) => {
        if (!locateActive.current) return;
        pendingLocate.current = line;
        setView((v) => (v.state === 'idle' || v.state === 'hint' ? { ...v, line } : v));
      },
    });
    transport.ready?.();
    return off;
  }, [transport]);

  const segment = useMemo(() => trail?.segments.find((s) => s.order === focus) ?? null, [trail, focus]);
  const mainSegments = useMemo(() => trail?.segments.filter((s) => !s.detour) ?? [], [trail]);
  const checkpoint = segment?.checkpoints[cpIndex] ?? null;
  locateActive.current = screen === 'climbing' && checkpoint?.type === 'locate'
    && (view.state === 'idle' || view.state === 'hint')
    && !(segment && checkpoint && checkpointDone(progress, segment, checkpoint.id));

  // Segment data: guide, code (web) and editor highlight (VS Code).
  useEffect(() => {
    if (!trail || !segment || screen !== 'climbing') return;
    const order = segment.order;
    if (!(order in guides)) {
      transport.call<{ guide: string | null }>('segment.guide', { trailId: trail.id, order })
        .then((r) => setGuides((g) => ({ ...g, [order]: r.guide })))
        .catch(() => setGuides((g) => ({ ...g, [order]: null })));
    }
    if (transport.host === 'web' && !(order in code)) {
      transport.call<CodeExcerpt>('segment.code', { trailId: trail.id, order, context: 3 })
        .then((c) => setCode((m) => ({ ...m, [order]: c })))
        .catch(() => undefined);
    }
    transport.setCurrent?.(trail.id, order, segment.file, [segment.start_line, segment.end_line]);
  }, [trail, segment, screen, guides, code, transport]);

  // When a segment opens, jump to its first unfinished checkpoint.
  useEffect(() => {
    if (!segment) return;
    const first = segment.checkpoints.findIndex((c) => !checkpointDone(progress, segment, c.id));
    setCpIndex(first === -1 ? 0 : first);
    setView(IDLE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segment?.order, trail?.id]);

  const nextStop = useCallback((pr: Progress | null) => {
    if (!trail || !segment) return;
    const more = segment.checkpoints.findIndex((c, i) => i > cpIndex && !checkpointDone(pr, segment, c.id));
    if (more !== -1) {
      setCpIndex(more);
      setView(IDLE);
      return;
    }
    const after = mainSegments.find((s) => s.order > segment.order && segmentStatus(pr, s) === 'todo')
      ?? mainSegments.find((s) => segmentStatus(pr, s) === 'todo');
    if (after) {
      setFocus(after.order);
      setView(IDLE);
    } else {
      setScreen('summit');
      transport.setCurrent?.(trail.id, null);
    }
  }, [trail, segment, cpIndex, mainSegments, transport]);

  const submit = useCallback(async (lineOverride?: number) => {
    const v = viewRef.current;
    if (!checkpoint || busy) return;
    const answer = checkpoint.type === 'locate' ? (lineOverride ?? v.line) : v.selected;
    if (answer === undefined) return;
    setBusy(true);
    try {
      const r = await transport.call<AnswerResult>('checkpoint.answer', { checkpointId: checkpoint.id, answer });
      setProgress(r.progress);
      if (r.result === 'hint') {
        setView({ ...v, state: 'hint', hint: r.hint, wrong: typeof answer === 'string' ? answer : undefined, selected: undefined, line: undefined });
      } else {
        const ans = Array.isArray(r.answer)
          ? t('checkpoint.answer', { answer: r.answer.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ') })
          : r.answer;
        setView({
          ...v,
          state: r.result === 'correct' ? 'passed' : 'revealed',
          explanation: checkpoint.type === 'locate' && r.result === 'revealed' ? `${ans}. ${r.explanation ?? ''}` : r.explanation,
          answer: typeof r.answer === 'string' ? r.answer : undefined,
        });
        if (transport.host === 'vscode' && r.file && r.evidenceLines) {
          transport.openFile?.(r.file, r.evidenceLines[0], r.evidenceLines[1]);
        }
      }
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }, [checkpoint, busy, transport, t, fail]);

  // VS Code: the line of the next editor click is submitted as the answer.
  useEffect(() => {
    if (pendingLocate.current != null && checkpoint?.type === 'locate' && (view.state === 'idle' || view.state === 'hint')) {
      const line = pendingLocate.current;
      pendingLocate.current = null;
      void submit(line);
    }
  }, [view.line, checkpoint, view.state, submit]);

  const skip = useCallback(async () => {
    if (!checkpoint) return;
    setBusy(true);
    try {
      const pr = await transport.call<Progress>('checkpoint.skip', { checkpointId: checkpoint.id });
      setProgress(pr);
      nextStop(pr);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }, [checkpoint, transport, nextStop, fail]);

  const switchLang = useCallback(async () => {
    const next: Lang = lang === 'en' ? 'ko' : 'en';
    setLang(next);
    try {
      await transport.call('initialize', { lang: next });
      const cur = await transport.call<{ trail: Trail; progress: Progress } | null>('trail.current');
      if (cur && trail && cur.trail.id === trail.id) setTrail(cur.trail);
    } catch {
      /* the UI language still switched */
    }
  }, [lang, transport, trail]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const terrainNodes = useMemo<TerrainNode[]>(() => {
    if (!map) return [];
    const status = new Map<string, Status>();
    trail?.segments.forEach((s) => {
      const st = segmentStatus(progress, s);
      if (st !== 'todo') s.nodes.forEach((n) => status.set(n, st));
    });
    return map.nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      h: n.h,
      role: n.role ?? undefined,
      status: status.get(n.id),
      label: n.qualname === '<module>' ? n.file : n.qualname,
      file: `${n.file}:${n.start_line}`,
    }));
  }, [map, trail, progress]);

  const trailPath = useMemo(() => mainSegments.map((s) => s.nodes[0]), [mainSegments]);
  const passedUntil = useMemo(() => {
    const i = mainSegments.findIndex((s) => segmentStatus(progress, s) === 'todo');
    return i === -1 ? mainSegments.length : i;
  }, [mainSegments, progress]);

  const openNode = (n: TerrainNode) => {
    const node = map?.nodes.find((x) => x.id === n.id);
    if (node) transport.openFile?.(node.file, node.start_line, node.end_line);
  };

  const trailRows: TrailSegment[] = (trail?.segments ?? []).map((s) => ({
    order: s.order, title: s.title, file: s.file, status: segmentStatus(progress, s), detour: s.detour, changed: s.changed,
  }));

  const terrain = (compact: boolean) => map && (
    <TerrainMap
      nodes={terrainNodes}
      trail={trailPath}
      passedUntil={passedUntil}
      current={screen === 'climbing' ? segment?.nodes[0] : undefined}
      label={t('map.label', { name: map.repo.name })}
      onNodeClick={openNode}
      compact={compact}
    />
  );

  const header = (
    <header className="tb-appbar">
      <h1 className="tb-title tb-logo">{t('app.title')}</h1>
      {map && <span className="tb-caption tb-repo">{map.repo.name}</span>}
      <span className="tb-spacer" />
      {(screen === 'climbing' || screen === 'summit') && (
        <Button variant="ghost" size="sm" onClick={() => setScreen('map')}>{t('action.show_map')}</Button>
      )}
      <Button variant="ghost" size="sm" onClick={switchLang} aria-label={t('lang.label')} lang={lang === 'en' ? 'ko' : 'en'}>
        {t('lang.other')}
      </Button>
    </header>
  );

  let body: JSX.Element;
  if (screen === 'analyzing') {
    const body2 = map?.repo.files ? t('empty.analyzing.body', { files: map.repo.files }) : t('empty.analyzing.body_unknown');
    const stageText = stage && stage.stage !== 'done'
      ? t(`progress.${stage.stage}`, { done: stage.done, total: stage.total })
      : '';
    body = <EmptyState variant="analyzing" title={t('empty.analyzing.title')} body={stageText ? `${body2} ${stageText}` : body2} />;
  } else if (screen === 'unsupported') {
    body = <EmptyState variant="unsupported" title={t('empty.unsupported.title')} body={t('empty.unsupported.body')} />;
  } else if (screen === 'error') {
    body = (
      <EmptyState
        variant="error"
        title={t('empty.error.title')}
        body={t('empty.error.body', { message: error })}
        action={<Button onClick={() => void boot()}>{t('action.retry')}</Button>}
      />
    );
  } else if (screen === 'map' || !trail) {
    body = (
      <div className="tb-mapscreen">
        <div className="tb-mapscreen-bar">
          <Tabs
            label={t('tabs.label')}
            items={[{ id: 'full', label: t('tabs.full') }, { id: 'diff', label: t('tabs.diff') }]}
            value={kind}
            onChange={(id) => setKind(id as Kind)}
          />
          <Button variant="primary" icon="debug-start" disabled={busy} onClick={() => void start(kind)}>
            {t('action.start_climb')}
          </Button>
          {map && (
            <span className="tb-caption">
              {t('map.summary', { files: map.repo.files, nodes: map.nodes.length - map.repo.files, entries: map.entries.length })}
            </span>
          )}
        </div>
        {notice && <EmptyState variant="no-key" title={notice.title} body={notice.body} />}
        {terrain(false)}
        <p className="tb-caption tb-legend">
          <span className="tb-legend-entry" aria-hidden="true" /> {t('map.legend.entry')}
          <span className="tb-legend-summit" aria-hidden="true" /> {t('map.legend.summit')}
          <span className="tb-legend-trail" aria-hidden="true" /> {t('map.legend.trail')}
          <span className="tb-legend-sep">·</span> {t('map.hint')}
        </p>
      </div>
    );
  } else if (screen === 'summit') {
    const review = trail.segments
      .filter((s) => ['weak', 'skipped'].includes(segmentStatus(progress, s)))
      .map((s) => ({ order: s.order, title: s.title, file: s.file, line: s.start_line, status: segmentStatus(progress, s) as 'weak' | 'skipped' }));
    body = (
      <div className="tb-climb">
        <aside className="tb-climb-side" aria-label={t('trail.label')}><TrailList segments={trailRows} onSelect={(o) => { setFocus(o); setScreen('climbing'); }} /></aside>
        <div className="tb-climb-main">
          <Summit
            review={review}
            onOpen={(o) => { setFocus(o); setScreen('climbing'); }}
            onAgain={async () => {
              const pr = await transport.call<Progress>('progress.reset', { trailId: trail.id });
              resume(trail, pr);
            }}
            onMap={() => setScreen('map')}
          />
        </div>
        <aside className="tb-climb-map" aria-label={t('term.terrain_map')}>{terrain(true)}</aside>
      </div>
    );
  } else {
    const status = segment ? segmentStatus(progress, segment) : 'todo';
    const excerpt = segment ? code[segment.order] : undefined;
    const finished = segment && checkpoint ? checkpointDone(progress, segment, checkpoint.id) && view.state === 'idle' : false;
    body = (
      <div className="tb-climb">
        <aside className="tb-climb-side" aria-label={t('trail.label')}>
          <TrailList segments={trailRows} current={focus ?? undefined} onSelect={(o) => { setFocus(o); setView(IDLE); }} />
        </aside>
        <div className="tb-climb-main">
          {segment && (
            <SegmentCard
              order={mainSegments.findIndex((s) => s.order === segment.order) + 1 || segment.order}
              total={mainSegments.length}
              title={segment.title}
              file={segment.file}
              lines={[segment.start_line, segment.end_line]}
              guide={segment.order in guides ? guides[segment.order] : undefined}
              code={excerpt ? excerpt.lines.join('\n') : undefined}
              startLine={excerpt?.startLine}
              highlight={excerpt?.highlight}
              status={status === 'todo' ? undefined : status}
              changed={segment.changed}
              selectedLine={view.line}
              onLineClick={checkpoint?.type === 'locate' && (view.state === 'idle' || view.state === 'hint') && !finished
                ? (line) => setView((v) => ({ ...v, line })) : undefined}
              onOpen={transport.host === 'vscode' ? () => transport.openFile?.(segment.file, segment.start_line, segment.end_line) : undefined}
            />
          )}
          {segment && checkpoint && (finished ? (
            <section className="tb-card tb-checkpoint" aria-label={t('checkpoint.label')}>
              <p className="tb-question">{checkpoint.prompt}</p>
              <p className="tb-body"><Icon name="info" /> {t(`status.${status}`)}</p>
              <footer className="tb-card-footer">
                <Button variant="primary" icon="arrow-right" onClick={() => nextStop(progress)}>{t('action.continue')}</Button>
              </footer>
            </section>
          ) : (
            <CheckpointCard
              key={checkpoint.id}
              type={checkpoint.type}
              prompt={checkpoint.prompt}
              options={checkpoint.options}
              selected={view.selected}
              selectedLine={view.line}
              state={view.state}
              hint={view.hint}
              wrong={view.wrong}
              explanation={view.explanation}
              answer={view.answer ?? (view.state === 'passed' ? view.selected : undefined)}
              host={transport.host}
              busy={busy}
              onSelect={(id) => setView((v) => ({ ...v, selected: id }))}
              onSubmit={() => void submit()}
              onSkip={() => void skip()}
              onContinue={() => nextStop(progress)}
            />
          ))}
        </div>
        <aside className="tb-climb-map" aria-label={t('term.terrain_map')}>{terrain(true)}</aside>
      </div>
    );
  }

  return (
    <LangProvider lang={lang}>
      <div className={`tb-app tb-host-${transport.host}`}>
        {header}
        <main className="tb-content">{body}</main>
      </div>
    </LangProvider>
  );
}

import { useT } from '../i18n';
import type { Status } from '../types';
import { Icon, StatusBadge } from '../ui';
import { useLang } from '../i18n';

export interface SegmentCardProps {
  order: number;
  total: number;
  title: string;
  file: string;
  lines: [number, number];
  /** null when no LLM key is set */
  guide?: string | null;
  code?: string;
  startLine?: number;
  highlight?: [number, number];
  status?: Status;
  changed?: boolean;
  /** web only: clicking a line number answers locate questions */
  onLineClick?: (line: number) => void;
  selectedLine?: number;
  onOpen?: () => void;
}

/** What to look at, and the code (web only). Never the answer or the explanation. */
export function SegmentCard({
  order, total, title, file, lines, guide, code, startLine = 1, highlight, status, changed, onLineClick,
  selectedLine, onOpen,
}: SegmentCardProps) {
  const t = useT();
  const lang = useLang();
  const codeLines = code === undefined ? [] : code.split('\n');
  return (
    <article className="tb-card tb-segment" aria-labelledby={`segment-${order}-title`}>
      <header className="tb-card-header">
        <div>
          <p className="tb-caption">{t('segment.of', { order, total })}</p>
          <h2 id={`segment-${order}-title`} className="tb-heading tb-mono">{title}</h2>
          <p className="tb-caption tb-segment-file">
            <Icon name="file-code" /> {file} · {t('segment.lines', { start: lines[0], end: lines[1] })}
          </p>
        </div>
        <div className="tb-card-badges">
          {changed && <span className="tb-badge tb-badge-changed"><Icon name="git-compare" />{t('segment.changed')}</span>}
          {status && status !== 'todo' && <StatusBadge status={status} lang={lang} />}
        </div>
      </header>
      {guide ? (
        <p className="tb-body tb-guide" aria-label={t('segment.guide_label')}>{guide}</p>
      ) : guide === null ? (
        <p className="tb-body tb-guide tb-guide-nokey">
          <Icon name="key" />
          <span>{t('empty.nokey.body')}</span>
        </p>
      ) : null}
      {onOpen && (
        <p>
          <button type="button" className="tb-link" onClick={onOpen}>{t('action.open_in_editor')}</button>
        </p>
      )}
      {code !== undefined && (
        <div className="tb-code" role="group" tabIndex={0} aria-label={t('segment.code_label', { title })}>
          {codeLines.map((text, i) => {
            const line = startLine + i;
            const hl = highlight && line >= highlight[0] && line <= highlight[1];
            const selected = selectedLine === line;
            return (
              <div key={line} className={['tb-code-line', hl ? 'tb-code-hl' : '', selected ? 'tb-code-selected' : ''].join(' ')}>
                {onLineClick ? (
                  <button
                    type="button"
                    className="tb-code-number"
                    aria-label={t('checkpoint.locate.selected', { line })}
                    aria-pressed={selected}
                    onClick={() => onLineClick(line)}
                  >
                    {line}
                  </button>
                ) : (
                  <span className="tb-code-number" aria-hidden="true">{line}</span>
                )}
                <code className="tb-code-text">{text || ' '}</code>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

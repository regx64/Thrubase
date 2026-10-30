import { useT } from '../i18n';
import type { Status } from '../types';
import { Icon, STATUS_ICON } from '../ui';

export interface TrailSegment {
  order: number;
  title: string;
  file: string;
  status?: Status;
  detour?: boolean;
  changed?: boolean;
}

export interface TrailListProps {
  segments: TrailSegment[];
  current?: number;
  onSelect?: (order: number) => void;
  label?: string;
}

/** One row per segment. Status is icon + color; only the current row gets accent-soft;
 * detours are indented, unnumbered and say "detour". */
export function TrailList({ segments, current, onSelect, label }: TrailListProps) {
  const t = useT();
  let number = 0;
  return (
    <ol className="tb-traillist" aria-label={label ?? t('trail.label')}>
      {segments.map((s) => {
        const status: Status = s.order === current ? 'current' : s.status ?? 'todo';
        if (!s.detour) number += 1;
        return (
          <li key={s.order} className={['tb-trailrow', `tb-trailrow-${status}`, s.detour ? 'tb-trailrow-detour' : ''].join(' ')}>
            <button
              type="button"
              className="tb-trailrow-button"
              aria-current={s.order === current ? 'step' : undefined}
              onClick={() => onSelect?.(s.order)}
              title={`${s.title} — ${s.file}`}
            >
              <Icon name={STATUS_ICON[status]} className={`tb-status-${status}`} label={t(`status.${status}`)} />
              <span className="tb-trailrow-number" aria-hidden={s.detour}>
                {s.detour ? '' : number}
              </span>
              <span className="tb-trailrow-title tb-mono">{s.title}</span>
              {s.changed && <Icon name="git-compare" className="tb-trailrow-changed" label={t('segment.changed')} />}
              <span className="tb-trailrow-file">{s.detour ? t('trail.detour') : s.file}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

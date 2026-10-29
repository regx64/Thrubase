import { useLang, useT } from '../i18n';
import { Button, Icon, StatusBadge } from '../ui';
import type { Status } from '../types';

export interface SummitProps {
  review: { order: number; title: string; file: string; line: number; status: Extract<Status, 'weak' | 'skipped'> }[];
  onOpen?: (order: number) => void;
  onAgain?: () => void;
  onMap?: () => void;
}

/** The summit: what is worth another look (unsure and skipped segments). */
export function Summit({ review, onOpen, onAgain, onMap }: SummitProps) {
  const t = useT();
  const lang = useLang();
  return (
    <section className="tb-card tb-summit" aria-labelledby="tb-summit-title">
      <header className="tb-summit-header">
        <Icon name="check" large className="tb-status-passed" />
        <h2 id="tb-summit-title" className="tb-title">{t('summit.title')}</h2>
      </header>
      {review.length === 0 ? (
        <p className="tb-body">{t('summit.none')}</p>
      ) : (
        <>
          <h3 className="tb-heading">{t('summit.review')}</h3>
          <ul className="tb-review">
            {review.map((r) => (
              <li key={r.order}>
                <button type="button" className="tb-review-row" onClick={() => onOpen?.(r.order)}>
                  <StatusBadge status={r.status} lang={lang} />
                  <code className="tb-mono">{r.title}</code>
                  <span className="tb-caption">{r.file}:{r.line}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <footer className="tb-card-footer">
        <Button variant="primary" icon="debug-start" onClick={onAgain}>{t('action.climb_again')}</Button>
        <Button onClick={onMap}>{t('action.back_to_map')}</Button>
      </footer>
    </section>
  );
}

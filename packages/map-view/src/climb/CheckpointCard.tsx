import { useEffect, useRef, type KeyboardEvent } from 'react';
import { useLang, useT } from '../i18n';
import { Button, Icon, StatusBadge } from '../ui';

export interface CheckpointOption {
  id: string;
  label: string;
}

export interface CheckpointCardProps {
  type: 'flow' | 'locate' | 'diff_edge';
  prompt: string;
  options?: CheckpointOption[];
  selected?: string;
  /** shown once passed or revealed: an option id, or a line description for locate */
  answer?: string;
  state?: 'idle' | 'hint' | 'passed' | 'revealed';
  hint?: string;
  explanation?: string;
  onSelect?: (id: string) => void;
  onSubmit?: () => void;
  onSkip?: () => void;
  onContinue?: () => void;
  /** locate: where the line is picked */
  host?: 'web' | 'vscode';
  /** locate: the picked line */
  selectedLine?: number;
  /** id of the option that was wrong on the first try */
  wrong?: string;
  busy?: boolean;
}

/** The app manages transitions: idle → hint → passed | revealed. Keyboard: 1–4 pick,
 * Enter check, S skip. */
export function CheckpointCard({
  type, prompt, options = [], selected, answer, state = 'idle', hint, explanation, onSelect, onSubmit, onSkip,
  onContinue, host = 'web', selectedLine, wrong, busy,
}: CheckpointCardProps) {
  const t = useT();
  const lang = useLang();
  const done = state === 'passed' || state === 'revealed';
  const ref = useRef<HTMLElement>(null);
  const continueRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (done) continueRef.current?.focus();
  }, [done]);

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return;
    if (done) {
      if (e.key === 'Enter' && onContinue && e.target === ref.current) {
        e.preventDefault();
        onContinue();
      }
      return;
    }
    const n = Number(e.key);
    if (n >= 1 && n <= options.length) {
      e.preventDefault();
      onSelect?.(options[n - 1].id);
    } else if (e.key === 'Enter' && (selected || selectedLine) && !(e.target instanceof HTMLButtonElement)) {
      e.preventDefault();
      onSubmit?.();
    } else if (e.key === 's' || e.key === 'S') {
      e.preventDefault();
      onSkip?.();
    }
  };

  const optionClass = (id: string) => {
    const c = ['tb-option'];
    if (id === selected && !done) c.push('tb-option-selected');
    if (state === 'hint' && id === wrong) c.push('tb-option-wrong');
    if (done && id === answer) c.push('tb-option-correct');
    return c.join(' ');
  };

  return (
    <section
      ref={ref}
      className={`tb-card tb-checkpoint tb-checkpoint-${state}`}
      aria-label={t('checkpoint.label')}
      tabIndex={-1}
      onKeyDown={onKeyDown}
    >
      <header className="tb-card-header">
        <span className="tb-label">{t(`checkpoint.type.${type}`)}</span>
        {state === 'passed' && <StatusBadge status="passed" lang={lang} />}
        {state === 'revealed' && <StatusBadge status="weak" lang={lang} />}
      </header>
      <p className="tb-question" id="tb-question">{prompt}</p>

      {type === 'locate' ? (
        <p className="tb-body tb-locate">
          <Icon name="location" />
          {selectedLine
            ? t('checkpoint.locate.selected', { line: selectedLine })
            : host === 'vscode'
              ? t('checkpoint.locate.editor')
              : t('checkpoint.locate.web')}
        </p>
      ) : (
        <div className="tb-options" role="radiogroup" aria-labelledby="tb-question">
          {options.map((o, i) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={o.id === selected}
              disabled={done}
              className={optionClass(o.id)}
              onClick={() => onSelect?.(o.id)}
            >
              <span className="tb-option-key" aria-hidden="true">{i + 1}</span>
              <code className="tb-option-label">{o.label}</code>
              {done && o.id === answer && <Icon name="check" className="tb-status-passed" />}
              {state === 'hint' && o.id === wrong && <Icon name="warning" className="tb-status-weak" />}
            </button>
          ))}
        </div>
      )}

      {state === 'hint' && hint && (
        <p className="tb-hint" role="status">
          <Icon name="lightbulb" />
          <span>{hint}</span>
        </p>
      )}
      {done && explanation && (
        <p className="tb-explanation" role="status">
          <Icon name="info" />
          <span>{explanation}</span>
        </p>
      )}

      <footer className="tb-card-footer">
        {done ? (
          <Button ref={continueRef} variant="primary" icon="arrow-right" onClick={onContinue}>
            {t('action.continue')}
          </Button>
        ) : (
          <>
            <Button variant="primary" disabled={busy || !(selected || selectedLine)} onClick={onSubmit}>
              {t('action.check')}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={onSkip}>
              {t('action.skip')}
            </Button>
            <span className="tb-caption tb-keys" aria-hidden="true">{t('checkpoint.keys')}</span>
          </>
        )}
      </footer>
    </section>
  );
}

import { useId, type InputHTMLAttributes } from 'react';
import { Icon } from './Icon';

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

/** Label above; help or error text below on one line. Errors are never signalled by color alone. */
export function TextInput({ label, hint, error, id, className, ...rest }: TextInputProps) {
  const auto = useId();
  const inputId = id ?? auto;
  const noteId = `${inputId}-note`;
  return (
    <div className={['tb-field', error ? 'tb-field-error' : '', className ?? ''].join(' ').trim()}>
      {label && <label className="tb-field-label" htmlFor={inputId}>{label}</label>}
      <input
        id={inputId}
        className="tb-input"
        aria-invalid={error ? true : undefined}
        aria-describedby={error || hint ? noteId : undefined}
        {...rest}
      />
      {error ? (
        <p id={noteId} className="tb-field-note tb-field-note-error"><Icon name="warning" />{error}</p>
      ) : hint ? (
        <p id={noteId} className="tb-field-note">{hint}</p>
      ) : null}
    </div>
  );
}

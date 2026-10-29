import { cloneElement, isValidElement, useId, useState, type ReactElement, type ReactNode } from 'react';

export interface TooltipProps {
  text: string;
  open?: boolean;
  children: ReactNode;
}

/** Supplementary, one-line information about something already on screen. Opens on hover and
 * on keyboard focus. Never holds answers, hints or explanations. */
export function Tooltip({ text, open, children }: TooltipProps) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const visible = open ?? shown;
  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, { 'aria-describedby': id })
    : children;
  return (
    <span
      className="tb-tooltip-anchor"
      onMouseEnter={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      onFocus={() => setShown(true)}
      onBlur={() => setShown(false)}
      onKeyDown={(e) => e.key === 'Escape' && setShown(false)}
    >
      {child}
      <span id={id} role="tooltip" className="tb-tooltip" hidden={!visible}>
        {text}
      </span>
    </span>
  );
}

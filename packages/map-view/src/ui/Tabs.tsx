import { useRef, useState, type KeyboardEvent } from 'react';

export interface TabsProps {
  items: { id: string; label: string }[];
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  label?: string;
}

/** Segmented tabs (2–4) that switch a view in place. Arrow keys move between tabs. */
export function Tabs({ items, value, defaultValue, onChange, label }: TabsProps) {
  const [inner, setInner] = useState(defaultValue ?? items[0]?.id);
  const current = value ?? inner;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const select = (id: string) => {
    setInner(id);
    onChange?.(id);
  };
  const onKey = (e: KeyboardEvent, index: number) => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (index + delta + items.length) % items.length;
    refs.current[next]?.focus();
    select(items[next].id);
  };
  return (
    <div className="tb-tabs" role="tablist" aria-label={label}>
      {items.map((item, i) => (
        <button
          key={item.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          aria-selected={item.id === current}
          tabIndex={item.id === current ? 0 : -1}
          className={item.id === current ? 'tb-tab tb-tab-selected' : 'tb-tab'}
          onClick={() => select(item.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

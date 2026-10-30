import { translate } from '../i18n';
import type { Lang } from '../types';
import { Icon } from './Icon';

export interface StatusBarItemProps {
  count: number;
  lang?: Lang;
  onClick?: () => void;
}

/** Mock of the VS Code status bar suggestion (the real item is created by the extension with
 * vscode.window.createStatusBarItem). A suggestion, not a warning: theme default colors. */
export function StatusBarItem({ count, lang = 'en', onClick }: StatusBarItemProps) {
  return (
    <div className="tb-statusbar" role="presentation">
      <button type="button" className="tb-statusbar-item" title={translate(lang, 'statusbar.tooltip')} onClick={onClick}>
        <Icon name="debug-start" />
        {translate(lang, 'statusbar.text', { n: count })}
      </button>
    </div>
  );
}

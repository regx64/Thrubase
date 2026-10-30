// Editor integration: open files, highlight the current segment, and turn the next mouse
// click in the segment's file into the answer of a locate question.
import * as vscode from 'vscode';

export class EditorBridge implements vscode.Disposable {
  private readonly segmentDecoration = vscode.window.createTextEditorDecorationType({
    isWholeLine: true,
    backgroundColor: new vscode.ThemeColor('thrubase.segmentBackground'),
    overviewRulerColor: new vscode.ThemeColor('thrubase.segmentBackground'),
    overviewRulerLane: vscode.OverviewRulerLane.Left,
  });
  private readonly evidenceDecoration = vscode.window.createTextEditorDecorationType({
    isWholeLine: true,
    backgroundColor: new vscode.ThemeColor('editor.rangeHighlightBackground'),
    borderWidth: '0 0 0 2px',
    borderStyle: 'solid',
    borderColor: new vscode.ThemeColor('focusBorder'),
  });
  private current: { file: string; range: [number, number] } | undefined;
  private readonly subs: vscode.Disposable[] = [];
  private readonly clickEmitter = new vscode.EventEmitter<{ file: string; line: number }>();
  /** A mouse click (not keyboard movement) in the current segment's file. */
  readonly onLocate = this.clickEmitter.event;

  constructor(private readonly root: () => vscode.Uri | undefined) {
    this.subs.push(
      vscode.window.onDidChangeTextEditorSelection((e) => {
        if (!this.current || e.kind !== vscode.TextEditorSelectionChangeKind.Mouse) return;
        const rel = this.relative(e.textEditor.document.uri);
        if (rel !== this.current.file || !e.selections[0]?.isEmpty) return;
        this.clickEmitter.fire({ file: rel, line: e.selections[0].active.line + 1 });
      }),
      vscode.window.onDidChangeVisibleTextEditors(() => this.paint()),
    );
  }

  uri(file: string): vscode.Uri | undefined {
    const root = this.root();
    // Paths are POSIX inside Thrubase; joinPath turns them into OS paths only here.
    return root ? vscode.Uri.joinPath(root, ...file.split('/')) : undefined;
  }

  relative(uri: vscode.Uri): string | undefined {
    const root = this.root();
    if (!root) return undefined;
    const rel = vscode.workspace.asRelativePath(uri, false);
    // asRelativePath hands back the full path for files outside the workspace.
    return rel === uri.fsPath ? undefined : rel.replace(/\\/g, '/');
  }

  async open(file: string, line: number, endLine?: number, preserveFocus = true): Promise<void> {
    const uri = this.uri(file);
    if (!uri) return;
    const doc = await vscode.workspace.openTextDocument(uri);
    const range = new vscode.Range(Math.max(0, line - 1), 0, Math.max(0, (endLine ?? line) - 1), 0);
    const editor = await vscode.window.showTextDocument(doc, {
      viewColumn: vscode.ViewColumn.One,
      preserveFocus,
      preview: false,
      selection: new vscode.Range(range.start, range.start),
    });
    editor.revealRange(range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
  }

  /** Highlight the segment range and show it. */
  async setSegment(file: string | undefined, range: [number, number] | undefined): Promise<void> {
    this.current = file && range ? { file, range } : undefined;
    if (this.current) await this.open(this.current.file, range![0], range![1]);
    this.paint();
  }

  showEvidence(file: string, lines: [number, number]): void {
    for (const editor of vscode.window.visibleTextEditors) {
      if (this.relative(editor.document.uri) === file) {
        editor.setDecorations(this.evidenceDecoration, [new vscode.Range(lines[0] - 1, 0, lines[1] - 1, 0)]);
      }
    }
  }

  private paint(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      const match = this.current && this.relative(editor.document.uri) === this.current.file;
      editor.setDecorations(
        this.segmentDecoration,
        match ? [new vscode.Range(this.current!.range[0] - 1, 0, this.current!.range[1] - 1, 0)] : [],
      );
      if (!match) editor.setDecorations(this.evidenceDecoration, []);
    }
  }

  dispose(): void {
    this.subs.forEach((d) => d.dispose());
    this.segmentDecoration.dispose();
    this.evidenceDecoration.dispose();
    this.clickEmitter.dispose();
  }
}

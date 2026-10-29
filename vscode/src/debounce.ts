/** Collapses bursts (an agent saving ten files at once) into one call after `ms` of quiet. */
export class Debouncer {
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly ms: number,
    private readonly fn: () => void,
    private readonly timers: { set: typeof setTimeout; clear: typeof clearTimeout } = { set: setTimeout, clear: clearTimeout },
  ) {}

  trigger(): void {
    if (this.timer) this.timers.clear(this.timer);
    this.timer = this.timers.set(() => {
      this.timer = undefined;
      this.fn();
    }, this.ms);
  }

  dispose(): void {
    if (this.timer) this.timers.clear(this.timer);
    this.timer = undefined;
  }
}

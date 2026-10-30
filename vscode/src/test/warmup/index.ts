// Starts VS Code once and exits: a language pack installed from the command line only takes
// effect from the next start, after VS Code has built its translation cache.
export function run(): Promise<void> {
  return Promise.resolve();
}

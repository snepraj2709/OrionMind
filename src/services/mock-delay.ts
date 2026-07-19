export function simulateLatency(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

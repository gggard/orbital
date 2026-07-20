const MI = 2 ** 20;
const GI = 2 ** 30;

export function fmtCpu(cores: number): string {
  if (cores < 0.9995) return `${Math.round(cores * 1000)}m`;
  return `${cores.toFixed(cores < 10 ? 2 : 1)}`;
}

export function fmtMem(bytes: number): string {
  if (bytes < GI) return `${Math.round(bytes / MI)} MiB`;
  return `${(bytes / GI).toFixed(2)} GiB`;
}

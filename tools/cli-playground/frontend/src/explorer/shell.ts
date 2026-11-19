import type { Argument } from "../services/catalog";

export function quoteToken(value: string): string {
  // eslint-disable-next-line no-control-regex
  if (!value || /[\x00-\x1f\x7f-\x9f\u2028\u2029]/.test(value))
    throw new Error("Unsafe terminal token");
  return /^[a-zA-Z0-9_./-]+$/.test(value) ? value : `'${value.replace(/'/g, `'"'"'`)}'`;
}
export function commandText(cli: string, path: string[]): string {
  return [quoteToken(cli), ...path.map(quoteToken)].join(" ") + " ";
}
export function flagNames({ long, short }: Argument) {
  return { long: long ? `--${long}` : "", short: short ? `-${short}` : "" };
}
export function flagText(arg: Argument): string {
  const { long, short } = flagNames(arg);
  const flag = long || short;
  if (!flag) return "";
  return ` ${quoteToken(flag)} `;
}

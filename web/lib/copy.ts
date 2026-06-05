/**
 * lib/copy.ts — single source of typed locale strings.
 *
 * The canonical string values live in lib/locales/id.json and en.json.
 * This file imports them and provides:
 *   - COPY[lang]  — the full locale object for a given language
 *   - CopyShape   — a flexible type for component props (all leaves → string,
 *                   all nested objects → Record<string, string>)
 *
 * To add a new string: add the key + value to BOTH JSON files, then use it
 * as t.yourNewKey or labels.yourNewKey. TypeScript will error if a key is
 * missing from either locale.
 */

import id from "./locales/id.json";
import en from "./locales/en.json";

// Compile-time guard: both locales must have identical keys.
// If they diverge, this line will produce a type error.
type _LocaleCheck = typeof id extends typeof en
  ? typeof en extends typeof id
    ? true
    : never
  : never;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _check: _LocaleCheck = true;

export const COPY = { id, en } as const;

/**
 * CopyShape is what components receive via `labels: CopyShape`.
 * All leaf values are widened to `string` and nested objects to
 * `Record<string, string>` so that both COPY["id"] and COPY["en"]
 * are assignable without hitting literal-type conflicts.
 */
export type CopyShape = {
  [K in keyof typeof id]: (typeof id)[K] extends Record<string, unknown>
    ? Record<string, string>
    : string;
};

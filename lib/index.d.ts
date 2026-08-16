import { Context } from "@deepseek-ai/cordis";
//#region src/index.d.ts
/** Minimal structural projection of the Cordis Loader entry tree used by DSH. */
interface LoaderEntryOptions {
  id: string;
  name: string;
  group?: boolean | null;
  disabled?: boolean | null;
}
interface LoaderEntry {
  id: string;
  options: LoaderEntryOptions;
  readonly disabled: boolean;
  fiber?: {
    state: number;
  } | undefined;
}
interface RuntimeLoader {
  entries(): Iterable<LoaderEntry>;
}
declare module '@deepseek-ai/cordis' {
  interface Context {
    loader?: RuntimeLoader;
  }
}
/** Register the host bridge. The Core executable is intentionally external. */
declare const inject: string[];
declare function apply(ctx: Context): void;
//#endregion
export { apply, inject };
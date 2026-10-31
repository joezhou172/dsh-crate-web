export interface RuntimePluginRow { id: string; name: string; enabled: boolean; phase: string | null }
export function readRuntimeInventory(ctx: unknown): { rows: RuntimePluginRow[]; complete: boolean }
export function inspectorApplicability(rows: unknown, complete: unknown): {
  inventoryComplete: true; inventoryCount: number; applicable: boolean; reason: string; plugins: RuntimePluginRow[]
}

/** Portable directory names, shared by the UI and the Core bridge. */
export function isSafeProfileName(value: unknown): value is string {
  return typeof value === 'string'
    && value.length > 0 && value.trim() === value
    && value !== '.' && value !== '..'
    && !/[<>:"/\\|?*\x00-\x1f\x7f]/.test(value)
    && !/[. ]$/.test(value)
    && !/^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)/i.test(value)
    && value.toLowerCase() !== 'node_modules'
}

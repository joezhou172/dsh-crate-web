type IconName = 'cube' | 'copy' | 'send' | 'chat' | 'close' | 'file'
const paths: Record<IconName, string> = {
  cube: 'M12 2 22 7v10l-10 5-10-5V7l10-5Zm0 10L2 7m10 5 10-5M12 12v10M7 4.5l10 5',
  copy: 'M9 8h11v14H9zM5 16H2V2h11v3',
  send: 'm22 2-7 20-4-9-9-4 20-7Zm0 0L11 13',
  chat: 'M4 3h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H9l-6 4v-4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm3 8h.01M12 11h.01M17 11h.01',
  close: 'm6 6 12 12M6 18 18 6',
  file: 'M14 2H4v20h16V8l-6-6Zm0 0v6h6M8 13h8M8 17h8',
}
export function CrateIcon({ name }: { name: IconName }) {
  return <svg className="dsh-crate-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}

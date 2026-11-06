const shapes = {
  cycle: <><path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5M4 16a8 8 0 0 0 14 2l3-3m0 5v-5h-5" /><path d="M12 7c-2 3-4 5-4 7a4 4 0 0 0 8 0c0-2-2-4-4-7Z" /></>,
  oil: <><path d="M5 8h14v12H5zM8 8V5h8v3M9 2h6M4 12h4m8 0h4M4 17h4m8 0h4" /><path d="M12 10c-1 2-2 3-2 4a2 2 0 0 0 4 0c0-1-1-2-2-4Z" /></>,
  canister: <><path d="M7 4h5l3 4h4v13H5V8l2-4ZM8 1h4v3M8 8l1-2h2l2 2M8 12h8v6H8z" /></>,
  cap: <><ellipse cx="12" cy="7" rx="8" ry="3" /><path d="M4 7v9c0 4 16 4 16 0V7M7 11v5m3-4v5m4-5v5m3-6v5" /></>,
  boiler: <><path d="M6 5h12v14H6zM4 19h16M9 2v3m6-3v3M3 10h3m12 0h3" /><path d="M12 10c2 2 3 3 3 4a3 3 0 0 1-6 0c0-1 1-3 3-4Z" /></>,
  separator: <><path d="M4 4h16l-3 9H7L4 4ZM9 13v7m6-7v7M3 20h8m2 0h8M12 1v3" /><path d="M8 8h8" /></>,
  outlet: <><path d="M5 3v7c0 4 3 6 7 6h5M14 12l4 4-4 4M9 3v7c0 1 1 2 3 2" /></>,
  mixer: <><path d="M6 7h12v11a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V7ZM12 2v15M9 14l6 3m-6 0 6-3M4 7h16" /></>,
  factory: <><path d="M3 21V10l6 3V7l6 4V3h4l2 18H3ZM7 17h1m3 0h1m4 0h1M16 3h3" /></>,
  tank: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 4 16 4 16 0V5M4 12c3 3 13 3 16 0" /></>,
  supply: <><path d="m3 8 9-5 9 5-9 5-9-5ZM3 8v10l9 4 9-4V8M12 13v9M8 5l9 5" /></>,
  filter: <><path d="M4 3h16v6l-6 6v6h-4v-6L4 9V3ZM4 7h16M8 3v4m4-4v4m4-4v4" /></>,
  filling: <><path d="M4 3h12v6h4M8 3v7M7 13h6v8H7v-8ZM9 10v3M17 13h4v8h-4v-8ZM19 9v4" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
}

export function ProductionIcon({ name, className = '' }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{shapes[name] || shapes.factory}</svg>
}

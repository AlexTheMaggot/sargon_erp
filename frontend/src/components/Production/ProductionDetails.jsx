export function ProductionDetails({ children, title }) {
  return (
    <section className="access-grid">
      <details className="access-card production-details">
        <summary>{title}</summary>
        <div className="production-details-body">{children}</div>
      </details>
    </section>
  )
}

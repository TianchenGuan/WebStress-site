import { Link, NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS: { to: string; label: string }[] = [
  { to: "/tasks", label: "Tasks" },
  { to: "/primitives", label: "Primitives" },
  { to: "/environments", label: "Environments" },
  { to: "/results", label: "Results" },
  { to: "/docs", label: "Docs" },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-cream/90 backdrop-blur sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-6">
          <Link to="/" className="no-underline text-ink hover:text-accent">
            <span className="font-serif text-xl font-bold tracking-tight">
              WebStress
            </span>
            <span className="ml-2 text-xs uppercase tracking-widest text-muted">
              Benchmark
            </span>
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `no-underline transition ${
                    isActive ? "text-accent font-medium" : "text-ink hover:text-accent"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border mt-12 py-8 bg-white">
        <div className="max-w-6xl mx-auto px-6 text-xs text-muted flex flex-wrap items-center justify-between gap-4">
          <div>
            WebStress benchmark · NeurIPS 2026 submission
            <span className="mx-2">·</span>
            <a
              href="https://github.com/Arvid-pku/WebStress"
              target="_blank"
              rel="noreferrer"
              className="text-muted hover:text-accent"
            >
              GitHub
            </a>
            <span className="mx-2">·</span>
            <Link to="/docs" className="text-muted hover:text-accent">
              Documentation
            </Link>
          </div>
          <div>
            Synthetic sandbox environments. No real user data.
          </div>
        </div>
      </footer>
    </div>
  );
}

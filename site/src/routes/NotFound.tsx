import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-20 text-center">
      <h1 className="text-4xl font-serif mb-3">404</h1>
      <p className="text-ink/80 mb-6">
        That page doesn't exist on this site.
      </p>
      <Link to="/" className="btn-primary">
        ← Back to home
      </Link>
    </div>
  );
}

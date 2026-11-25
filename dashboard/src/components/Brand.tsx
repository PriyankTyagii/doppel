import { Link } from "../lib/router";

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="brand" aria-label="Doppel home">
      <span className="brand-mark" aria-hidden>
        <i />
        <i />
      </span>
      <span className="brand-name">Doppel</span>
    </Link>
  );
}

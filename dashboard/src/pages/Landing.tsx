import { Brand } from "../components/Brand";
import { useAuth } from "../lib/auth";
import { Link } from "../lib/router";

const STEPS = [
  {
    title: "Connect both versions",
    body: "Synapse turns the legacy API and the rewrite into two MCP servers. Doppel calls both the same way, whatever language each is written in.",
  },
  {
    title: "Run real business scenarios",
    body: "Sixty seeded cases cover states, coupons, Sunday due dates, late payments and partial refunds. Each one runs on both systems from the same seed data.",
  },
  {
    title: "Diff without the noise",
    body: "Ids, timestamps, key order and sub-paisa float noise are ignored. Every remaining difference is a field, a value on each side, and a rupee delta.",
  },
  {
    title: "Explain from the code",
    body: "Each group of mismatches is traced to a file and line in both codebases, plus the change in the rewrite that caused it. Doppel never edits code.",
  },
];

const OUTPUTS = [
  { title: "Parity score", body: "The share of scenarios where the rewrite returns exactly what the legacy system returns, and how it moved since the last run." },
  { title: "Root cause with line numbers", body: "What v1 does, what v2 does, and where: file and line in each system, with a suggested fix for a human to apply." },
  { title: "Business impact", body: "Invoices affected, customers over- and under-charged, GST misreported, and a projection to your monthly volume, labelled as a projection." },
  { title: "Change detection", body: "Re-runs only call the rewrite. New, fixed and unchanged mismatches are marked, so a regression shows up within seconds of a change." },
];

export function Landing() {
  const { user } = useAuth();
  const cta = user ? { href: "/app", label: "Open dashboard" } : { href: "/login", label: "Get started" };

  return (
    <div className="landing">
      <header className="site-nav">
        <Brand />
        <nav>
          <a href="#how">How it works</a>
          <Link href={user ? "/app" : "/login"} className="btn btn-sm">
            {user ? "Dashboard" : "Sign in"}
          </Link>
        </nav>
      </header>

      <main>
        <section className="hero-landing">
          <div className="hero-copy">
            <p className="eyebrow">Parity testing for AI rewrites</p>
            <h1>Prove the rewrite still bills like the original.</h1>
            <p className="lede">
              Doppel runs the same business scenarios against your legacy system and its rewrite, compares every field, and
              traces each difference to the line of code that caused it.
            </p>
            <div className="hero-actions">
              <Link href={cta.href} className="btn btn-primary btn-lg">
                {cta.label}
              </Link>
              <a href="#how" className="btn btn-lg btn-ghost">
                How it works
              </a>
            </div>
          </div>

          <figure className="sample" aria-label="Example finding from a Doppel run">
            <div className="sample-top">
              <span className="sample-score">82%</span>
              <span className="muted">49 of 60 scenarios identical</span>
            </div>
            <div className="sample-card">
              <span className="pill pill-bad">Mismatch</span>
              <h3>Sunday late-fee waiver missing in the rewrite</h3>
              <p>
                v1 waives the 2% late fee when the due date falls on a Sunday. v2 charges it whenever payment is late. The rule
                was never documented.
              </p>
              <dl className="sample-stats">
                <div>
                  <dt>Invoices</dt>
                  <dd>4</dd>
                </div>
                <div>
                  <dt>Overcharged</dt>
                  <dd>₹119.18</dd>
                </div>
              </dl>
              <div className="sample-refs">
                <code>billing-v1/main.py:229</code>
                <code>billing-v2/src/tax.ts:56</code>
              </div>
            </div>
            <figcaption className="muted">From the demo billing system: legacy Python vs TypeScript rewrite.</figcaption>
          </figure>
        </section>

        <section className="problem">
          <p>
            AI can rewrite a legacy system in days. Proving the rewrite is correct is the hard part: one study of AI
            migrations found only <strong>51% parity</strong> on high-level business features.{" "}
            <a href="https://arxiv.org/pdf/2608.28972" target="_blank" rel="noreferrer">
              Source
            </a>
          </p>
        </section>

        <section id="how" className="section">
          <h2>How it works</h2>
          <ol className="steps-list">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className="step-num">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="section">
          <h2>What you get from every run</h2>
          <div className="outputs">
            {OUTPUTS.map((o) => (
              <div key={o.title} className="output">
                <h3>{o.title}</h3>
                <p>{o.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="closing">
          <h2>Check the rewrite before you switch.</h2>
          <Link href={cta.href} className="btn btn-primary btn-lg">
            {cta.label}
          </Link>
        </section>
      </main>

      <footer className="site-foot">
        <Brand />
        <span className="muted">Read-only by design: Doppel never changes either codebase.</span>
      </footer>
    </div>
  );
}

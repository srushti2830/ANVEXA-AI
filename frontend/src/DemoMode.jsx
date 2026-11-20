import React, { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import fixtures from "./demoFixtures.json";

const REVIEW_STORAGE_KEY = "anvexa_demo_reviews_v1";
const VERIFIED_STORAGE_KEY = "anvexa_demo_verified_v1";
const VERDICTS = [
  "SUPPORTED",
  "PARTLY_SUPPORTED",
  "UNSUPPORTED",
  "CONTRADICTORY",
  "POSSIBLY_OUTDATED",
  "NEEDS_REVIEW",
];
const NAV_ITEMS = [
  ["dashboard", "Dashboard"],
  ["document", "Prepared document"],
  ["claims", "Claims & evidence"],
  ["sources", "Citation & sources"],
  ["verification", "Verification"],
  ["review", "Human review"],
  ["report", "Report"],
];

function readReviews() {
  const saved = sessionStorage.getItem(REVIEW_STORAGE_KEY);
  return saved ? JSON.parse(saved) : [];
}

function DemoHeader({ eyebrow, title, action }) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {action && <div className="header-actions">{action}</div>}
    </header>
  );
}

function DemoDashboard() {
  const metrics = [
    ["Prepared claims", fixtures.claims.length],
    ["Citation markers", fixtures.citations.length],
    ["Synthetic source records", fixtures.sourceRecords.length],
    ["Verdict categories", VERDICTS.length],
  ];
  return (
    <>
      <DemoHeader eyebrow="Prepared workspace" title="Demo dashboard" action={<Link className="button" to="/demo/document">Open prepared document</Link>} />
      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>
        ))}
      </div>
      <section className="panel demo-intro">
        <span className="demo-label">ILLUSTRATIVE FIXTURE — NOT LIVE RESEARCH</span>
        <h2>{fixtures.document.title}</h2>
        <p>{fixtures.document.classification}.</p>
        <p>This guided journey uses deterministic prepared examples. It makes no database writes and does not call Gemini or research providers.</p>
        <Link className="button" to="/demo/document">Begin the demo journey</Link>
      </section>
      <section className="panel">
        <div className="panel-heading"><h2>Journey</h2></div>
        <div className="demo-journey">
          {NAV_ITEMS.slice(1).map(([path, label], index) => (
            <Link key={path} to={`/demo/${path}`}><span>{String(index + 1).padStart(2, "0")}</span>{label}</Link>
          ))}
        </div>
      </section>
    </>
  );
}

function DemoDocument() {
  return (
    <>
      <DemoHeader eyebrow="Prepared document" title={fixtures.document.title} action={<Link className="button" to="/demo/claims">Inspect extracted claims</Link>} />
      <section className="panel">
        <div className="demo-meta">
          <span className="demo-label">SYNTHETIC PREPARED DATA</span>
          <span>{fixtures.document.filename}</span>
          <span>{fixtures.document.classification}</span>
        </div>
        {fixtures.document.sections.map((section) => (
          <article className="demo-document-section" key={section.heading}>
            <h2>{section.heading}</h2>
            <p>{section.text}</p>
            {section.citationMarker && <span className="demo-marker">{section.citationMarker}</span>}
          </article>
        ))}
        <p className="demo-footnote">This is a prepared academic-style scenario displayed as text; no real paper was uploaded or parsed.</p>
      </section>
    </>
  );
}

function DemoClaims() {
  return (
    <>
      <DemoHeader eyebrow="Prepared extraction" title="Claims and evidence" action={<Link className="button secondary" to="/demo/sources">Explore citation mappings</Link>} />
      <p className="demo-callout">All passages below are synthetic examples written for this demo. They are not quotations from publications.</p>
      <div className="demo-claim-list">
        {fixtures.claims.map((claim) => (
          <article className="panel demo-claim" key={claim.id}>
            <div className="panel-heading">
              <span className="demo-label">{claim.id}</span>
              <span className="status">{claim.citationMarker}</span>
            </div>
            <h2>{claim.text}</h2>
            <p className="muted">Page {claim.page} · {claim.section}</p>
            <div className="demo-mapping">
              <strong>Mapped prepared records:</strong>{" "}
              {claim.sourceIds.length
                ? claim.sourceIds.map((id) => <Link key={id} to="/demo/sources">{id}</Link>)
                : <span>None in this fixture</span>}
            </div>
            {claim.evidence.length ? claim.evidence.map((item, index) => (
              <article className="evidence-card" key={`${claim.id}-${index}`}>
                <span className="demo-label">{item.kind}</span>
                <p>{item.passage}</p>
                <footer>{item.sourceId} · prepared, not externally retrieved</footer>
              </article>
            )) : <p className="demo-no-evidence">No evidence passage is prepared for this claim. This is not proof that the claim is false.</p>}
          </article>
        ))}
      </div>
      <Link className="button" to="/demo/verification">Continue to demo verification</Link>
    </>
  );
}

function DemoSources() {
  return (
    <>
      <DemoHeader eyebrow="Traceability" title="Citation and source explorer" action={<Link className="button" to="/demo/verification">Open verification</Link>} />
      <p className="demo-callout">These are synthetic source-record fixtures, not real research publications. No Crossref, OpenAlex, Semantic Scholar, Europe PMC, or other provider was queried.</p>
      <section className="panel">
        <div className="panel-heading"><h2>Illustrative citation mappings</h2><span>{fixtures.citations.length} markers</span></div>
        {fixtures.citations.map((citation) => (
          <article className="demo-citation-row" key={citation.marker}>
            <strong>{citation.marker}</strong>
            <span>{citation.sourceIds.length ? citation.sourceIds.join(", ") : "No mapped source"}</span>
            <small>{citation.mappingNote}</small>
          </article>
        ))}
      </section>
      <div className="source-grid demo-source-grid">
        {fixtures.sourceRecords.map((source) => (
          <article className="source-card" key={source.id}>
            <span className="demo-label">SYNTHETIC · NOT A PUBLICATION</span>
            <h3>{source.label}</h3>
            <p>{source.recordType}</p>
            <p>{source.summary}</p>
            <p><strong>Provider:</strong> {source.providerStatus}</p>
            <p><strong>Identifier:</strong> {source.identifier}</p>
          </article>
        ))}
      </div>
    </>
  );
}

function DemoVerification({ verified, onRun }) {
  return (
    <>
      <DemoHeader eyebrow="Prepared workflow" title="Demo verification" />
      <section className="panel demo-intro">
        <h2>Run the prepared verification illustration</h2>
        <p>This action reveals fixture verdicts and explanations. It does not run Gemini, contact a research provider, or assess a real document.</p>
        <button className="button" onClick={onRun}>{verified ? "Show prepared verdicts again" : "Run prepared demo verification"}</button>
      </section>
      {verified ? (
        <>
          <div className="success-box">Prepared demonstration results shown. No live verification was performed.</div>
          <div className="demo-verdict-list">
            {fixtures.claims.map((claim) => (
              <article className="panel demo-verdict" key={claim.id}>
                <div className="panel-heading"><h2>{claim.verdict}</h2><span className="status">Illustrative</span></div>
                <p className="demo-claim-text">{claim.text}</p>
                <p>{claim.explanation}</p>
                <h3>Limitations</h3>
                <ul>{claim.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                <p className="muted">Evidence references: {claim.sourceIds.length ? claim.sourceIds.join(", ") : "none prepared"}</p>
              </article>
            ))}
          </div>
          <Link className="button" to="/demo/review">Continue to human review</Link>
        </>
      ) : <p className="muted">The prepared verdicts will appear here after you trigger the demonstration workflow.</p>}
    </>
  );
}

function DemoReview({ reviews, onSave }) {
  const [claimId, setClaimId] = useState("claim-needs-review");
  const [verdict, setVerdict] = useState("NEEDS_REVIEW");
  const [explanation, setExplanation] = useState("Sample reviewer note: the prepared evidence is insufficient for a population-wide conclusion.");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const selectedClaim = fixtures.claims.find((claim) => claim.id === claimId);

  function submit(event) {
    event.preventDefault();
    if (explanation.trim().length < 10) {
      setError("Enter a reviewer explanation of at least 10 characters.");
      return;
    }
    onSave({
      id: `demo-review-${Date.now()}`,
      claimId,
      claimText: selectedClaim.text,
      verdict,
      explanation: explanation.trim(),
      submittedAt: new Date().toISOString(),
    });
    setError("");
    setSaved(true);
  }

  return (
    <>
      <DemoHeader eyebrow="Local-only interaction" title="Human review" />
      <p className="demo-callout">Review submissions are stored only in this browser tab's demo session. No account or backend request is used.</p>
      <div className="review-layout demo-review-layout">
        <section className="panel review-list-panel">
          <div className="panel-heading"><h2>Prepared review queue</h2><span>1 sample</span></div>
          <article className="evidence-card">
            <span className="status">NEEDS_REVIEW</span>
            <p>{fixtures.claims.find((claim) => claim.id === "claim-needs-review").text}</p>
            <footer>Illustrative document · synthetic evidence only</footer>
          </article>
          <h3>Submitted demo reviews</h3>
          {reviews.length ? reviews.map((review) => (
            <article className="demo-review-entry" key={review.id}>
              <strong>{review.verdict}</strong>
              <p>{review.claimText}</p>
              <small>{new Date(review.submittedAt).toLocaleString()}</small>
            </article>
          )) : <p className="muted">No review submitted in this demo session yet.</p>}
        </section>
        <form className="panel review-detail" onSubmit={submit}>
          <p className="eyebrow">Sample reviewer action</p>
          <label>Claim
            <select value={claimId} onChange={(event) => { setClaimId(event.target.value); setSaved(false); }}>
              {fixtures.claims.map((claim) => <option value={claim.id} key={claim.id}>{claim.verdict} — {claim.text}</option>)}
            </select>
          </label>
          <label>Human verdict
            <select value={verdict} onChange={(event) => { setVerdict(event.target.value); setSaved(false); }}>
              {VERDICTS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label>Reviewer explanation
            <textarea rows="5" value={explanation} onChange={(event) => { setExplanation(event.target.value); setSaved(false); }} />
          </label>
          {error && <div className="error-box">{error}</div>}
          {saved && <div className="success-box" role="status">Sample review saved to this demo session only.</div>}
          <button className="button" type="submit">Submit sample review</button>
        </form>
      </div>
    </>
  );
}

function DemoReport({ verified, reviews }) {
  const report = {
    mode: "DEMO — prepared illustrative data; not a live analysis",
    document: fixtures.document,
    verificationTriggered: verified,
    verdicts: verified ? fixtures.claims.map(({ id, text, verdict, explanation, limitations }) => ({ id, text, verdict, explanation, limitations })) : [],
    demoReviews: reviews,
    note: "Synthetic fixture content only. No database or external provider was used.",
  };

  function downloadJson() {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "anvexa-demo-report.json";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <>
      <DemoHeader eyebrow="Prepared export" title="Demonstration report" action={
        <>
          <button className="button secondary" onClick={downloadJson}>Download JSON</button>
          <button className="button" onClick={() => window.print()}>Print / Save as PDF</button>
        </>
      } />
      <p className="demo-callout">Use Print / Save as PDF and select “Save as PDF” in the browser print dialog for a PDF copy.</p>
      <article className="panel demo-report-preview">
        <span className="demo-label">DEMO REPORT · SYNTHETIC ILLUSTRATION</span>
        <h2>{fixtures.document.title}</h2>
        <p>{fixtures.document.classification}</p>
        <p><strong>Verification workflow:</strong> {verified ? "Prepared fixture results displayed; no live verification performed." : "Not triggered in this demo session."}</p>
        <h3>Verdict examples</h3>
        {VERDICTS.map((verdict) => {
          const claim = fixtures.claims.find((item) => item.verdict === verdict);
          return <div className="demo-report-row" key={verdict}><strong>{verdict}</strong><span>{claim.text}</span></div>;
        })}
        <h3>Human review submissions</h3>
        {reviews.length ? reviews.map((review) => (
          <div className="demo-report-row" key={review.id}><strong>{review.verdict}</strong><span>{review.explanation}</span></div>
        )) : <p>No sample review has been submitted in this demo session.</p>}
        <p className="demo-footnote">Prepared, synthetic demonstration data only. No database, Gemini, or external research service was used.</p>
      </article>
    </>
  );
}

export default function DemoMode() {
  const location = useLocation();
  const navigate = useNavigate();
  const section = location.pathname.replace(/^\/demo\/?/, "").split("/")[0] || "dashboard";
  const [verified, setVerified] = useState(() => sessionStorage.getItem(VERIFIED_STORAGE_KEY) === "true");
  const [reviews, setReviews] = useState(readReviews);

  function runDemo() {
    sessionStorage.setItem(VERIFIED_STORAGE_KEY, "true");
    setVerified(true);
  }

  function saveReview(review) {
    const nextReviews = [review, ...reviews];
    sessionStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(nextReviews));
    setReviews(nextReviews);
  }

  function exitDemo() {
    sessionStorage.removeItem(REVIEW_STORAGE_KEY);
    sessionStorage.removeItem(VERIFIED_STORAGE_KEY);
    navigate("/");
  }

  let content;
  switch (section) {
    case "dashboard":
      content = <DemoDashboard />;
      break;
    case "document":
      content = <DemoDocument />;
      break;
    case "claims":
      content = <DemoClaims />;
      break;
    case "sources":
      content = <DemoSources />;
      break;
    case "verification":
      content = <DemoVerification verified={verified} onRun={runDemo} />;
      break;
    case "review":
      content = <DemoReview reviews={reviews} onSave={saveReview} />;
      break;
    case "report":
      content = <DemoReport verified={verified} reviews={reviews} />;
      break;
    default:
      return <Navigate to="/demo/dashboard" replace />;
  }

  return (
    <div className="demo-app">
      <div className="demo-disclaimer" role="status">{fixtures.notice}</div>
      <div className="demo-layout">
        <aside className="demo-sidebar">
          <Link className="brand-link" to="/demo/dashboard">
            <div className="brand"><div className="brand-mark">A</div><div><strong>ANVEXA</strong><span> Demo workspace</span></div></div>
          </Link>
          <nav aria-label="Demo navigation">
            {NAV_ITEMS.map(([path, label]) => (
              <Link className={section === path ? "demo-nav-link active" : "demo-nav-link"} to={`/demo/${path}`} key={path}>{label}</Link>
            ))}
          </nav>
          <button className="demo-exit" onClick={exitDemo}>Exit demo</button>
        </aside>
        <main className="demo-main">{content}</main>
      </div>
    </div>
  );
}

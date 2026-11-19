import React, { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import api, { errorMessage } from "./api";
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "./authStorage";

const verdictLabels = [
  "SUPPORTED",
  "PARTLY_SUPPORTED",
  "UNSUPPORTED",
  "CONTRADICTORY",
  "POSSIBLY_OUTDATED",
  "NEEDS_REVIEW",
];

function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api.get("/auth/me")
      .then((response) => setUser(response.data))
      .catch(() => {
        clearAuthTokens();
      })
      .finally(() => setLoading(false));
  }, []);
  return { user, loading };
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-state">Loading account...</div>;
  return user ? children : <Navigate to="/login" replace />;
}

function Logo({ compact = false }) {
  return (
    <div className="brand">
      <div className="brand-mark">A</div>
      {!compact && <div><strong>ANVEXA</strong><span> Research Intelligence</span></div>}
    </div>
  );
}

function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(null);
  useEffect(() => {
    api.get("/auth/me").then((response) => setUser(response.data)).catch(() => {});
  }, []);
  async function logout() {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) await api.post("/auth/logout", { refresh_token: refreshToken });
    } catch (_) {}
    clearAuthTokens();
    navigate("/login");
  }
  const links = [
    ["/app/dashboard", "Dashboard"],
    ["/app/documents", "Documents"],
    ["/app/sources", "Sources"],
    ["/app/reviews", "Human review"],
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand-link" to="/app/dashboard"><Logo /></Link>
        <nav>
          {links.map(([path, label]) => (
            <Link className={location.pathname.startsWith(path) ? "nav-link active" : "nav-link"} to={path} key={path}>
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-user">
          <div className="avatar">{user?.full_name?.[0] || "U"}</div>
          <div><strong>{user?.full_name || "Account"}</strong><span>{user?.role || ""}</span></div>
          <button className="icon-button" onClick={logout} title="Logout">↗</button>
        </div>
      </aside>
      <main className="main-area">{children}</main>
    </div>
  );
}

function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <Logo />
        <div className="landing-actions">
          <Link className="text-link" to="/login">Sign in</Link>
          <Link className="button" to="/register">Create account</Link>
        </div>
      </header>
      <section className="hero">
        <p className="eyebrow">Evidence traceability for academic claims</p>
        <h1>Turn research documents into <em>explainable evidence.</em></h1>
        <p>Extract claims, retrieve sources, map evidence, and preserve every decision from AI analysis through human review.</p>
        <div className="hero-actions">
          <Link className="button" to="/register">Start verification</Link>
          <Link className="button secondary" to="/login">Open workspace</Link>
        </div>
      </section>
      <section className="capability-grid">
        {[
          ["01", "Trace claims", "Preserve exact wording, page, and section context."],
          ["02", "Map evidence", "Keep citations and source passages linked to claims."],
          ["03", "Explain verdicts", "Separate AI analysis from human judgment."],
          ["04", "Export reports", "Produce structured JSON and readable PDF reports."],
        ].map(([number, title, text]) => (
          <article className="capability" key={number}>
            <span>{number}</span><h3>{title}</h3><p>{text}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

function AuthPage({ mode }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await api.post("/auth/register", {
          email: form.email,
          full_name: form.full_name,
          password: form.password,
        });
        navigate("/login");
        return;
      }
      const response = await api.post("/auth/login", {
        email: form.email,
        password: form.password,
      });
      setAccessToken(response.data.access_token);
      setRefreshToken(response.data.refresh_token);
      navigate("/app/dashboard");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <Link className="auth-brand" to="/"><Logo /></Link>
      <form className="auth-card" onSubmit={submit}>
        <p className="eyebrow">{mode === "register" ? "New workspace" : "Welcome back"}</p>
        <h1>{mode === "register" ? "Create your account" : "Sign in"}</h1>
        {mode === "register" && (
          <label>Full name<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></label>
        )}
        <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label>Password<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} /></label>
        {error && <div className="error-box">{error}</div>}
        <button className="button full" disabled={busy}>{busy ? "Please wait..." : mode === "register" ? "Create account" : "Sign in"}</button>
        <p className="auth-switch">
          {mode === "register" ? "Already have an account?" : "New to ANVEXA?"}
          <Link to={mode === "register" ? "/login" : "/register"}>{mode === "register" ? " Sign in" : " Create account"}</Link>
        </p>
      </form>
    </div>
  );
}

function PageHeader({ eyebrow, title, actions }) {
  return (
    <header className="page-header">
      <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>
      {actions && <div className="header-actions">{actions}</div>}
    </header>
  );
}

function Loading({ text = "Loading..." }) { return <div className="page-state"><span className="spinner" />{text}</div>; }
function Empty({ title, text }) { return <div className="empty-state"><h3>{title}</h3><p>{text}</p></div>; }
function ErrorBox({ error }) { return error ? <div className="error-box">{error}</div> : null; }

function Dashboard() {
  const [data, setData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api.get("/analytics/overview"),
      api.get("/documents", { params: { page: 1, per_page: 5, sort_order: "desc" } }),
    ]).then(([analytics, docs]) => {
      setData(analytics.data);
      setDocuments(docs.data.documents || []);
    }).catch((err) => setError(errorMessage(err)));
  }, []);
  if (error) return <><PageHeader eyebrow="Overview" title="Dashboard" /><ErrorBox error={error} /></>;
  if (!data) return <Loading />;
  const cards = [
    ["Uploaded documents", data.documents_uploaded],
    ["Processed documents", data.documents_processed],
    ["Extracted claims", data.claims_extracted],
    ["Detected citations", data.citations_detected],
    ["Retrieved sources", data.sources_retrieved],
    ["Evidence passages", data.evidence_passages_extracted],
    ["Verified claims", data.claims_verified],
    ["Awaiting review", data.claims_awaiting_review],
  ];
  return (
    <>
      <PageHeader eyebrow="Workspace" title="Dashboard" actions={<Link className="button" to="/app/documents">Manage documents</Link>} />
      <div className="metric-grid">
        {cards.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}
      </div>
      <section className="panel">
        <div className="panel-heading"><h2>Recent documents</h2><Link to="/app/documents">View all</Link></div>
        {documents.length === 0 ? <Empty title="No documents yet" text="Upload an academic document to begin verification." /> :
          <div className="table-wrap"><table><thead><tr><th>Document</th><th>Status</th><th>Uploaded</th></tr></thead><tbody>
            {documents.map((document) => (
              <tr key={document.id}><td><Link to={`/app/documents/${document.id}`}>{document.filename}</Link></td><td><span className="status">{document.processing_status}</span></td><td>{new Date(document.uploaded_at).toLocaleDateString()}</td></tr>
            ))}
          </tbody></table></div>}
      </section>
    </>
  );
}

function Documents() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState("");
  async function load() {
    setLoading(true);
    try {
      const response = await api.get("/documents", { params: { page: 1, per_page: 50, sort_order: "desc" } });
      setDocuments(response.data.documents || []);
    } catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) {
      setError("Only PDF and DOCX files are supported.");
      return;
    }
    setUploading(true);
    setError("");
    setSuccess("");
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post("/documents/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      setSuccess("Document uploaded successfully.");
      await load();
    } catch (err) { setError(errorMessage(err)); }
    finally { setUploading(false); event.target.value = ""; }
  }
  return (
    <>
      <PageHeader eyebrow="Document library" title="Documents" actions={
        <label className="button file-button">{uploading ? "Uploading..." : "Upload document"}<input type="file" accept=".pdf,.docx" onChange={upload} disabled={uploading} /></label>
      } />
      <ErrorBox error={error} />
      {success && <div className="success-box">{success}</div>}
      {loading ? <Loading /> : documents.length === 0 ? <Empty title="No documents" text="Upload a PDF or DOCX academic document to begin." /> :
        <div className="document-grid">
          {documents.map((document) => (
            <Link className="document-card" to={`/app/documents/${document.id}`} key={document.id}>
              <div className="document-icon">PDF</div>
              <div><h3>{document.filename}</h3><p>{document.file_type}</p><span className="status">{document.processing_status}</span></div>
            </Link>
          ))}
        </div>}
    </>
  );
}

function DocumentDetail() {
  const { id } = useParams();
  const [document, setDocument] = useState(null);
  const [claims, setClaims] = useState([]);
  const [citations, setCitations] = useState([]);
  const [sources, setSources] = useState([]);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [success, setSuccess] = useState("");
  async function load() {
    try {
      const [documentResponse, claimResponse, citationResponse, sourceResponse, reportResponse] = await Promise.allSettled([
        api.get(`/documents/${id}`),
        api.get(`/documents/${id}/claims`, { params: { page: 1, per_page: 100 } }),
        api.get(`/documents/${id}/citations`, { params: { page: 1, per_page: 100 } }),
        api.get(`/documents/${id}/sources`, { params: { page: 1, per_page: 100 } }),
        api.get(`/documents/${id}/report`),
      ]);
      if (documentResponse.status === "fulfilled") setDocument(documentResponse.value.data);
      if (claimResponse.status === "fulfilled") setClaims(claimResponse.value.data.claims || []);
      if (citationResponse.status === "fulfilled") setCitations(citationResponse.value.data.citations || []);
      if (sourceResponse.status === "fulfilled") setSources(sourceResponse.value.data.sources || []);
      if (reportResponse.status === "fulfilled") setReport(reportResponse.value.data);
    } catch (err) { setError(errorMessage(err)); }
  }
  useEffect(() => { load(); }, [id]);
  async function run(label, path, method = "post") {
    setBusy(label);
    setError("");
    setSuccess("");
    try {
      await api[method](path);
      setSuccess(`${label} completed successfully.`);
      await load();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(""); }
  }
  async function download(format) {
    try {
      const response = await api.get(`/documents/${id}/report/${format}`, { responseType: "blob" });
      const blob = new Blob([response.data], { type: format === "pdf" ? "application/pdf" : "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `document-${id}-report.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(errorMessage(err)); }
  }
  if (!document) return <Loading />;
  const workflow = [
    ["Parse document", `/documents/${id}/parse`, "post"],
    ["Extract claims", `/documents/${id}/extract-claims`, "post"],
    ["Detect citations", `/documents/${id}/detect-citations`, "post"],
    ["Retrieve sources", `/documents/${id}/retrieve-sources`, "post"],
    ["Extract evidence", `/documents/${id}/extract-evidence`, "post"],
    ["Verify claims", `/documents/${id}/verify`, "post"],
    ["Classify verdicts", `/documents/${id}/classify-verdicts`, "post"],
  ];
  return (
    <>
      <PageHeader eyebrow="Document workspace" title={document.filename} actions={
        <><button className="button secondary" onClick={() => download("json")}>JSON report</button><button className="button" onClick={() => download("pdf")}>PDF report</button></>
      } />
      <ErrorBox error={error} />
      {success && <div className="success-box">{success}</div>}
      <div className="status-strip">
        <span>Processing</span><strong>{document.processing_status}</strong>
        <span>Claims</span><strong>{claims.length}</strong>
        <span>Citations</span><strong>{citations.length}</strong>
        <span>Sources</span><strong>{sources.length}</strong>
      </div>
      <section className="panel">
        <div className="panel-heading"><h2>Verification workflow</h2></div>
        <div className="workflow">
          {workflow.map(([label, path]) => (
            <button key={label} className="workflow-step" disabled={!!busy} onClick={() => run(label, path)}>
              <span>{busy === label ? "Running..." : label}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading"><h2>Claims</h2><span>{claims.length} records</span></div>
        {claims.length === 0 ? <Empty title="No claims extracted" text="Run claim extraction after parsing this document." /> :
          <div className="claim-list">
            {claims.map((claim) => (
              <Link className="claim-row" to={`/app/claims/${claim.id}`} key={claim.id}>
                <div><strong>{claim.claim_text || claim.original_sentence}</strong><p>Page {claim.page_number || "—"} · {claim.section_heading || "Section unavailable"}</p></div>
                <span className="status">{claim.claim_type}</span>
              </Link>
            ))}
          </div>}
      </section>
    </>
  );
}

function ClaimWorkspace() {
  const { id } = useParams();
  const [claim, setClaim] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [sources, setSources] = useState([]);
  const [verification, setVerification] = useState(null);
  const [classification, setClassification] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.allSettled([
      api.get(`/claims/${id}`),
      api.get(`/claims/${id}/evidence`),
      api.get(`/claims/${id}/sources`),
      api.get(`/claims/${id}/verification`),
      api.get(`/claims/${id}/verdict`),
    ]).then((responses) => {
      if (responses[0].status === "fulfilled") setClaim(responses[0].value.data);
      const evidenceResponse = responses[1];
      const sourceResponse = responses[2];
      const verificationResponse = responses[3];
      const classificationResponse = responses[4];
      if (evidenceResponse.status === "fulfilled") setEvidence(evidenceResponse.value.data.evidence || []);
      if (sourceResponse.status === "fulfilled") setSources(sourceResponse.value.data || []);
      if (verificationResponse.status === "fulfilled") setVerification(verificationResponse.value.data);
      if (classificationResponse.status === "fulfilled") setClassification(classificationResponse.value.data);
    }).catch((err) => setError(errorMessage(err)));
  }, [id]);
  return (
    <>
      <PageHeader eyebrow="Claim workspace" title="Evidence analysis" />
      <ErrorBox error={error} />
      <div className="workspace-grid">
        <section className="panel">
          <div className="panel-heading"><h2>Claim</h2><span>{id}</span></div>
          {claim && <h3 className="exact-claim">{claim.claim_text || claim.original_sentence}</h3>}
          {classification ? (
            <>
              <h3>{classification.claim_id}</h3>
              <div className="verdict-row">
                <span>AI verdict</span><strong>{classification.ai_verdict}</strong>
                <span>Final verdict</span><strong>{classification.final_verdict}</strong>
              </div>
              <p>{verification?.explanation || "Verification explanation unavailable."}</p>
              {classification.limitations?.length > 0 && <div><h4>Limitations</h4><ul>{classification.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
            </>
          ) : <Empty title="No classified verdict" text="Run claim verification and verdict classification first." />}
        </section>
        <aside className="panel evidence-panel">
          <div className="panel-heading"><h2>Evidence</h2><span>{evidence.length} passages</span></div>
          {evidence.length === 0 ? <Empty title="No evidence" text="Evidence extraction has not returned passages for this claim." /> :
            evidence.map((item) => (
              <article className="evidence-card" key={item.evidence_id}>
                <div><span className="status">{item.content_type}</span>{item.doi && <small>DOI {item.doi}</small>}</div>
                <p>{item.evidence_text}</p>
                <footer>{item.publication_title} · {item.section_name || "Section unavailable"} · Page {item.page_number || "—"}</footer>
              </article>
            ))}
        </aside>
      </div>
      {sources.length > 0 && <section className="panel"><div className="panel-heading"><h2>Retrieved sources</h2></div><div className="source-grid">{sources.map((source) => (
        <article className="source-card" key={source.id}><h3>{source.title}</h3><p>{source.authors?.join(", ") || "Authors unavailable"}</p><p>{source.publication_year || "Year unavailable"} · {source.doi || "No DOI"}</p>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Open source</a>}</article>
      ))}</div></section>}
    </>
  );
}

function Reviews() {
  const [reviews, setReviews] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [verdict, setVerdict] = useState("NEEDS_REVIEW");
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  async function load() {
    try {
      const response = await api.get("/reviews/queue", { params: { page: 1, per_page: 50 } });
      setReviews(response.data.reviews || []);
    } catch (err) { setError(errorMessage(err)); }
  }
  useEffect(() => { load(); }, []);
  async function open(review) {
    setError("");
    try {
      const response = await api.get(`/reviews/${review.review_id}`);
      setSelected(response.data);
    } catch (err) { setError(errorMessage(err)); }
  }
  async function submit() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/reviews/${selected.review_id}/submit`, { verdict, explanation });
      setSuccess("Human verdict submitted successfully.");
      await load();
      setSelected(null);
      setExplanation("");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function investigate() {
    if (!selected) return;
    if (!explanation.trim() || explanation.trim().length < 10) {
      setError("Reviewer explanation is required (at least 10 characters).");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/reviews/${selected.review_id}/request-investigation`, {
        explanation: explanation || "Further investigation is required to assess this claim.",
      });
      setSuccess("Further investigation requested successfully.");
      await load();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return (
    <>
      <PageHeader eyebrow="Human review" title="Review queue" />
      <ErrorBox error={error} />
      {success && <div className="success-box">{success}</div>}
      <div className="review-layout">
        <section className="panel review-list-panel">
          {reviews.length === 0 ? <Empty title="No cases awaiting review" text="AI and classified cases that require review will appear here." /> :
            reviews.map((review) => (
              <button className="review-list-item" key={review.review_id} onClick={() => open(review)}>
                <span className="status">{review.ai_verdict}</span>
                <strong>{review.claim_text}</strong>
                <small>{review.document_title}</small>
              </button>
            ))}
        </section>
        {selected && <section className="panel review-detail">
          <p className="eyebrow">{selected.document_title}</p>
          <h2>{selected.claim_text}</h2>
          <div className="verdict-row"><span>AI verdict</span><strong>{selected.ai_verdict}</strong></div>
          <p>{selected.ai_explanation}</p>
          <h3>Supporting evidence</h3>
          {selected.supporting_evidence.length === 0 ? <p className="muted">No supporting evidence was linked.</p> :
            selected.supporting_evidence.map((item) => <article className="evidence-card" key={item.evidence_id}><p>{item.evidence_text}</p><footer>{item.publication_title} · {item.doi || "No DOI"}</footer></article>)}
          <h3>Contradicting evidence</h3>
          {selected.contradicting_evidence.length === 0 ? <p className="muted">No contradicting evidence was linked.</p> :
            selected.contradicting_evidence.map((item) => <article className="evidence-card" key={item.evidence_id}><p>{item.evidence_text}</p><footer>{item.publication_title}</footer></article>)}
          <label>Human verdict
            <select value={verdict} onChange={(event) => setVerdict(event.target.value)}>
              {verdictLabels.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label>Reviewer explanation<textarea rows="5" value={explanation} onChange={(event) => setExplanation(event.target.value)} /></label>
          <div className="header-actions">
            <button className="button secondary" disabled={busy} onClick={investigate}>Request investigation</button>
            <button className="button" disabled={busy} onClick={submit}>Submit human verdict</button>
          </div>
        </section>}
      </div>
    </>
  );
}

function Settings() {
  const [user, setUser] = useState(null);
  useEffect(() => { api.get("/auth/me").then((response) => setUser(response.data)).catch(() => {}); }, []);
  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" />
      <section className="panel settings-card">
        <h2>Profile</h2>
        {user ? <><p><strong>Name</strong><span>{user.full_name}</span></p><p><strong>Email</strong><span>{user.email}</span></p><p><strong>Role</strong><span>{user.role}</span></p></> : <Loading />}
      </section>
    </>
  );
}

function SourcesExplorer() {
  const [documents, setDocuments] = useState([]);
  const [sources, setSources] = useState([]);
  const [citations, setCitations] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get("/documents", { params: { page: 1, per_page: 100 } })
      .then(async (response) => {
        setDocuments(response.data.documents || []);
        const foundSources = [];
        const foundCitations = [];
        for (const document of response.data.documents || []) {
          const [sourceResponse, citationResponse] = await Promise.allSettled([
            api.get(`/documents/${document.id}/sources`, { params: { page: 1, per_page: 100 } }),
            api.get(`/documents/${document.id}/citations`, { params: { page: 1, per_page: 100 } }),
          ]);
          if (sourceResponse.status === "fulfilled") foundSources.push(...(sourceResponse.value.data.sources || []).map((item) => ({ ...item, document_id: document.id })));
          if (citationResponse.status === "fulfilled") foundCitations.push(...(citationResponse.value.data.citations || []).map((item) => ({ ...item, document_id: document.id })));
        }
        setSources(foundSources);
        setCitations(foundCitations);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);
  return (
    <>
      <PageHeader eyebrow="Traceability" title="Citation and source explorer" />
      <ErrorBox error={error} />
      <div className="workspace-grid">
        <section className="panel">
          <div className="panel-heading"><h2>Citations</h2><span>{citations.length} records</span></div>
          {citations.length === 0 ? <Empty title="No citations" text="Run citation detection for uploaded documents." /> :
            citations.map((citation) => (
              <article className="evidence-card" key={`${citation.document_id}-${citation.id}`}>
                <strong>{citation.original_marker || citation.citation_text}</strong>
                <p>{citation.publication_title || "Publication title unavailable"}</p>
                <footer>{citation.citation_type} · DOI {citation.doi || "unavailable"} · Page {citation.page_number || "—"}</footer>
              </article>
            ))}
        </section>
        <aside className="panel">
          <div className="panel-heading"><h2>Retrieved sources</h2><span>{sources.length} records</span></div>
          {sources.length === 0 ? <Empty title="No sources" text="Run source retrieval after citation detection." /> :
            sources.map((source) => (
              <article className="source-card" key={`${source.document_id}-${source.id}`}>
                <h3>{source.title}</h3>
                <p>{source.authors?.join(", ") || "Authors unavailable"}</p>
                <p>{source.publication_year || "Year unavailable"} · {source.doi || "No DOI"}</p>
                {source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Open source</a>}
              </article>
            ))}
        </aside>
      </div>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/app" element={<Protected><Layout><Navigate to="/app/dashboard" replace /></Layout></Protected>} />
      <Route path="/app/dashboard" element={<Protected><Layout><Dashboard /></Layout></Protected>} />
      <Route path="/app/documents" element={<Protected><Layout><Documents /></Layout></Protected>} />
      <Route path="/app/documents/:id" element={<Protected><Layout><DocumentDetail /></Layout></Protected>} />
      <Route path="/app/claims/:id" element={<Protected><Layout><ClaimWorkspace /></Layout></Protected>} />
      <Route path="/app/reviews" element={<Protected><Layout><Reviews /></Layout></Protected>} />
      <Route path="/app/sources" element={<Protected><Layout><SourcesExplorer /></Layout></Protected>} />
      <Route path="/app/settings" element={<Protected><Layout><Settings /></Layout></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

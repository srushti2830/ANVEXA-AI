import React, { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import api, { errorMessage } from "./api";

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
    const token = localStorage.getItem("anvexa_access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api.get("/auth/me")
      .then((response) => setUser(response.data))
      .catch(() => {
        localStorage.removeItem("anvexa_access_token");
        localStorage.removeItem("anvexa_refresh_token");
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
    const refreshToken = localStorage.getItem("anvexa_refresh_token");
    try {
      if (refreshToken) await api.post("/auth/logout", { refresh_token: refreshToken });
    } catch (_) {}
    localStorage.removeItem("anvexa_access_token");
    localStorage.removeItem("anvexa_refresh_token");
    navigate("/login");
  }
  const links = [
    ["/app/dashboard", "Dashboard"],
    ["/app/documents", "Documents"],
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
      localStorage.setItem("anvexa_access_token", response.data.access_token);
      localStorage.setItem("anvexa_refresh_token", response.data.refresh_token);
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

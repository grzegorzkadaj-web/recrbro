"use client";

import {
  useAgentContext,
  useFrontendTool,
} from "@copilotkit/react-core/v2";
import {
  ChangeEvent,
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { z } from "zod";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const SESSION_KEY = "recrbro_session";

type Plan = "free" | "premium";
type User = {
  id: number;
  name: string;
  email: string;
  plan: Plan;
  result_limit: number;
  monthly_budget_pln: number;
  tracked_cost_usd: number;
};
type Profile = {
  user_id: number;
  core_skills: string[];
  other_skills: string[];
  languages: string[];
  location: string;
  work_modes: string[];
  minimum_salary: number | null;
  contract_types: string[];
  excluded_companies: string[];
  cv_filename: string | null;
};
type JobOffer = {
  result_type: "job" | "collection";
  title: string;
  company: string;
  url: string;
  summary: string;
  score: number;
  matched_skills: string[];
  match_reasons: string[];
};
type Usage = { input_tokens: number; output_tokens: number; cost_usd: number };
type SearchJob = {
  id: number;
  status: "queued" | "running" | "complete" | "failed";
  requested_results: number;
  offers: JobOffer[];
  warning: string | null;
  error: string | null;
  available_at: string;
};

const emptyProfile: Profile = {
  user_id: 0,
  core_skills: [],
  other_skills: [],
  languages: [],
  location: "",
  work_modes: [],
  minimum_salary: null,
  contract_types: [],
  excluded_companies: [],
  cv_filename: null,
};

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

async function api<T>(
  path: string,
  token?: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function Logo() {
  return (
    <span className="logo" aria-hidden="true">
      <span>R</span>
      <i />
    </span>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ token: string; user: User }>(
        mode === "login" ? "/api/auth/login" : "/api/auth/register",
        undefined,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: form.get("name"),
            email: form.get("email"),
            password: form.get("password"),
          }),
        },
      );
      onAuthenticated(result.token, result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authShell">
      <section className="authIntro">
        <a className="brand" href="#" aria-label="RecrBro home">
          <Logo />
          <span>RecrBro</span>
        </a>
        <div>
          <p className="eyebrow">Your recruiting bro</p>
          <h1>Find work that fits.</h1>
          <p className="heroCopy">
            Turn your experience and preferences into a verified, ranked
            shortlist instead of another endless job-board scroll.
          </p>
        </div>
        <p className="authTrust">Live LinkedIn discovery. Active-offer checks. Your profile stays under your account.</p>
      </section>
      <section className="authPanel">
        <div className="authCard">
          <p className="sectionNumber">{mode === "login" ? "Welcome back" : "Create your profile"}</p>
          <h2>{mode === "login" ? "Sign in to RecrBro" : "Start searching smarter"}</h2>
          <form onSubmit={submit}>
            {mode === "register" && (
              <label><span>Name</span><input name="name" autoComplete="name" required minLength={2} /></label>
            )}
            <label><span>Email</span><input name="email" type="email" autoComplete="email" required /></label>
            <label><span>Password</span><input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={10} /></label>
            {error && <div className="notice compact" role="alert">{error}</div>}
            <button className="primaryButton" disabled={busy}>
              {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create free account"}
              <span>→</span>
            </button>
          </form>
          <div className="divider"><span>or</span></div>
          <a className="googleButton" href={`${API_URL}/api/auth/google/start`}>
            Continue with Google
          </a>
          <button className="textButton" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
          </button>
        </div>
      </section>
    </main>
  );
}

function Dashboard({
  initialUser,
  token,
  onLogout,
}: {
  initialUser: User;
  token: string;
  onLogout: () => void;
}) {
  const [user, setUser] = useState(initialUser);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [usage, setUsage] = useState<Usage>({ input_tokens: 0, output_tokens: 0, cost_usd: 0 });
  const [offers, setOffers] = useState<JobOffer[]>([]);
  const [maxResults, setMaxResults] = useState(Math.min(10, user.result_limit));
  const [status, setStatus] = useState("Loading your profile...");
  const [warning, setWarning] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [searchJob, setSearchJob] = useState<SearchJob | null>(null);
  const [progressStep, setProgressStep] = useState(0);
  const progressMessages = useMemo(() => [
    "Preparing focused search queries",
    "Discovering LinkedIn job pages",
    "Checking links and active status",
    "Validating location eligibility",
    "Ranking your strongest matches",
  ], []);

  const refreshAccount = useCallback(async () => {
    const [loadedUser, loadedProfile, loadedUsage] = await Promise.all([
      api<User>("/api/me", token),
      api<Profile>("/api/profile", token),
      api<Usage>("/api/usage", token),
    ]);
    setUser(loadedUser);
    setProfile(loadedProfile);
    setUsage(loadedUsage);
  }, [token]);

  useEffect(() => {
    refreshAccount()
      .then(() => setStatus("Profile ready"))
      .catch((error: Error) => setWarning(error.message))
      .finally(() => setBusy(false));
  }, [refreshAccount]);

  useEffect(() => {
    if (!busy || searchJob?.status === "queued") return;
    const timer = window.setInterval(
      () => setProgressStep((step) => Math.min(step + 1, progressMessages.length - 1)),
      2600,
    );
    return () => window.clearInterval(timer);
  }, [busy, progressMessages.length, searchJob?.status]);

  useEffect(() => {
    if (searchJob?.status !== "queued" && searchJob?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<SearchJob>(`/api/searches/${searchJob.id}`, token);
        setSearchJob(latest);
        if (latest.status === "complete") {
          setOffers(latest.offers);
          setWarning(latest.warning);
          setStatus(`Found ${latest.offers.length} ranked matches`);
          setBusy(false);
        } else if (latest.status === "failed") {
          setWarning(latest.error ?? "The scheduled search failed.");
          setStatus("Search failed");
          setBusy(false);
        }
      } catch (error) {
        setWarning(error instanceof Error ? error.message : "Could not refresh search.");
      }
    }, 10000);
    return () => window.clearInterval(timer);
  }, [searchJob?.id, searchJob?.status, token]);

  useAgentContext({
    description: "Current RecrBro account, profile, requested result count, and visible job matches.",
    value: { user, profile, requestedResults: maxResults, visibleOffers: offers },
  });

  useFrontendTool({
    name: "updateSearchCriteria",
    description: "Update visible search criteria. The user still saves changes explicitly.",
    parameters: z.object({
      coreSkills: z.array(z.string()).optional(),
      location: z.string().optional(),
    }),
    handler: async ({ coreSkills, location }) => {
      setProfile((current) => ({ ...current, core_skills: coreSkills ?? current.core_skills, location: location ?? current.location }));
      return "Updated the visible criteria for review.";
    },
  }, []);

  function updateField<K extends keyof Profile>(field: K, value: Profile[K]) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  async function saveProfile() {
    setBusy(true);
    setWarning(null);
    setStatus("Saving your profile...");
    try {
      const { user_id: _, cv_filename: __, ...payload } = profile;
      const savedProfile = await api<Profile>("/api/profile", token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setProfile(savedProfile);
      setStatus("Profile saved");
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "Could not save profile.");
      setStatus("Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadCv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setWarning(null);
    setStatus("Reading and analyzing your CV...");
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api<{ profile: Profile; analysis_mode: "ai" | "local-fallback"; warning: string | null }>("/api/cv", token, { method: "POST", body: form });
      setProfile(result.profile);
      setWarning(result.warning);
      setStatus(result.analysis_mode === "ai" ? "CV analyzed with AI" : "CV parsed locally");
      setUsage(await api<Usage>("/api/usage", token));
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "CV analysis failed.");
      setStatus("CV analysis failed");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function runSearch() {
    setBusy(true);
    setOffers([]);
    setWarning(null);
    setProgressStep(0);
    setSearchJob(null);
    setStatus("Preparing your search...");
    try {
      const { user_id: _, cv_filename: __, ...payload } = profile;
      const savedProfile = await api<Profile>("/api/profile", token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setProfile(savedProfile);

      const job = await api<SearchJob>("/api/searches", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_results: maxResults }),
      });
      setSearchJob(job);
      if (job.status === "complete") {
        setOffers(job.offers);
        setWarning(job.warning);
        setStatus(`Found ${job.offers.length} ranked matches`);
        setBusy(false);
      } else {
        setStatus(`Queued for ${new Date(job.available_at).toLocaleString()}`);
      }
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "Search failed.");
      setStatus("Search failed");
      setBusy(false);
    }
  }

  async function upgrade(method: "przelewy24" | "blik") {
    setBusy(true);
    try {
      const result = await api<{ redirect_url: string }>("/api/payments/checkout", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method }),
      });
      window.location.assign(result.redirect_url);
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "Checkout is unavailable.");
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top"><Logo /><span>RecrBro</span></a>
        <div className="userControl">
          <span className={`planBadge ${user.plan}`}>{user.plan}</span>
          <span className="userName">{user.name}</span>
          <button className="textButton" onClick={onLogout}>Sign out</button>
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">Your focused job search</p>
          <h1>Less scrolling.<br />Better-fit roles.</h1>
          <p className="heroCopy">Shape your profile once. RecrBro discovers, verifies, and ranks live job pages around what matters most.</p>
        </div>
        <div className="statusCard" aria-live="polite">
          <span className={busy ? "pulse" : "statusDot"} />
          <div>
            <strong>{busy && searchJob?.status !== "queued" ? progressMessages[progressStep] : status}</strong>
            <small>{user.result_limit} results per search · ${usage.cost_usd.toFixed(4)} tracked AI cost</small>
          </div>
        </div>
      </section>

      {warning && <div className="notice" role="alert"><strong>Heads up</strong><span>{warning}</span><button onClick={() => setWarning(null)} aria-label="Dismiss notice">×</button></div>}

      <section className="workspace">
        <article className="panel profilePanel">
          <div className="panelHeading">
            <div><p className="sectionNumber">01</p><h2>Candidate profile</h2></div>
            <button className="secondaryButton" onClick={saveProfile} disabled={busy}>Save profile</button>
          </div>
          <div className="formGrid">
            <label className="wide"><span>Core skills</span><input value={profile.core_skills.join(", ")} onChange={(e) => updateField("core_skills", splitList(e.target.value))} placeholder="Python, FastAPI, SQL" /><small>Required matches and the strongest ranking signal.</small></label>
            <label><span>Location</span><input value={profile.location} onChange={(e) => updateField("location", e.target.value)} placeholder="Poland" /></label>
            <label><span>Minimum monthly salary</span><input type="number" min="0" value={profile.minimum_salary ?? ""} onChange={(e) => updateField("minimum_salary", e.target.value ? Number(e.target.value) : null)} placeholder="18000" /></label>
            <label><span>Work mode</span><input value={profile.work_modes.join(", ")} onChange={(e) => updateField("work_modes", splitList(e.target.value))} placeholder="remote, hybrid" /></label>
            <label><span>Contract type</span><input value={profile.contract_types.join(", ")} onChange={(e) => updateField("contract_types", splitList(e.target.value))} placeholder="B2B, employment" /></label>
            <label className="wide"><span>Languages</span><input value={profile.languages.join(", ")} onChange={(e) => updateField("languages", splitList(e.target.value))} placeholder="English, Polish" /></label>
            <label className="wide"><span>Other skills</span><input value={profile.other_skills.join(", ")} onChange={(e) => updateField("other_skills", splitList(e.target.value))} placeholder="Docker, Azure, mentoring" /></label>
            <label className="wide"><span>Companies to exclude</span><input value={profile.excluded_companies.join(", ")} onChange={(e) => updateField("excluded_companies", splitList(e.target.value))} placeholder="Company A, Company B" /></label>
          </div>
          <div className={`cvCard ${user.plan !== "premium" ? "locked" : ""}`}>
            <div><strong>Build from a CV</strong><span>{profile.cv_filename ? `Using ${profile.cv_filename}` : "Upload a PDF to extract skills and languages."}</span></div>
            <label className="uploadButton">{user.plan === "premium" ? "Choose PDF" : "Premium feature"}<input type="file" accept="application/pdf" disabled={busy || user.plan !== "premium"} onChange={uploadCv} /></label>
          </div>
        </article>

        <aside className="panel searchPanel">
          <p className="sectionNumber">02</p><h2>Start a search</h2>
          <p>Core skills shape discovery. Your remaining profile criteria refine ranking and eligibility.</p>
          <label><span>Maximum results</span><input type="range" min="1" max={user.result_limit} value={Math.min(maxResults, user.result_limit)} onChange={(e) => setMaxResults(Number(e.target.value))} /></label>
          <div className="resultCount"><strong>{Math.min(maxResults, user.result_limit)}</strong><span>offers</span></div>
          <button className="primaryButton" onClick={runSearch} disabled={busy}>{busy ? "Working..." : "Search LinkedIn"}<span>↗</span></button>
          <div className="planDetail"><span>Current plan</span><strong>{user.plan === "premium" ? "Premium" : "Free"}</strong><small>{user.plan === "premium" ? "Immediate results · up to 100 offers" : "Scheduled search · 5 offers · email delivery"}</small></div>
          {user.plan === "free" && <div className="upgradeBox"><strong>Go Premium · 50 PLN</strong><p>Immediate searches, CV analysis, and up to 100 results.</p><div><button onClick={() => upgrade("blik")} disabled={busy}>Pay with BLIK</button><button onClick={() => upgrade("przelewy24")} disabled={busy}>Przelewy24</button></div></div>}
        </aside>
      </section>

      <section className="resultsSection">
        <div className="resultsHeading"><div><p className="sectionNumber">03</p><h2>Ranked opportunities</h2></div>{offers.length > 0 && <span>{offers.length} verified LinkedIn pages</span>}</div>
        {searchJob?.status === "queued" ? (
          <div className="emptyState queuedState"><span>◷</span><h3>Your search is in the queue</h3><p>It will run after {new Date(searchJob.available_at).toLocaleString()}. Keep this page open for updates, or check your email later.</p></div>
        ) : offers.length === 0 ? (
          <div className="emptyState"><span>◎</span><h3>Your shortlist starts here</h3><p>Save your profile and run a search to see ranked job offers.</p></div>
        ) : (
          <div className="offerList">{offers.map((offer, index) => (
            <article className="offerCard" key={offer.url}>
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="offerBody"><div className="offerTitle"><div><p>{offer.company}</p><h3>{offer.title}</h3></div><div className="score"><strong>{Math.round(offer.score)}%</strong><span>match</span></div></div><p className="summary">{offer.summary}</p><div className="tags">{offer.match_reasons.map((reason) => <span key={reason}>{reason}</span>)}</div></div>
              <a className="openOffer" href={offer.url} target="_blank" rel="noreferrer">Open offer <span>↗</span></a>
            </article>
          ))}</div>
        )}
      </section>
      <footer><span>RecrBro · Recruiting help without the noise</span><span>Live discovery by Tavily · Assistant by CopilotKit</span></footer>
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<{ token: string; user: User } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const oauthToken = fragment.get("session");
    if (oauthToken) {
      localStorage.setItem(SESSION_KEY, oauthToken);
      history.replaceState(null, "", window.location.pathname);
    }
    const token = oauthToken ?? localStorage.getItem(SESSION_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    api<User>("/api/me", token)
      .then((user) => setSession({ token, user }))
      .catch(() => localStorage.removeItem(SESSION_KEY))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="loadingScreen"><Logo /><strong>Loading RecrBro...</strong></main>;
  if (!session) return <AuthScreen onAuthenticated={(token, user) => { localStorage.setItem(SESSION_KEY, token); setSession({ token, user }); }} />;
  return <Dashboard initialUser={session.user} token={session.token} onLogout={() => { void api<void>("/api/auth/session", session.token, { method: "DELETE" }); localStorage.removeItem(SESSION_KEY); setSession(null); }} />;
}

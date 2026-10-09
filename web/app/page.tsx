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
  useRef,
  useState,
} from "react";
import { z } from "zod";
import { BrandLogo, LogoMark } from "./brand-logo";
import { LegalFooter } from "./legal-footer";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
const SESSION_KEY = "recrbro_session";
const TURNSTILE_SCRIPT_ID = "cloudflare-turnstile-script";

type TurnstileApi = {
  render: (
    container: HTMLElement,
    options: {
      sitekey: string;
      action: string;
      callback: (token: string) => void;
      "error-callback": () => void;
      "expired-callback": () => void;
      "timeout-callback": () => void;
    },
  ) => string;
  remove: (widgetId: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

type Plan = "free" | "premium";
type WorkMode = "remote" | "on-site" | "hybrid";
type User = {
  id: number;
  name: string;
  email: string;
  plan: Plan;
  result_limit: number;
  monthly_budget_pln: number;
  tracked_cost_usd: number;
  credits_bought: number;
  available_credits: number;
};
type Profile = {
  user_id: number;
  core_skills: string[];
  other_skills: string[];
  languages: string[];
  location: string;
  work_modes: WorkMode[];
  minimum_salary: number | null;
  contract_types: string[];
  excluded_companies: string[];
  additional_limitations: string;
  cv_filename: string | null;
};
type JobOffer = {
  id: number;
  result_type: "job";
  title: string;
  company: string;
  url: string;
  summary: string;
  score: number;
  matched_skills: string[];
  match_reasons: string[];
  applied: boolean;
};
type Usage = {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  credits_bought: number;
  available_credits: number;
};

const COFFEE_OPTIONS = [
  { size: "small", price: "8 zł" },
  { size: "medium", price: "15 zł" },
  { size: "large", price: "25 zł" },
] as const;
type SearchJob = {
  id: number;
  status: "queued" | "running" | "complete" | "failed";
  requested_results: number;
  offers: JobOffer[];
  warning: string | null;
  error: string | null;
  available_at: string;
};
type SearchResults = {
  current: SearchJob | null;
  archival: JobOffer[];
};
type ListProfileField =
  | "core_skills"
  | "other_skills"
  | "languages"
  | "contract_types"
  | "excluded_companies";
type ListDrafts = Record<ListProfileField, string>;
type SearchProgressMessage = {
  title: string;
  detail: string;
};

const SEARCH_PROGRESS_MESSAGES: SearchProgressMessage[] = [
  {
    title: "Preparing focused search queries",
    detail: "Using your core skills, location, and preferences to target relevant roles.",
  },
  {
    title: "Searching live job sources",
    detail: "Looking across employer sites and job boards for individual offers.",
  },
  {
    title: "Opening candidate offer pages",
    detail: "Collecting the full job details instead of relying on search snippets.",
  },
  {
    title: "Checking links and active status",
    detail: "Removing expired, closed, redirected, and duplicate offers.",
  },
  {
    title: "Validating location and work mode",
    detail: "Checking each role against where and how you want to work.",
  },
  {
    title: "Comparing offers with your core skills",
    detail: "Giving the strongest weight to the experience you marked as essential.",
  },
  {
    title: "Reviewing your additional requirements",
    detail: "Checking contract, salary, exclusions, languages, and other priorities.",
  },
  {
    title: "Calculating match strength",
    detail: "Balancing matching points with important gaps for every verified offer.",
  },
  {
    title: "Sorting your strongest matches",
    detail: "Comparing qualified offers consistently before building your shortlist.",
  },
  {
    title: "Preparing your verified shortlist",
    detail: "Final checks are in progress. Complex searches can take a few minutes.",
  },
];

const RANKING_PROGRESS_START = 5;
const SEARCH_POLL_INTERVAL_MS = 2000;

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
  additional_limitations: "",
  cv_filename: null,
};

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function listDraftsFromProfile(profile: Profile): ListDrafts {
  return {
    core_skills: profile.core_skills.join(", "),
    other_skills: profile.other_skills.join(", "),
    languages: profile.languages.join(", "),
    contract_types: profile.contract_types.join(", "),
    excluded_companies: profile.excluded_companies.join(", "),
  };
}

function profileWithListDrafts(profile: Profile, drafts: ListDrafts): Profile {
  return {
    ...profile,
    core_skills: splitList(drafts.core_skills),
    other_skills: splitList(drafts.other_skills),
    languages: splitList(drafts.languages),
    contract_types: splitList(drafts.contract_types),
    excluded_companies: splitList(drafts.excluded_companies),
  };
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

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function TurnstileWidget({
  onToken,
  onError,
}: {
  onToken: (token: string | null) => void;
  onError: (message: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (window.turnstile) {
      setReady(true);
      return;
    }

    let script = document.getElementById(
      TURNSTILE_SCRIPT_ID,
    ) as HTMLScriptElement | null;
    const handleLoad = () => setReady(true);
    const handleError = () =>
      onError("CAPTCHA could not be loaded. Please refresh and try again.");

    if (!script) {
      script = document.createElement("script");
      script.id = TURNSTILE_SCRIPT_ID;
      script.src =
        "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener("load", handleLoad);
    script.addEventListener("error", handleError);
    return () => {
      script?.removeEventListener("load", handleLoad);
      script?.removeEventListener("error", handleError);
    };
  }, [onError]);

  useEffect(() => {
    if (
      !ready ||
      !window.turnstile ||
      !containerRef.current ||
      widgetIdRef.current
    ) {
      return;
    }
    widgetIdRef.current = window.turnstile.render(containerRef.current, {
      sitekey: TURNSTILE_SITE_KEY,
      action: "register",
      callback: (token) => onToken(token),
      "error-callback": () => {
        onToken(null);
        onError("CAPTCHA verification failed. Please try again.");
      },
      "expired-callback": () => onToken(null),
      "timeout-callback": () => onToken(null),
    });
    return () => {
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [onError, onToken, ready]);

  return <div className="turnstileContainer" ref={containerRef} />;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaVersion, setCaptchaVersion] = useState(0);
  const handleCaptchaToken = useCallback((token: string | null) => {
    setCaptchaToken(token);
    if (token) setError(null);
  }, []);
  const handleCaptchaError = useCallback((message: string) => {
    setError(message);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "register" && !captchaToken) {
      setError("Complete the CAPTCHA before creating your account.");
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const credentials = {
      email: form.get("email"),
      password: form.get("password"),
    };
    try {
      const result = await api<{ token: string; user: User }>(
        mode === "login" ? "/api/auth/login" : "/api/auth/register",
        undefined,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            mode === "login"
              ? credentials
              : {
                  ...credentials,
                  name: form.get("name"),
                  captcha_token: captchaToken,
                  terms_accepted: form.get("terms_accepted") === "on",
                  privacy_accepted: form.get("privacy_accepted") === "on",
                },
          ),
        },
      );
      onAuthenticated(result.token, result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
      if (mode === "register") {
        setCaptchaToken(null);
        setCaptchaVersion((version) => version + 1);
      }
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(mode === "login" ? "register" : "login");
    setError(null);
    setCaptchaToken(null);
    setCaptchaVersion((version) => version + 1);
  }

  return (
    <main className="authShell">
      <section className="authIntro">
        <a className="brand" href="#" aria-label="RecrBro home">
          <BrandLogo />
        </a>
        <div>
          <p className="eyebrow">Your recruiting bro</p>
          <h1>Find work that fits.</h1>
          <p className="heroCopy">
            Turn your experience and preferences into a verified, ranked
            shortlist instead of another endless job-board scroll.
          </p>
        </div>
        <div>
          <p className="authTrust">Live multi-source discovery. Active-offer checks. Your profile stays under your account.</p>
          <LegalFooter compact />
        </div>
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
            {mode === "register" && (
              <div className="consents">
                <label>
                  <input name="terms_accepted" type="checkbox" required />
                  <span>I accept the <a href="/terms" target="_blank" rel="noreferrer">Terms of Service</a>.</span>
                </label>
                <label>
                  <input name="privacy_accepted" type="checkbox" required />
                  <span>I have read the <a href="/privacy-policy" target="_blank" rel="noreferrer">Privacy Policy</a>.</span>
                </label>
              </div>
            )}
            {mode === "register" && TURNSTILE_SITE_KEY && (
              <TurnstileWidget
                key={captchaVersion}
                onToken={handleCaptchaToken}
                onError={handleCaptchaError}
              />
            )}
            {mode === "register" && !TURNSTILE_SITE_KEY && (
              <div className="notice compact" role="alert">
                Registration CAPTCHA is not configured.
              </div>
            )}
            {error && <div className="notice compact" role="alert">{error}</div>}
            <button
              className="primaryButton"
              disabled={
                busy ||
                (mode === "register" &&
                  (!TURNSTILE_SITE_KEY || !captchaToken))
              }
            >
              {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create free account"}
              <span>→</span>
            </button>
          </form>
          <button className="textButton" onClick={switchMode}>
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
  const [listDrafts, setListDrafts] = useState<ListDrafts>(
    listDraftsFromProfile(emptyProfile),
  );
  const [usage, setUsage] = useState<Usage>({
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    credits_bought: user.credits_bought,
    available_credits: user.available_credits,
  });
  const [offers, setOffers] = useState<JobOffer[]>([]);
  const [archivalOffers, setArchivalOffers] = useState<JobOffer[]>([]);
  const [applyingOfferIds, setApplyingOfferIds] = useState<Set<number>>(new Set());
  const [maxResults, setMaxResults] = useState(Math.min(10, user.result_limit));
  const [status, setStatus] = useState("Loading your profile...");
  const [warning, setWarning] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [searchJob, setSearchJob] = useState<SearchJob | null>(null);
  const [progressStep, setProgressStep] = useState(0);
  const noticeRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const progressMessage = SEARCH_PROGRESS_MESSAGES[progressStep];

  const scrollToOutcome = useCallback((hasError: boolean) => {
    window.setTimeout(() => {
      (hasError ? noticeRef.current : resultsRef.current)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 0);
  }, []);

  const replaceProfile = useCallback((nextProfile: Profile) => {
    setProfile(nextProfile);
    setListDrafts(listDraftsFromProfile(nextProfile));
  }, []);

  const refreshAccount = useCallback(async () => {
    const [loadedUser, loadedProfile, loadedUsage] = await Promise.all([
      api<User>("/api/me", token),
      api<Profile>("/api/profile", token),
      api<Usage>("/api/usage", token),
    ]);
    setUser(loadedUser);
    replaceProfile(loadedProfile);
    setUsage(loadedUsage);
  }, [replaceProfile, token]);

  const refreshSearchResults = useCallback(async () => {
    const results = await api<SearchResults>("/api/searches/results", token);
    setSearchJob(results.current);
    setOffers(results.current?.offers ?? []);
    setArchivalOffers(results.archival);
  }, [token]);

  useEffect(() => {
    Promise.all([refreshAccount(), refreshSearchResults()])
      .then(() => setStatus("Profile ready"))
      .catch((error: Error) => setWarning(error.message))
      .finally(() => setBusy(false));
  }, [refreshAccount, refreshSearchResults]);

  useEffect(() => {
    if (!isSearching) return;
    const timer = window.setInterval(
      () => setProgressStep((step) => (
        step === SEARCH_PROGRESS_MESSAGES.length - 1
          ? RANKING_PROGRESS_START
          : step + 1
      )),
      4000,
    );
    return () => window.clearInterval(timer);
  }, [isSearching]);

  useAgentContext({
    description: "Current RecrBro account, profile, requested result count, and visible job matches.",
    value: { user, profile, requestedResults: maxResults, visibleOffers: offers, archivalOffers },
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
      if (coreSkills) {
        setListDrafts((current) => ({ ...current, core_skills: coreSkills.join(", ") }));
      }
      return "Updated the visible criteria for review.";
    },
  }, []);

  function updateField<K extends keyof Profile>(field: K, value: Profile[K]) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  function updateListField(field: ListProfileField, value: string) {
    setListDrafts((current) => ({ ...current, [field]: value }));
    updateField(field, splitList(value));
  }

  async function saveProfile() {
    setBusy(true);
    setWarning(null);
    setStatus("Saving your profile...");
    try {
      const profileToSave = profileWithListDrafts(profile, listDrafts);
      const { user_id: _, cv_filename: __, ...payload } = profileToSave;
      const savedProfile = await api<Profile>("/api/profile", token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      replaceProfile(savedProfile);
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
      replaceProfile(result.profile);
      setWarning(result.warning);
      setStatus(result.analysis_mode === "ai" ? "CV analyzed with AI" : "CV parsed locally");
      await refreshAccount().catch(() => undefined);
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
    setIsSearching(true);
    setArchivalOffers((current) => Array.from(
      new Map([...offers, ...current].map((offer) => [offer.url, offer])).values(),
    ));
    setOffers([]);
    setWarning(null);
    setProgressStep(0);
    setSearchJob(null);
    setStatus("Preparing your search...");
    try {
      const profileToSave = profileWithListDrafts(profile, listDrafts);
      const { user_id: _, cv_filename: __, ...payload } = profileToSave;
      const savedProfile = await api<Profile>("/api/profile", token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      replaceProfile(savedProfile);

      const job = await api<SearchJob>("/api/searches", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_results: maxResults }),
      });
      setSearchJob(job);
      let completedJob = job;
      while (completedJob.status === "queued" || completedJob.status === "running") {
        await wait(SEARCH_POLL_INTERVAL_MS);
        completedJob = await api<SearchJob>(`/api/searches/${job.id}`, token);
        setSearchJob(completedJob);
      }
      if (completedJob.status !== "complete") {
        throw new Error(completedJob.error ?? "Search did not complete.");
      }
      await refreshSearchResults();
      setWarning(completedJob.warning);
      setStatus(`Found ${completedJob.offers.length} ranked matches`);
      setIsSearching(false);
      setBusy(false);
      await refreshAccount().catch(() => undefined);
      scrollToOutcome(false);
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "Search failed.");
      setStatus("Search failed");
      setIsSearching(false);
      setBusy(false);
      await refreshAccount().catch(() => undefined);
      scrollToOutcome(true);
    }
  }

  async function markApplied(offer: JobOffer) {
    setApplyingOfferIds((current) => new Set(current).add(offer.id));
    setWarning(null);
    try {
      await api<void>(`/api/offers/${offer.id}/applied`, token, { method: "PUT" });
      const updateOffers = (items: JobOffer[]) => items.map(
        (item) => item.url === offer.url ? { ...item, applied: true } : item,
      );
      setOffers(updateOffers);
      setArchivalOffers(updateOffers);
      setStatus("Offer marked as applied");
    } catch (error) {
      setWarning(error instanceof Error ? error.message : "Could not mark the offer as applied.");
    } finally {
      setApplyingOfferIds((current) => {
        const next = new Set(current);
        next.delete(offer.id);
        return next;
      });
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RecrBro home"><BrandLogo /></a>
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
      </section>

      {warning && <div className="notice" ref={noticeRef} role="alert"><strong>Heads up</strong><span>{warning}</span><button onClick={() => setWarning(null)} aria-label="Dismiss notice">×</button></div>}

      <section className="workspace">
        <article className="panel profilePanel">
          <div className="panelHeading">
            <div><p className="sectionNumber">01</p><h2>Candidate profile</h2></div>
            <button className="secondaryButton" onClick={saveProfile} disabled={busy}>Save profile</button>
          </div>
          <div className="formGrid">
            <label className="wide"><span>Core skills</span><input value={listDrafts.core_skills} onChange={(e) => updateListField("core_skills", e.target.value)} placeholder="Python, FastAPI, SQL" /><small>Required matches and the strongest ranking signal.</small></label>
            <label><span>Location</span><input value={profile.location} onChange={(e) => updateField("location", e.target.value)} placeholder="Poland" /></label>
            <label><span>Minimum monthly salary</span><input type="number" min="0" value={profile.minimum_salary ?? ""} onChange={(e) => updateField("minimum_salary", e.target.value ? Number(e.target.value) : null)} placeholder="18000" /></label>
            <fieldset className="workModes">
              <legend>Work mode</legend>
              {(["remote", "on-site", "hybrid"] as WorkMode[]).map((mode) => (
                <label key={mode}>
                  <input
                    type="checkbox"
                    checked={profile.work_modes.includes(mode)}
                    onChange={(event) => updateField(
                      "work_modes",
                      event.target.checked
                        ? [...profile.work_modes, mode]
                        : profile.work_modes.filter((value) => value !== mode),
                    )}
                  />
                  <span>{mode}</span>
                </label>
              ))}
            </fieldset>
            <label><span>Contract type</span><input value={listDrafts.contract_types} onChange={(e) => updateListField("contract_types", e.target.value)} placeholder="B2B, employment" /></label>
            <label className="wide"><span>Languages</span><input value={listDrafts.languages} onChange={(e) => updateListField("languages", e.target.value)} placeholder="English, Polish" /></label>
            <label className="wide"><span>Other skills</span><input value={listDrafts.other_skills} onChange={(e) => updateListField("other_skills", e.target.value)} placeholder="Docker, Azure, mentoring" /></label>
            <label className="wide"><span>Companies to exclude</span><input value={listDrafts.excluded_companies} onChange={(e) => updateListField("excluded_companies", e.target.value)} placeholder="Company A, Company B" /></label>
            <label className="wide"><span>Additional requirements</span><textarea value={profile.additional_limitations} onChange={(e) => updateField("additional_limitations", e.target.value)} placeholder="No night shifts." /><small>High-priority requirements used while discovering and validating offers.</small></label>
          </div>
          <div className="cvCard">
            <div><strong>Build from a CV</strong><span>{profile.cv_filename ? `Using ${profile.cv_filename}` : "Upload a PDF to extract skills and languages."}</span></div>
            <label className="uploadButton">Choose PDF<input type="file" accept="application/pdf" disabled={busy} onChange={uploadCv} /></label>
          </div>
        </article>

        <aside className="panel searchPanel">
          <p className="sectionNumber">02</p><h2>Start a search</h2>
          <p>Core skills shape discovery. Your remaining profile criteria refine ranking and eligibility.</p>
          <label><span>Maximum results</span><input type="range" min="1" max={user.result_limit} value={Math.min(maxResults, user.result_limit)} onChange={(e) => setMaxResults(Number(e.target.value))} /></label>
          <div className="resultCount"><strong>{Math.min(maxResults, user.result_limit)}</strong><span>offers</span></div>
          <button className="primaryButton" onClick={runSearch} disabled={busy}>
            {isSearching ? "Searching job sources..." : busy ? "Please wait..." : "Search job sources"}
            <span>{isSearching ? "●" : "↗"}</span>
          </button>
          <div className={`searchStatus${isSearching ? " active" : ""}`} aria-live="polite" aria-atomic="true">
            <span className={isSearching ? "pulse" : "statusDot"} />
            <div>
              <strong>{isSearching ? progressMessage.title : status}</strong>
              <small>
                {isSearching
                  ? progressMessage.detail
                  : `${user.result_limit} results per search · ${usage.available_credits.toFixed(2)} credits left`}
              </small>
            </div>
          </div>
          <div className="planDetail"><span>Current plan</span><strong>{user.plan === "premium" ? "Premium" : "Free"}</strong><small>Immediate results · up to 10 offers · CV upload included</small><small>{usage.available_credits.toFixed(2)} credits left</small></div>
          <div className="buyCoffee">
            <div className="buyCoffeeHeading">
              <h3>Postaw kawę za:</h3>
            </div>
            <div className="buyCoffeeOptions">
              {COFFEE_OPTIONS.map(({ size, price }) => (
                <a
                  href={`https://buycoffee.to/recrbro?coffeeSize=${size}`}
                  key={size}
                  rel="noopener noreferrer"
                  target="_blank"
                  title={`Postaw kawę za: ${price}`}
                >
                  <img
                    src={`https://buycoffee.to/static/img/icons/coffee-${size}.svg`}
                    alt={`${size} coffee icon`}
                  />
                  <span>{price}</span>
                </a>
              ))}
            </div>
            <p>Wsparcie jest obsługiwane przez buycoffee.to i nie zmienia automatycznie planu ani salda kredytów.</p>
          </div>
        </aside>
      </section>

      <section className="resultsSection" ref={resultsRef}>
        <div className="resultsHeading"><div><p className="sectionNumber">03</p><h2>Current results</h2></div>{offers.length > 0 && <span>{offers.length} verified results from job sources</span>}</div>
        {offers.length === 0 ? (
          <div className="emptyState"><span>◎</span><h3>Your shortlist starts here</h3><p>Save your profile and run a search to see ranked job offers.</p></div>
        ) : (
          <div className="offerList">{offers.map((offer, index) => (
            <article className={`offerCard ${offer.applied ? "appliedCard" : ""}`} key={offer.id}>
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="offerBody"><div className="offerTitle"><div><p>{offer.company}{offer.applied && <span className="appliedBadge">applied</span>}</p><h3>{offer.title}</h3></div><div className="score"><strong>{Math.round(offer.score)}%</strong><span>match</span></div></div><p className="summary">{offer.summary}</p><div className="tags">{offer.match_reasons.map((reason) => <span key={reason}>{reason}</span>)}</div></div>
              <div className="offerActions"><a className="openOffer" href={offer.url} target="_blank" rel="noreferrer">Open offer <span>↗</span></a>{!offer.applied && <button className="appliedButton" disabled={applyingOfferIds.has(offer.id)} onClick={() => markApplied(offer)}>{applyingOfferIds.has(offer.id) ? "Saving..." : "Applied"}</button>}</div>
            </article>
          ))}</div>
        )}
      </section>
      <section className="resultsSection archivalSection">
        <div className="resultsHeading"><div><p className="sectionNumber">04</p><h2>Archival results</h2></div>{archivalOffers.length > 0 && <span>{archivalOffers.length} offers from previous searches</span>}</div>
        {archivalOffers.length === 0 ? (
          <div className="emptyState"><span>↺</span><h3>No archived offers yet</h3><p>Your current results move here as soon as you start another search.</p></div>
        ) : (
          <div className="offerList">{archivalOffers.map((offer, index) => (
            <article className={`offerCard ${offer.applied ? "appliedCard" : ""}`} key={offer.id}>
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="offerBody"><div className="offerTitle"><div><p>{offer.company}{offer.applied && <span className="appliedBadge">applied</span>}</p><h3>{offer.title}</h3></div><div className="score"><strong>{Math.round(offer.score)}%</strong><span>match</span></div></div><p className="summary">{offer.summary}</p><div className="tags">{offer.match_reasons.map((reason) => <span key={reason}>{reason}</span>)}</div></div>
              <div className="offerActions"><a className="openOffer" href={offer.url} target="_blank" rel="noreferrer">Open offer <span>↗</span></a>{!offer.applied && <button className="appliedButton" disabled={applyingOfferIds.has(offer.id)} onClick={() => markApplied(offer)}>{applyingOfferIds.has(offer.id) ? "Saving..." : "Applied"}</button>}</div>
            </article>
          ))}</div>
        )}
      </section>
      <LegalFooter />
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<{ token: string; user: User } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(SESSION_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    api<User>("/api/me", token)
      .then((user) => setSession({ token, user }))
      .catch(() => localStorage.removeItem(SESSION_KEY))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="loadingScreen"><LogoMark /><strong>Loading RecrBro...</strong></main>;
  if (!session) return <AuthScreen onAuthenticated={(token, user) => { localStorage.setItem(SESSION_KEY, token); setSession({ token, user }); }} />;
  return <Dashboard initialUser={session.user} token={session.token} onLogout={() => { void api<void>("/api/auth/session", session.token, { method: "DELETE" }); localStorage.removeItem(SESSION_KEY); setSession(null); }} />;
}

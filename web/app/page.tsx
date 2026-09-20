"use client";

import {
  useAgentContext,
  useFrontendTool,
} from "@copilotkit/react-core/v2";
import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
  target_roles: string[];
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

type Usage = {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
};

const emptyProfile: Profile = {
  user_id: 0,
  target_roles: [],
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
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export default function Dashboard() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUserId, setSelectedUserId] = useState(2);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [usage, setUsage] = useState<Usage>({
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
  });
  const [offers, setOffers] = useState<JobOffer[]>([]);
  const [maxResults, setMaxResults] = useState(10);
  const [includeCollections, setIncludeCollections] = useState(false);
  const [status, setStatus] = useState("Loading profile...");
  const [warning, setWarning] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId),
    [selectedUserId, users],
  );

  const loadUser = useCallback(async (userId: number) => {
    setBusy(true);
    setWarning(null);
    try {
      const [loadedProfile, loadedUsage] = await Promise.all([
        api<Profile>(`/api/users/${userId}/profile`),
        api<Usage>(`/api/users/${userId}/usage`),
      ]);
      setProfile(loadedProfile);
      setUsage(loadedUsage);
      setOffers([]);
      setStatus("Profile ready");
    } catch (error) {
      setStatus("Could not load profile");
      setWarning(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    api<User[]>("/api/users")
      .then((loadedUsers) => {
        setUsers(loadedUsers);
        const initialId = loadedUsers.some((user) => user.id === 2)
          ? 2
          : loadedUsers[0]?.id;
        if (initialId) {
          setSelectedUserId(initialId);
          void loadUser(initialId);
        }
      })
      .catch((error: Error) => {
        setStatus("Backend unavailable");
        setWarning(error.message);
      });
  }, [loadUser]);

  useAgentContext({
    description:
      "Current Recrbro user, candidate profile, requested result count, and visible job matches.",
    value: {
      user: selectedUser ?? null,
      profile,
      requestedResults: maxResults,
      includeCollectionsIfNeeded: includeCollections,
      visibleOffers: offers.map(
        ({ title, company, score, match_reasons, result_type }) => ({
          title,
          company,
          score,
          match_reasons,
          result_type,
        }),
      ),
    },
  });

  useFrontendTool(
    {
      name: "updateSearchCriteria",
      description:
        "Update the visible target roles, core skills, and location in the candidate profile. The user still saves the changes explicitly.",
      parameters: z.object({
        targetRoles: z.array(z.string()).optional(),
        coreSkills: z.array(z.string()).optional(),
        location: z.string().optional(),
      }),
      handler: async ({ targetRoles, coreSkills, location }) => {
        setProfile((current) => ({
          ...current,
          target_roles: targetRoles ?? current.target_roles,
          core_skills: coreSkills ?? current.core_skills,
          location: location ?? current.location,
        }));
        return "Updated the visible search criteria. Ask the user to review and save.";
      },
    },
    [],
  );

  function updateField<K extends keyof Profile>(field: K, value: Profile[K]) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  async function saveProfile() {
    setBusy(true);
    setWarning(null);
    setStatus("Saving profile...");
    try {
      const { user_id: _, cv_filename: __, ...payload } = profile;
      const saved = await api<Profile>(
        `/api/users/${selectedUserId}/profile`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setProfile(saved);
      setStatus("Profile saved");
    } catch (error) {
      setStatus("Save failed");
      setWarning(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }

  async function uploadCv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setWarning(null);
    setStatus("Analyzing CV...");
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api<{
        profile: Profile;
        analysis_mode: "ai" | "local-fallback";
        warning: string | null;
      }>(`/api/users/${selectedUserId}/cv`, {
        method: "POST",
        body: form,
      });
      setProfile(result.profile);
      setWarning(result.warning);
      setStatus(
        result.analysis_mode === "ai"
          ? "CV analyzed with AI"
          : "CV parsed locally",
      );
      setUsage(await api<Usage>(`/api/users/${selectedUserId}/usage`));
    } catch (error) {
      setStatus("CV analysis failed");
      setWarning(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function runSearch() {
    setBusy(true);
    setOffers([]);
    setWarning(null);
    setStatus("Searching live LinkedIn pages...");
    try {
      const result = await api<{
        offers: JobOffer[];
        warning: string | null;
      }>(`/api/users/${selectedUserId}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_results: maxResults,
          include_collections_if_needed: includeCollections,
        }),
      });
      setOffers(result.offers);
      setWarning(result.warning);
      setStatus(`Found ${result.offers.length} ranked matches`);
    } catch (error) {
      setStatus("Search failed");
      setWarning(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Recrbro home">
          <span className="brandMark">R</span>
          <span>recrbro</span>
        </a>
        <div className="userControl">
          <span className={`planBadge ${selectedUser?.plan ?? "free"}`}>
            {selectedUser?.plan ?? "loading"}
          </span>
          <select
            aria-label="Active demo user"
            value={selectedUserId}
            onChange={(event) => {
              const userId = Number(event.target.value);
              setSelectedUserId(userId);
              void loadUser(userId);
            }}
          >
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">Your focused job search</p>
          <h1>Less scrolling.<br />Better-fit roles.</h1>
          <p className="heroCopy">
            Shape your profile once, then let Recrbro search and rank live
            LinkedIn job pages around what matters most.
          </p>
        </div>
        <div className="statusCard">
          <span className={busy ? "pulse" : "statusDot"} />
          <div>
            <strong>{status}</strong>
            <small>
              {selectedUser?.result_limit ?? 0} results per search · $
              {usage.cost_usd.toFixed(4)} tracked AI cost
            </small>
          </div>
        </div>
      </section>

      {warning && (
        <div className="notice" role="alert">
          <strong>Heads up</strong>
          <span>{warning}</span>
          <button onClick={() => setWarning(null)} aria-label="Dismiss notice">
            ×
          </button>
        </div>
      )}

      <section className="workspace">
        <article className="panel profilePanel">
          <div className="panelHeading">
            <div>
              <p className="sectionNumber">01</p>
              <h2>Candidate profile</h2>
            </div>
            <button
              className="secondaryButton"
              onClick={saveProfile}
              disabled={busy}
            >
              Save profile
            </button>
          </div>

          <div className="formGrid">
            <label className="wide">
              <span>Target roles</span>
              <input
                value={profile.target_roles.join(", ")}
                onChange={(event) =>
                  updateField("target_roles", splitList(event.target.value))
                }
                placeholder="Python Developer, AI Engineer"
              />
            </label>
            <label className="wide">
              <span>Core skills</span>
              <input
                value={profile.core_skills.join(", ")}
                onChange={(event) =>
                  updateField("core_skills", splitList(event.target.value))
                }
                placeholder="Python, FastAPI, SQL"
              />
              <small>Required matches and the strongest ranking signal.</small>
            </label>
            <label>
              <span>Location</span>
              <input
                value={profile.location}
                onChange={(event) =>
                  updateField("location", event.target.value)
                }
                placeholder="Poland"
              />
            </label>
            <label>
              <span>Minimum monthly salary</span>
              <input
                type="number"
                min="0"
                value={profile.minimum_salary ?? ""}
                onChange={(event) =>
                  updateField(
                    "minimum_salary",
                    event.target.value ? Number(event.target.value) : null,
                  )
                }
                placeholder="18000"
              />
            </label>
            <label>
              <span>Work mode</span>
              <input
                value={profile.work_modes.join(", ")}
                onChange={(event) =>
                  updateField("work_modes", splitList(event.target.value))
                }
                placeholder="remote, hybrid"
              />
            </label>
            <label>
              <span>Contract type</span>
              <input
                value={profile.contract_types.join(", ")}
                onChange={(event) =>
                  updateField("contract_types", splitList(event.target.value))
                }
                placeholder="B2B, employment"
              />
            </label>
            <label className="wide">
              <span>Other skills</span>
              <input
                value={profile.other_skills.join(", ")}
                onChange={(event) =>
                  updateField("other_skills", splitList(event.target.value))
                }
                placeholder="Docker, Azure, mentoring"
              />
            </label>
            <label className="wide">
              <span>Companies to exclude</span>
              <input
                value={profile.excluded_companies.join(", ")}
                onChange={(event) =>
                  updateField(
                    "excluded_companies",
                    splitList(event.target.value),
                  )
                }
                placeholder="Company A, Company B"
              />
            </label>
          </div>

          <div className={`cvCard ${selectedUser?.plan !== "premium" ? "locked" : ""}`}>
            <div>
              <strong>Build from a CV</strong>
              <span>
                {profile.cv_filename
                  ? `Using ${profile.cv_filename}`
                  : "Upload a PDF to extract skills and languages."}
              </span>
            </div>
            <label className="uploadButton">
              {selectedUser?.plan === "premium"
                ? "Choose PDF"
                : "Premium feature"}
              <input
                type="file"
                accept="application/pdf"
                disabled={busy || selectedUser?.plan !== "premium"}
                onChange={uploadCv}
              />
            </label>
          </div>
        </article>

        <aside className="panel searchPanel">
          <p className="sectionNumber">02</p>
          <h2>Start a search</h2>
          <p>
            Core skills shape the query. Location, work mode, and contract type
            improve the ranking.
          </p>
          <label>
            <span>Maximum results</span>
            <input
              type="range"
              min="1"
              max={selectedUser?.result_limit ?? 5}
              value={Math.min(maxResults, selectedUser?.result_limit ?? 5)}
              onChange={(event) => setMaxResults(Number(event.target.value))}
            />
          </label>
          <div className="resultCount">
            <strong>
              {Math.min(maxResults, selectedUser?.result_limit ?? 5)}
            </strong>
            <span>offers</span>
          </div>
          <label className="collectionToggle">
            <input
              type="checkbox"
              checked={includeCollections}
              onChange={(event) => setIncludeCollections(event.target.checked)}
            />
            <span>
              Include LinkedIn result pages if there are not enough verified
              offers
            </span>
          </label>
          <button
            className="primaryButton"
            onClick={runSearch}
            disabled={busy}
          >
            {busy ? "Working..." : "Search LinkedIn"}
            <span>↗</span>
          </button>
          <div className="planDetail">
            <span>Current plan</span>
            <strong>{selectedUser?.plan === "premium" ? "Premium" : "Free"}</strong>
            <small>
              {selectedUser?.plan === "premium"
                ? "Immediate results · up to 100 offers"
                : "PoC runs immediately · limited to 5 offers"}
            </small>
          </div>
        </aside>
      </section>

      <section className="resultsSection">
        <div className="resultsHeading">
          <div>
            <p className="sectionNumber">03</p>
            <h2>Ranked opportunities</h2>
          </div>
          {offers.length > 0 && (
            <span>{offers.length} live LinkedIn pages</span>
          )}
        </div>

        {offers.length === 0 ? (
          <div className="emptyState">
            <span>◎</span>
            <h3>Your shortlist starts here</h3>
            <p>Save your profile and run a search to see ranked job offers.</p>
          </div>
        ) : (
          <div className="offerList">
            {offers.map((offer, index) => (
              <article
                className={`offerCard ${offer.result_type === "collection" ? "collectionCard" : ""}`}
                key={offer.url}
              >
                <div className="rank">{String(index + 1).padStart(2, "0")}</div>
                <div className="offerBody">
                  <div className="offerTitle">
                    <div>
                      <p>
                        {offer.company}
                        {offer.result_type === "collection" && (
                          <span className="collectionBadge">Collection</span>
                        )}
                      </p>
                      <h3>{offer.title}</h3>
                    </div>
                    {offer.result_type === "job" ? (
                      <div className="score">
                        <strong>{Math.round(offer.score)}%</strong>
                        <span>match</span>
                      </div>
                    ) : (
                      <div className="collectionIcon" aria-hidden="true">
                        ⋯
                      </div>
                    )}
                  </div>
                  <p className="summary">{offer.summary}</p>
                  <div className="tags">
                    {offer.match_reasons.map((reason) => (
                      <span key={reason}>{reason}</span>
                    ))}
                  </div>
                </div>
                <a
                  className="openOffer"
                  href={offer.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {offer.result_type === "job" ? "Open offer" : "Browse offers"}{" "}
                  <span>↗</span>
                </a>
              </article>
            ))}
          </div>
        )}
      </section>

      <footer>
        <span>recrbro proof of concept</span>
        <span>Live search powered by Tavily · Assistant powered by CopilotKit</span>
      </footer>
    </main>
  );
}

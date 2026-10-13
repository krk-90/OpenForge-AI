import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp, BookOpen, Check, ChevronDown, CircleHelp, Clock3,
  Code2, Command, ExternalLink, FileCode2, GitBranch, Github, Layers3,
  LoaderCircle, LogOut, Menu, MessageSquare, Plus, Search, Settings2,
  Sparkles, Sun, Moon, X,
} from "lucide-react";
import "./styles.css";

const SESSION_KEY = "openforge-session";
const STARTERS = [
  { icon: Search, title: "Find a good first issue", prompt: "Help me find a good first issue in this repository. Explain what makes it beginner-friendly." },
  { icon: BookOpen, title: "Explain this codebase", prompt: "Give me a practical overview of this repository's architecture and where I should start reading." },
  { icon: Code2, title: "Plan a contribution", prompt: "Help me plan a small, useful contribution. Ask me anything you need to know first." },
];
const AGENTS = [
  { id: "orchestrator", name: "Orchestrator", detail: "Contribution guide", icon: Sparkles, tone: "orchestrator-icon" },
  { id: "mentor", name: "Code mentor", detail: "Learn as you build", icon: BookOpen, tone: "mentor-icon" },
  { id: "pr-reviewer", name: "PR reviewer", detail: "Review with confidence", icon: FileCode2, tone: "review-icon" },
  { id: "repository-rag", name: "Repository Q&A", detail: "Answers from indexed code", icon: Search, tone: "discovery-icon" },
  { id: "documentation", name: "Documentation", detail: "Map the codebase", icon: BookOpen, tone: "mentor-icon" },
  { id: "repository-discovery", name: "Repo discovery", detail: "Find projects by skill", icon: GitBranch, tone: "review-icon" },
  { id: "profile", name: "Developer profile", detail: "Build a skill profile", icon: Layers3, tone: "discovery-icon" },
];

function normalizeRepository(repository) {
  const value = repository.trim().replace(/^https?:\/\/(www\.)?github\.com\//i, "").replace(/\.git\/?$/i, "").replace(/\/$/, "");
  const [owner, name] = value.split("/");
  if (!owner || !name) throw new Error("Enter a GitHub repository as owner/repo.");
  return { repositoryId: `${owner}/${name.split(/[?#]/)[0]}`, repositoryUrl: `https://github.com/${owner}/${name.split(/[?#]/)[0]}` };
}

function listSection(title, values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `## ${title}\n${values.map((value) => `- ${typeof value === "string" ? value : value.path || JSON.stringify(value)}`).join("\n")}`;
}

function formatStructuredResult(value) {
  if (typeof value === "string") {
    try { return formatStructuredResult(JSON.parse(value)); } catch { return value; }
  }
  if (!value || typeof value !== "object") return String(value ?? "");
  if (typeof value.answer === "string") return value.answer;
  if (typeof value.document === "string") return formatStructuredResult(value.document);
  if (Array.isArray(value.repositories)) {
    if (!value.repositories.length) return "No matching repositories were found. Try a different skill or language.";
    return value.repositories.map((repo) => `## ${repo.repository}\n${repo.reason}\n${repo.language || "Language not listed"} · ${repo.stars} stars · score ${repo.score}`).join("\n\n");
  }
  if (value.repository_name || value.repository_summary || value.architecture_overview) {
    return [
      `# ${value.repository_name || "Repository overview"}`,
      value.repository_summary,
      value.architecture_overview && `## Architecture\n${value.architecture_overview}`,
      listSection("Technology", value.tech_stack),
      listSection("Main modules", value.main_modules),
      listSection("Starting points", value.contributor_guide?.starting_points),
      value.contributor_guide?.difficulty && `Difficulty: ${value.contributor_guide.difficulty}`,
      listSection("Suggested improvements", value.improvement_suggestions),
    ].filter(Boolean).join("\n\n");
  }
  if (typeof value.summary === "string" && Array.isArray(value.findings)) {
    const findings = value.findings.map((finding) => `### ${finding.severity?.toUpperCase() || "INFO"}: ${finding.title}\n${finding.file ? `${finding.file}${finding.line ? `:${finding.line}` : ""}\n` : ""}${finding.body}${finding.suggestion ? `\nSuggestion: ${finding.suggestion}` : ""}`).join("\n\n");
    return [`# Pull request review`, value.summary, `Recommendation: ${value.recommendation || "Not provided"}`, findings && `## Findings\n${findings}`, listSection("Tests to run", value.tests_to_run)].filter(Boolean).join("\n\n");
  }
  if (typeof value.issue_summary === "string") {
    return [`## ${value.issue_summary}`, listSection("Learning objectives", value.learning_objectives), listSection("Approach", value.approach_steps), value.first_task && `First task: ${value.first_task}`, listSection("Suggested commands", value.suggested_commands), listSection("Likely pitfalls", value.likely_pitfalls)].filter(Boolean).join("\n\n");
  }
  if (value.profile && typeof value.profile === "object") {
    const profile = value.profile;
    return [`## Developer profile${profile.display_name ? `: ${profile.display_name}` : ""}`, profile.bio, listSection("Skills", profile.skills), listSection("Interests", profile.interests), listSection("Preferred languages", profile.preferred_languages), listSection("Contribution goals", profile.contribution_goals)].filter(Boolean).join("\n\n");
  }
  return JSON.stringify(value, null, 2);
}

function formatStoredRequest(value) {
  if (!value?.agent || !value.request || typeof value.request !== "object") return "";
  const request = value.request.request && typeof value.request.request === "object"
    ? value.request.request
    : value.request;
  if (typeof request.message === "string") return request.message;
  if (typeof request.question === "string") return request.question;
  if (Array.isArray(request.skills)) return `Find repositories for: ${request.skills.join(", ")}`;
  if (request.profile) {
    const skills = request.profile.skills;
    return `Build a developer profile${skills ? ` from these skills: ${Array.isArray(skills) ? skills.join(", ") : skills}` : ""}.`;
  }
  if (request.pull_number) return `Review pull request ${request.owner}/${request.repo}#${request.pull_number}.`;
  if (request.explanation_type) {
    return `Generate ${request.explanation_type} documentation for ${request.repository?.repo_url || "the repository"}.`;
  }
  return `Run ${value.agent.replaceAll("-", " ")}.`;
}

function responseText(result) {
  return formatStructuredResult(result);
}

async function api(path, token, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || "Something went wrong. Please try again.");
  return result;
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api(`/auth/${mode === "signup" ? "signup" : "login"}`, null, {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      if (result.session) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...result.session, email: result.user?.email }));
        onAuthenticated(result.session, result.user);
      } else {
        setNotice(result.message || "Check your email to confirm your account.");
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand">
        <div className="wordmark"><span className="mark"><Command size={19} /></span>OpenForge</div>
        <div className="auth-pitch">
          <span className="eyebrow"><span className="live-dot" /> Open-source contribution, guided</span>
          <h1>Make your<br /><em>next move.</em></h1>
          <p>Find the right issue. Understand the code. Make a contribution you’re proud of.</p>
          <div className="auth-art" aria-hidden="true">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" />
            <div className="art-core"><GitBranch size={34} /></div>
            <span className="art-node node-a"><Code2 size={17} /></span>
            <span className="art-node node-b"><Sparkles size={17} /></span>
            <span className="art-node node-c"><Check size={17} /></span>
          </div>
        </div>
        <div className="auth-foot"><span>BUILT FOR THE OPEN WEB</span><span>01 — CONTRIBUTE</span></div>
      </section>
      <section className="auth-form-side">
        <div className="auth-topline"><span>YOUR DEVELOPER WORKSPACE</span><a href="https://github.com" target="_blank" rel="noreferrer">GitHub <ExternalLink size={13} /></a></div>
        <div className="auth-card">
          <div className="auth-icon"><Github size={21} /></div>
          <p className="eyebrow dark-eyebrow">{mode === "login" ? "GOOD TO HAVE YOU BACK" : "START BUILDING IN PUBLIC"}</p>
          <h2>{mode === "login" ? "Pick up where you left off." : "Your next contribution starts here."}</h2>
          <p className="auth-copy">{mode === "login" ? "Sign in to return to your repositories and agent conversations." : "Create an account and find your place in open source."}</p>
          <div className="auth-tabs" role="group" aria-label="Account action">
            <button type="button" aria-pressed={mode === "login"} onClick={() => { setMode("login"); setError(""); setNotice(""); }}>Sign in</button>
            <button type="button" aria-pressed={mode === "signup"} onClick={() => { setMode("signup"); setError(""); setNotice(""); }}>Create account</button>
          </div>
          <form onSubmit={submit}>
            <label className="field-label" htmlFor="email">Email address</label>
            <input className="text-input" id="email" name="email" type="email" autoComplete="email" placeholder="you@domain.com" required maxLength={320} />
            <label className="field-label password-label" htmlFor="password">Password <span>6 characters minimum</span></label>
            <input className="text-input" id="password" name="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder="Enter your password" required minLength={6} maxLength={128} />
            {error && <p className="form-feedback error-feedback" role="alert">{error}</p>}
            {notice && <p className="form-feedback" role="status">{notice}</p>}
            <button className="auth-submit" type="submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={17} /> : null}
              {busy ? "One moment" : mode === "login" ? "Sign in to OpenForge" : "Create your account"}
              {!busy && <ArrowUp size={16} className="submit-arrow" />}
            </button>
          </form>
          <p className="auth-legal">By continuing, you agree to build things that make the internet a little better.</p>
        </div>
        <div className="auth-bottom"><span>OPEN SOURCE, IN MOTION</span><CircleHelp size={16} /></div>
      </section>
    </main>
  );
}

function App() {
  const stored = (() => { try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch { return null; } })();
  const [session, setSession] = useState(stored);
  const [email, setEmail] = useState(stored?.email || "");
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState("orchestrator");
  const [messages, setMessages] = useState([]);
  const [repository, setRepository] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem("openforge-theme") || "light"; } catch { return "light"; } });
  const scrollRef = useRef(null);

  useEffect(() => {
    try { localStorage.setItem("openforge-theme", theme); } catch {}
  }, [theme]);
  const newSessionIds = useRef(new Set());
  const activeSession = sessions.find((item) => item.session_id === activeId);
  const activeAgent = AGENTS.find((agent) => agent.id === selectedAgent) || AGENTS[0];

  useEffect(() => {
    if (!session?.access_token) return;
    api("/agents/sessions", session.access_token)
      .then(({ sessions: items = [] }) => setSessions(items))
      .catch((error) => setNotice(error.message));
  }, [session?.access_token]);

  useEffect(() => {
    if (!activeId || !session?.access_token) return;
    if (newSessionIds.current.delete(activeId)) return;
    setLoading(true);
    api(`/agents/sessions/${encodeURIComponent(activeId)}`, session.access_token)
      .then(({ session: item, messages: history = [] }) => {
        setRepository(item?.repository_id || "");
        setMessages(history.flatMap((entry, index) => {
          if (!entry || typeof entry !== "object") return [];
          const role = entry.role || entry.type || "assistant";
          const rawContent = entry.content ?? entry.message ?? entry.response ?? entry.answer;
          if (typeof rawContent !== "string" || !rawContent.trim()) return [];
          let content = rawContent;
          try {
            const parsed = JSON.parse(rawContent);
            if (typeof parsed.content === "string" && !parsed.content.trim() && !parsed.request && !parsed.answer && !parsed.response) return [];
            content = parsed.request?.message || parsed.request?.question || parsed.answer || parsed.response || parsed.content || formatStoredRequest(parsed) || formatStructuredResult(parsed);
          } catch {}
          if (typeof content !== "string" || !content.trim()) return [];
          return {
            id: `${activeId}-${index}`,
            role: role === "human" || role === "user" ? "user" : "assistant",
            content,
          };
        }));
      })
      .catch((error) => setNotice(error.message))
      .finally(() => setLoading(false));
  }, [activeId, session?.access_token]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  function startFresh() {
    setActiveId(null);
    setMessages([]);
    setDraft("");
    setNotice("");
    setMobileMenu(false);
  }

  function openRepository() {
    try {
      window.open(normalizeRepository(repository).repositoryUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function selectSession(item) {
    setActiveId(item.session_id);
    setMobileMenu(false);
  }

  async function sendMessage(text = draft) {
    const content = text.trim();
    if (!content || busy) return;
    const needsRepository = selectedAgent !== "repository-discovery";
    if (needsRepository && !repository.trim()) {
      setNotice("Add a GitHub repository above to start a contribution chat.");
      return;
    }
    let repositoryParts = { repositoryId: "", repositoryUrl: "" };
    if (needsRepository) {
      try {
        repositoryParts = normalizeRepository(repository);
      } catch (error) {
        setNotice(error.message);
        return;
      }
    }
    const pullNumber = content.match(/(?:pull request|pr)?\s*#(\d+)\b/i)?.[1];
    if (selectedAgent === "pr-reviewer" && !pullNumber) {
      setNotice("Include a pull request number such as #42 in your message.");
      return;
    }
    setDraft("");
    setNotice("");
    setBusy(true);
    const optimistic = { id: `local-${Date.now()}`, role: "user", content };
    setMessages((current) => [...current, optimistic]);
    try {
      let chatId = activeId;
      if (!chatId) {
        const result = await api("/agents/sessions", session.access_token, {
          method: "POST",
          body: JSON.stringify({ repository_id: repositoryParts.repositoryId, title: content.slice(0, 64) }),
        });
        const created = result.session;
        chatId = created.session_id;
        newSessionIds.current.add(chatId);
        setActiveId(chatId);
        setSessions((current) => [created, ...current]);
      }
      const common = { session_id: chatId, repository_id: repositoryParts.repositoryId };
      let endpoint;
      let payload;
      if (selectedAgent === "mentor") {
        const context = await api("/agents/rag/query", session.access_token, {
          method: "POST",
          body: JSON.stringify({ ...common, question: content }),
        });
        if (!context.chunk_count) {
          throw new Error("Code mentor needs an indexed repository. Index this repository or choose Repository Q&A to check what is available.");
        }
        endpoint = "/agents/mentor";
        payload = { ...common, message: content, repository_context: context.answer };
      } else if (selectedAgent === "pr-reviewer") {
        endpoint = "/agents/pr-review";
        payload = {
          session_id: chatId,
          owner: repositoryParts.repositoryId.split("/")[0],
          repo: repositoryParts.repositoryId.split("/")[1],
          pull_number: Number(pullNumber),
          additional_context: content.replace(/(?:pull request|pr)?\s*#\d+\b/i, "").trim(),
        };
      } else if (selectedAgent === "repository-rag") {
        endpoint = "/agents/rag/query";
        payload = { ...common, question: content };
      } else if (selectedAgent === "documentation") {
        endpoint = "/agents/documentation";
        payload = {
          session_id: chatId,
          request: {
            repository: { repo_url: repositoryParts.repositoryUrl },
            explanation_type: "repository",
            target_audience: "intermediate",
            output_mode: "markdown",
          },
        };
      } else if (selectedAgent === "repository-discovery") {
        endpoint = "/agents/repository-discovery";
        payload = { session_id: chatId, skills: content.split(/[,;\n]/).map((skill) => skill.trim()).filter(Boolean).slice(0, 30) };
      } else if (selectedAgent === "profile") {
        endpoint = "/agents/profile";
        payload = { session_id: chatId, profile: { skills: content } };
      } else {
        endpoint = "/agents/orchestrator";
        payload = { ...common, message: content, repository_context: "" };
      }

      const result = await api(endpoint, session.access_token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const answer = responseText(result);
      if (!answer.trim()) throw new Error(`${activeAgent.name} returned an empty response. Please retry.`);
      setMessages((current) => [...current, { id: `reply-${Date.now()}`, role: "assistant", content: answer }]);
    } catch (error) {
      setNotice(error.message);
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setDraft(content);
    } finally {
      setBusy(false);
    }
  }

  async function deleteSession(event, item) {
    event.stopPropagation();
    try {
      await api(`/agents/sessions/${encodeURIComponent(item.session_id)}`, session.access_token, { method: "DELETE" });
      setSessions((current) => current.filter((chat) => chat.session_id !== item.session_id));
      if (activeId === item.session_id) startFresh();
    } catch (error) {
      setNotice(error.message);
    }
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
    setSessions([]);
    startFresh();
  }

  if (!session?.access_token) {
    return <AuthScreen onAuthenticated={(authSession, user) => { setSession({ ...authSession, email: user?.email }); setEmail(user?.email || ""); }} />;
  }

  const initials = (email || "OF").slice(0, 2).toUpperCase();
  return (
    <main className={`workspace ${mobileMenu ? "menu-open" : ""}`} data-theme={theme}>
      <aside className="sidebar">
        <div className="sidebar-head">
          <a className="wordmark" href="#workspace" aria-label="OpenForge home"><span className="mark"><Command size={18} /></span>OpenForge</a>
          <button className="icon-button mobile-close" type="button" aria-label="Close menu" onClick={() => setMobileMenu(false)}><X size={18} /></button>
        </div>
        <button className="new-chat" type="button" onClick={startFresh}><Plus size={17} />New contribution chat<span>⌘ K</span></button>
        <div className="side-label">WORKSPACE</div>
        <button className="nav-item selected" type="button" onClick={startFresh}><Layers3 size={17} />My workspace</button>
        <div className="side-label history-label">RECENT CHATS <span>{sessions.length}</span></div>
        <div className="session-list">
          {sessions.length ? sessions.map((item) => (
            <div className="session-entry" key={item.session_id}>
              <button className={`session-link ${activeId === item.session_id ? "current" : ""}`} type="button" onClick={() => selectSession(item)} title={item.title}>
                <MessageSquare size={15} /><span>{item.title || item.repository_id || "New chat"}</span>
              </button>
              <button className="delete-chat" type="button" aria-label={`Delete ${item.title || "chat"}`} onClick={(event) => deleteSession(event, item)}><X size={13} /></button>
            </div>
          )) : <p className="empty-history">Your contribution chats will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <div className="sidebar-status"><span className="live-dot" /><span>Agents ready</span><span className="status-caption">7 AGENTS</span></div>
          <button className="profile-row" type="button" onClick={logout} title="Sign out">
            <span className="avatar">{initials}</span><span className="profile-text"><strong>{email || "Developer"}</strong><small>Personal workspace</small></span><LogOut size={16} />
          </button>
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu-button" type="button" aria-label="Open menu" onClick={() => setMobileMenu(true)}><Menu size={19} /></button>
          <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{activeSession?.title || "New contribution"}</strong></div>
          <div className="topbar-actions">
            <button className="icon-button theme-toggle" type="button" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}<span>{theme === "dark" ? "Light" : "Dark"}</span></button>
            <span className="connection"><span className="live-dot" />CONNECTED</span>
            <select className="agent-mode" aria-label="Select agent" value={selectedAgent} onChange={(event) => setSelectedAgent(event.target.value)}>
              {AGENTS.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          </div>
        </header>

        <div className="chat-layout">
          <section className="conversation">
            <div className="repo-toolbar">
              <div className="repo-label"><Github size={16} /><span>{selectedAgent === "repository-discovery" ? "OPTIONAL REPO" : "REPOSITORY"}</span></div>
              <div className="repo-input-wrap"><input aria-label="GitHub repository" value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={selectedAgent === "repository-discovery" ? "Not needed for discovery" : "owner/repository"} spellCheck="false" /><ChevronDown size={15} /></div>
              <button className="repo-action" type="button" title="Open repository" onClick={openRepository}><ExternalLink size={15} /></button>
            </div>
            {messages.length === 0 && !loading ? (
              <div className="welcome-area">
                <div className="welcome-marker"><Sparkles size={17} /></div>
                <p className="eyebrow dark-eyebrow">YOUR OPEN-SOURCE COPILOT</p>
                <h1>Good work starts<br />with a <em>first question.</em></h1>
                <p className="welcome-copy">Choose a direction, or tell me what you’re hoping to build. I’ll help you find a clear path into the code.</p>
                <div className="starter-grid">
                  {STARTERS.map(({ icon: Icon, title, prompt }, index) => (
                    <button className="starter-card" key={title} type="button" onClick={() => sendMessage(prompt)}>
                      <span className={`starter-icon starter-${index}`}><Icon size={17} /></span><strong>{title}</strong><ArrowUp size={15} className="starter-arrow" />
                    </button>
                  ))}
                </div>
                <div className="welcome-foot"><span className="foot-rule" /><span>GROUNDED IN YOUR REPOSITORY</span><span className="foot-rule" /></div>
              </div>
            ) : (
              <div className="messages" ref={scrollRef} aria-live="polite">
                {loading && <div className="loading-row"><LoaderCircle className="spin" size={17} /> Loading conversation</div>}
                {messages.map((message) => <article className={`message-row ${message.role === "user" ? "user-message" : "agent-message"}`} key={message.id}>
                  <span className={`message-avatar ${message.role === "user" ? "user-avatar" : "agent-avatar"}`}>{message.role === "user" ? initials : <Sparkles size={15} />}</span>
                  <div className="message-body"><span className="message-author">{message.role === "user" ? "YOU" : "OPENFORGE"}</span><p>{message.content}</p></div>
                </article>)}
                {busy && <div className="loading-row"><span className="message-avatar agent-avatar"><Sparkles size={15} /></span><LoaderCircle className="spin" size={16} /> OpenForge is reading the room...</div>}
              </div>
            )}
            <div className="composer-area">
              {notice && <div className="inline-notice" role="status"><span>{notice}</span><button type="button" aria-label="Dismiss" onClick={() => setNotice("")}><X size={14} /></button></div>}
              <form className="composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
                <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} placeholder={selectedAgent === "pr-reviewer" ? "Review a pull request, e.g. acme/repo #42..." : selectedAgent === "profile" ? "List your skills, languages, and contribution interests..." : selectedAgent === "repository-discovery" ? "Which skills or technologies should repositories use?" : "Ask about the code, issues, or your next contribution..."} rows={2} aria-label="Message OpenForge" />
                <div className="composer-footer"><span><kbd>↵</kbd> to send <span className="hint-divider">·</span> <kbd>⇧ ↵</kbd> for a new line</span><button className="send-button" type="submit" aria-label="Send message" disabled={!draft.trim() || busy}><ArrowUp size={17} /></button></div>
              </form>
              {selectedAgent === "mentor" && <p className="composer-note">Code mentor requires this repository to be indexed first.</p>}
              {selectedAgent === "pr-reviewer" && <p className="composer-note">Include a pull request number, such as #42.</p>}
              <p className="composer-note">OpenForge can make mistakes. Review suggestions before you contribute.</p>
            </div>
          </section>

          <aside className="context-panel">
            <div className="context-heading"><span>SESSION CONTEXT</span><button className="icon-button" aria-label="Context options" type="button"><Settings2 size={16} /></button></div>
            <div className="context-repo">
              <div className="repo-monogram"><Github size={22} /></div>
              <div><strong>{repository || (selectedAgent === "repository-discovery" ? "Skill-based search" : "No repository")}</strong><span>{repository ? "GitHub repository" : selectedAgent === "repository-discovery" ? "Search across GitHub" : "Connect one to begin"}</span></div>
              <span className={`context-state ${repository || selectedAgent === "repository-discovery" ? "state-ready" : ""}`} title={repository ? "Repository selected" : selectedAgent === "repository-discovery" ? "Repository is optional" : "Repository required"} />
            </div>
            <div className="context-divider" />
            <div className="context-section-title">AVAILABLE AGENTS <span>{String(AGENTS.length).padStart(2, "0")}</span></div>
            <div className="agent-list">
              {AGENTS.map(({ id, name, detail, icon: Icon, tone }) => (
                <button className={`agent-entry ${selectedAgent === id ? "active-agent" : ""}`} key={id} type="button" aria-pressed={selectedAgent === id} onClick={() => setSelectedAgent(id)}>
                  <span className={`agent-icon ${tone}`}><Icon size={15} /></span>
                  <span><strong>{name}</strong><small>{detail}</small></span>
                  {selectedAgent === id && <span className="agent-online" />}
                </button>
              ))}
            </div>
            <div className="context-divider" />
            <div className="context-section-title">ACTIVITY <Clock3 size={14} /></div>
            <div className="activity-item"><span className="activity-pip" /><span>{activeSession ? "Conversation resumed" : "Workspace ready"}<small>{activeSession ? "Active session" : "Waiting for your first prompt"}</small></span></div>
            <div className="context-bottom"><div className="context-tip-icon"><GitBranch size={16} /></div><div><strong>Small steps ship.</strong><p>Every great open-source project started with someone asking a question.</p></div></div>
          </aside>
        </div>
      </section>
      {mobileMenu && <button className="scrim" aria-label="Close navigation" type="button" onClick={() => setMobileMenu(false)} />}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
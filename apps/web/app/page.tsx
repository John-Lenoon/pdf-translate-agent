"use client";

import { useEffect, useRef, useState } from "react";

import { API_BASE_URL, errorMessage, requestJson } from "../lib/api.mjs";

type Run = { id: string; status: string; progress: { done: number; total: number }; error_code?: string | null; error_message?: string | null; context_degraded: boolean };
type Segment = { id: string; ordinal: number; page_number: number; chapter_id?: string | null; source_text: string; translation?: string | null; status: string; last_error?: string | null; context_before: string[]; context_after: string[] };
type Entity = { id: number; source_name: string; target_name: string; first_segment_id: string };
type Artifact = { name: string; size: number; download_url: string };
type View = "review" | "entities" | "artifacts";

const TERMINAL = new Set(["completed", "failed", "render_failed", "cancelled"]);
const JUDGE_LABELS = ["ok", "fidelity", "coherence", "entity", "formatting", "other"];

export default function Home() {
  const [pdf, setPdf] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [glossaryText, setGlossaryText] = useState("[]");
  const [run, setRun] = useState<Run | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pageFilter, setPageFilter] = useState("all");
  const [view, setView] = useState<View>("review");
  const [judgeLabel, setJudgeLabel] = useState("ok");
  const [judgeNotes, setJudgeNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const idempotencyKey = useRef(crypto.randomUUID());

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run");
    if (!runId) return;
    requestJson(`/runs/${runId}`)
      .then(setRun)
      .catch((loadError) => setError(errorMessage(loadError)));
  }, []);

  useEffect(() => {
    if (!run?.id) return;
    const runId = run.id;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function refresh() {
      try {
        const [nextRun, nextSegments, nextEntities, nextArtifacts] = await Promise.all([
          requestJson(`/runs/${runId}`),
          requestJson(`/runs/${runId}/segments`),
          requestJson(`/runs/${runId}/entities`),
          requestJson(`/runs/${runId}/artifacts`),
        ]);
        if (cancelled) return;
        setRun(nextRun);
        setSegments(nextSegments);
        setEntities(nextEntities);
        setArtifacts(nextArtifacts.files);
        setSelectedId((current) => current ?? nextSegments[0]?.id ?? null);
        setError(null);
        if (!TERMINAL.has(nextRun.status)) timer = setTimeout(refresh, 1500);
      } catch (refreshError) {
        if (!cancelled) {
          setError(errorMessage(refreshError));
          timer = setTimeout(refresh, 3000);
        }
      }
    }

    void refresh();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [run?.id, refreshKey]);

  async function createRun() {
    setBusy(true);
    setError(null);
    try {
      const glossary = JSON.parse(glossaryText);
      if (!Array.isArray(glossary)) throw new Error("Glossary must be a JSON array.");
      if (!pdf) throw new Error("Choose a PDF file first.");
      const form = new FormData();
      form.append("file", pdf);
      form.append("idempotency_key", idempotencyKey.current);
      form.append("glossary", JSON.stringify(glossary));
      const created = await requestJson("/runs/upload", {
        method: "POST",
        body: form,
      });
      await requestJson(`/runs/${created.run_id}/start`, { method: "POST" });
      setRun(await requestJson(`/runs/${created.run_id}`));
      window.history.replaceState(null, "", `?run=${created.run_id}`);
      idempotencyKey.current = crypto.randomUUID();
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  function choosePdf(file: File | undefined) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    setError(null);
    setPdf(file);
  }

  async function cancelRun() {
    if (!run) return;
    setBusy(true);
    try {
      await requestJson(`/runs/${run.id}/cancel`, { method: "POST" });
      setRefreshKey((value) => value + 1);
    } catch (cancelError) {
      setError(errorMessage(cancelError));
    } finally {
      setBusy(false);
    }
  }

  async function resumeRun() {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      await requestJson(`/runs/${run.id}/start`, { method: "POST" });
      setRefreshKey((value) => value + 1);
    } catch (resumeError) {
      setError(errorMessage(resumeError));
    } finally {
      setBusy(false);
    }
  }

  async function submitJudgment() {
    if (!run || !selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await requestJson(`/runs/${run.id}/segments/${selectedId}/retranslate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: judgeLabel, notes: judgeNotes }),
      });
      setJudgeNotes("");
      setRefreshKey((value) => value + 1);
    } catch (judgeError) {
      setError(errorMessage(judgeError));
    } finally {
      setBusy(false);
    }
  }

  const pages = [...new Set(segments.map((segment) => segment.page_number))];
  const visibleSegments = pageFilter === "all" ? segments : segments.filter((segment) => segment.page_number === Number(pageFilter));
  const selected = segments.find((segment) => segment.id === selectedId) ?? null;
  const progress = run?.progress.total ? Math.round((run.progress.done / run.progress.total) * 100) : 0;

  return (
    <main>
      <header>
        <div><p className="eyebrow">LOCAL WORKSPACE</p><h1>Literary translation desk</h1></div>
        <div className={`status status-${run?.status ?? "ready"}`}>{run?.status ?? "ready"}</div>
      </header>

      {!run ? (
        <section className="setup" aria-label="Create translation run">
          <div className={dragging ? "file-drop active" : "file-drop"} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); choosePdf(event.dataTransfer.files[0]); }}>
            <input id="pdf-file" type="file" accept="application/pdf,.pdf" onChange={(event) => choosePdf(event.target.files?.[0])} />
            <label htmlFor="pdf-file"><strong>{pdf ? pdf.name : "Choose a PDF"}</strong><span>{pdf ? `${Math.ceil(pdf.size / 1024)} KB selected` : "Drag and drop a digital-text PDF here, or click to browse"}</span></label>
          </div>
          <label>User glossary (JSON)<textarea value={glossaryText} onChange={(event) => setGlossaryText(event.target.value)} rows={3} spellCheck={false} /></label>
          <button disabled={!pdf || busy} onClick={createRun}>{busy ? "Uploading..." : "Create run"}</button>
        </section>
      ) : (
        <>
          <section className="runbar" aria-label="Run progress">
            <div><span>Progress</span><strong>{run.progress.done} / {run.progress.total}</strong></div>
            <div className="track" aria-label={`${progress}% complete`}><i style={{ width: `${progress}%` }} /></div>
            <div className="run-actions">
              {!TERMINAL.has(run.status) ? <button className="secondary danger" disabled={busy} onClick={cancelRun}>Cancel</button> : null}
              {["failed", "render_failed", "cancelled"].includes(run.status) ? <button className="secondary" disabled={busy} onClick={resumeRun}>Resume</button> : null}
            </div>
          </section>
          <nav className="tabs" aria-label="Run views">
            {(["review", "entities", "artifacts"] as View[]).map((item) => (
              <button key={item} className={view === item ? "tab active" : "tab"} onClick={() => setView(item)}>
                {item} {item === "entities" ? `(${entities.length})` : item === "artifacts" ? `(${artifacts.length})` : ""}
              </button>
            ))}
          </nav>
        </>
      )}

      {error ? <div className="error" role="alert"><strong>Request failed</strong><span>{error}</span></div> : null}
      {run?.context_degraded ? <div className="warning" role="status">Chapter context is degraded. See run events and warnings.</div> : null}
      {run?.error_code ? <div className="error" role="alert"><strong>{run.error_code}</strong><span>{run.error_message}</span></div> : null}

      {run && view === "review" ? (
        <section className="workspace">
          <aside>
            <label className="page-filter">Page<select value={pageFilter} onChange={(event) => setPageFilter(event.target.value)}><option value="all">All pages</option>{pages.map((page) => <option key={page} value={page}>{page}</option>)}</select></label>
            <div className="segment-list">
              {visibleSegments.map((segment) => (
                <button className={selectedId === segment.id ? "segment active" : "segment"} key={segment.id} onClick={() => setSelectedId(segment.id)}>
                  <span>{String(segment.ordinal).padStart(3, "0")} · p.{segment.page_number}</span><em>{segment.status}</em><p>{segment.source_text.slice(0, 100)}</p>
                </button>
              ))}
            </div>
          </aside>
          <article>
            {selected ? (
              <>
                <div className="article-head"><span>SEGMENT {selected.ordinal} · PAGE {selected.page_number}</span><span>{selected.chapter_id} · {selected.status}</span></div>
                {selected.last_error ? <div className="error"><strong>Segment error</strong><span>{selected.last_error}</span></div> : null}
                <div className="context-strip"><div><h2>Before</h2><p>{selected.context_before.join(" ") || "None"}</p></div><div><h2>After</h2><p>{selected.context_after.join(" ") || "None"}</p></div></div>
                <div className="columns"><div><h2>Original</h2><p>{selected.source_text}</p></div><div><h2>Translation</h2><p>{selected.translation || "Pending"}</p></div></div>
                {run.status === "completed" || run.status === "retranslate_queued" ? (
                  <div className="judge">
                    <label>Judge label<select value={judgeLabel} onChange={(event) => setJudgeLabel(event.target.value)}>{JUDGE_LABELS.map((label) => <option key={label}>{label}</option>)}</select></label>
                    <label>Notes<textarea rows={3} value={judgeNotes} onChange={(event) => setJudgeNotes(event.target.value)} /></label>
                    <button disabled={busy} onClick={submitJudgment}>{busy ? "Submitting..." : "Submit judgment"}</button>
                  </div>
                ) : null}
              </>
            ) : <div className="empty"><h2>No segment selected</h2></div>}
          </article>
        </section>
      ) : null}

      {run && view === "entities" ? (
        <section className="table-view"><table><thead><tr><th>Source name</th><th>Canonical Chinese</th><th>First segment</th></tr></thead><tbody>{entities.map((entity) => <tr key={entity.id}><td>{entity.source_name}</td><td>{entity.target_name}</td><td>{entity.first_segment_id}</td></tr>)}</tbody></table>{!entities.length ? <p className="empty-line">No person entities recorded.</p> : null}</section>
      ) : null}

      {run && view === "artifacts" ? (
        <section className="table-view"><table><thead><tr><th>Artifact</th><th>Size</th><th></th></tr></thead><tbody>{artifacts.map((artifact) => <tr key={artifact.name}><td>{artifact.name}</td><td>{Math.ceil(artifact.size / 1024)} KB</td><td><a href={`${API_BASE_URL}${artifact.download_url}`}>Download</a></td></tr>)}</tbody></table>{!artifacts.length ? <p className="empty-line">No artifacts available.</p> : null}</section>
      ) : null}
    </main>
  );
}

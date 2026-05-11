import { useMemo, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const sectionCard =
  "rounded-2xl border border-slate-800/80 bg-slate-900/80 p-5 shadow-lg shadow-slate-950/40 backdrop-blur";

function formatCurrency(value) {
  if (typeof value !== "number") return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value) {
  if (typeof value !== "number") return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function StepBadge({ status }) {
  const colorClass =
    status === "completed"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
      : status === "skipped"
        ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
        : "bg-rose-500/15 text-rose-300 border-rose-500/40";

  return (
    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${colorClass}`}>
      {status || "unknown"}
    </span>
  );
}

function EmptyState({ label }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-400">
      {label}
    </div>
  );
}

export default function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const canSubmit = query.trim().length > 0 && !loading;

  const metrics = useMemo(() => {
    if (!result?.orchestration_summary) return null;
    const summary = result.orchestration_summary;
    return [
      { label: "Candidates", value: summary.candidates_retrieved ?? 0 },
      { label: "Processed", value: summary.customers_processed ?? 0 },
      { label: "Recommendations", value: summary.recommendations_generated ?? 0 },
      { label: "Outreach", value: summary.outreach_messages_generated ?? 0 },
    ];
  }, [result]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed with status ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error while analyzing query.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-100">
      <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-6">
          <p className="text-xs uppercase tracking-[0.2em] text-sky-300">Agentic Banking CRM</p>
          <h1 className="mt-2 text-3xl font-semibold text-white sm:text-4xl">Relationship Manager Dashboard</h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-300 sm:text-base">
            Enter an RM query to generate customer intelligence, product recommendations, outreach copy, and orchestration trace in one view.
          </p>
        </header>

        <section className={`${sectionCard} mb-6`}>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block text-sm font-medium text-slate-200" htmlFor="rm-query">
              RM Query
            </label>
            <textarea
              id="rm-query"
              rows={3}
              placeholder="Example: Find high-value customers likely to need investment advisory services."
              className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-sky-500 transition focus:ring-2"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={!canSubmit}
                className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              >
                {loading ? "Analyzing..." : "Submit Query"}
              </button>
              <span className="text-xs text-slate-400">Endpoint: {API_BASE_URL}/analyze</span>
            </div>
          </form>
        </section>

        {loading && (
          <section className={`${sectionCard} mb-6 border-sky-500/30`}>
            <p className="text-sm text-sky-200">Processing your request and orchestrating customer insights...</p>
          </section>
        )}

        {error && (
          <section className={`${sectionCard} mb-6 border-rose-500/40`}>
            <h2 className="mb-2 text-lg font-semibold text-rose-300">Error</h2>
            <p className="max-h-40 overflow-auto rounded-lg bg-rose-950/30 p-3 text-sm text-rose-100">{error}</p>
          </section>
        )}

        {result && (
          <div className="space-y-6 pb-6">
            <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {metrics?.map((metric) => (
                <article key={metric.label} className={`${sectionCard} border-slate-800 bg-slate-900`}>
                  <p className="text-xs uppercase tracking-wider text-slate-400">{metric.label}</p>
                  <p className="mt-1 text-2xl font-semibold text-white">{metric.value}</p>
                </article>
              ))}
            </section>

            <section className={`${sectionCard} border-sky-500/30`}>
              <h2 className="mb-3 text-xl font-semibold text-sky-200">1. Interpreted Intent</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Intent Name</p>
                  <p className="mt-1 text-base font-medium text-white">{result.interpreted_intent?.name || "-"}</p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Focus Recommendation</p>
                  <p className="mt-1 text-base font-medium text-white">{result.interpreted_intent?.focus_recommendation_type || "-"}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-slate-200">{result.interpreted_intent?.description || "No interpreted intent returned."}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {(result.interpreted_intent?.matched_keywords || []).map((keyword) => (
                  <span key={keyword} className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs text-sky-200">
                    {keyword}
                  </span>
                ))}
                {(result.interpreted_intent?.matched_keywords || []).length === 0 && <EmptyState label="No matched keywords detected." />}
              </div>
            </section>

            <section className={`${sectionCard} border-emerald-500/30`}>
              <h2 className="mb-4 text-xl font-semibold text-emerald-200">2. Shortlisted Customers</h2>
              {(result.shortlisted_customers || []).length === 0 ? (
                <EmptyState label="No customers shortlisted for this query." />
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {result.shortlisted_customers.map((customer) => (
                    <article key={customer.customer_id} className="rounded-xl border border-emerald-700/30 bg-emerald-950/10 p-4">
                      <div className="mb-3 flex items-center justify-between">
                        <p className="text-sm font-semibold text-white">{customer.customer_id}</p>
                        <span className="rounded-md bg-emerald-500/20 px-2 py-1 text-xs text-emerald-200">
                          Score: {customer.relationship_score}
                        </span>
                      </div>
                      <div className="space-y-1.5 text-sm text-slate-200">
                        <p>Income: {formatCurrency(customer.income)}</p>
                        <p>Credit Score: {customer.credit_score}</p>
                        <p>Loan Intent: {customer.loan_intent}</p>
                        <p>Age: {customer.age ?? "-"}</p>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className={`${sectionCard} border-violet-500/30`}>
              <h2 className="mb-4 text-xl font-semibold text-violet-200">3. Recommendations</h2>
              {(result.recommendations || []).length === 0 ? (
                <EmptyState label="No recommendations generated." />
              ) : (
                <div className="space-y-3">
                  {result.recommendations.map((group) => (
                    <article key={group.customer_id} className="rounded-xl border border-violet-700/30 bg-violet-950/10 p-4">
                      <p className="mb-3 text-sm font-semibold text-violet-100">{group.customer_id}</p>
                      <div className="space-y-2">
                        {(group.recommendations || []).map((rec, index) => (
                          <div key={`${group.customer_id}-${rec.recommendation_type}-${index}`} className="rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <p className="text-sm font-medium text-white">{rec.recommendation_type}</p>
                              <span className="rounded bg-violet-500/20 px-2 py-1 text-xs text-violet-100">
                                Confidence: {formatPercent(rec.confidence_score)}
                              </span>
                            </div>
                            <p className="text-sm text-slate-300">{rec.recommendation_reason}</p>
                          </div>
                        ))}
                        {(group.recommendations || []).length === 0 && <EmptyState label="No recommendation items for this customer." />}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className={`${sectionCard} border-amber-500/30`}>
              <h2 className="mb-4 text-xl font-semibold text-amber-200">4. Outreach Messages</h2>
              {(result.outreach_messages || []).length === 0 ? (
                <EmptyState label="No outreach generated for this query." />
              ) : (
                <div className="space-y-3">
                  {result.outreach_messages.map((message) => (
                    <article key={message.customer_id} className="rounded-xl border border-amber-700/30 bg-amber-950/10 p-4">
                      <p className="mb-3 text-sm font-semibold text-amber-100">{message.customer_id}</p>
                      <div className="grid gap-3 lg:grid-cols-2">
                        <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                          <p className="mb-1 text-xs uppercase tracking-wide text-slate-400">Email</p>
                          <p className="text-sm text-slate-200">{message.personalized_email}</p>
                        </div>
                        <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                          <p className="mb-1 text-xs uppercase tracking-wide text-slate-400">SMS</p>
                          <p className="text-sm text-slate-200">{message.sms_message}</p>
                        </div>
                      </div>
                      <div className="mt-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                        <p className="mb-1 text-xs uppercase tracking-wide text-slate-400">Summary</p>
                        <p className="text-sm text-slate-200">{message.outreach_summary}</p>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className={`${sectionCard} border-cyan-500/30`}>
              <h2 className="mb-4 text-xl font-semibold text-cyan-200">5. Orchestration Summary & Steps</h2>
              <div className="mb-4 grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Generated At</p>
                  <p className="mt-1 text-sm text-slate-200">{result.orchestration_summary?.generated_at || "-"}</p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Original Query</p>
                  <p className="mt-1 text-sm text-slate-200">{result.orchestration_summary?.query || "-"}</p>
                </div>
              </div>

              {(result.orchestration_summary?.steps || []).length === 0 ? (
                <EmptyState label="No orchestration steps were returned." />
              ) : (
                <div className="space-y-3">
                  {result.orchestration_summary.steps.map((step, index) => (
                    <article key={`${step.name}-${index}`} className="rounded-xl border border-cyan-700/30 bg-cyan-950/10 p-4">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{step.name}</p>
                        <StepBadge status={step.status} />
                      </div>
                      <p className="text-sm text-slate-300">{step.detail || "No details provided."}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

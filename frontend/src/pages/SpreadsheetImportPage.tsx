import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, FileUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";

interface ImportIssue {
  row: number;
  reason: string;
  detail: string;
}

interface ImportPlan {
  incomes: number;
  expenses: number;
  transfers: number;
  goal_contributions: number;
  excluded: number;
  opening_balances: Record<string, string>;
  accounts: string[];
  categories: number;
  subcategories: number;
  participants: string[];
  goals: number;
  total_rows: number;
  issues: ImportIssue[];
  can_apply: boolean;
  existing_transactions: number;
}

interface ImportResult {
  accounts: number;
  categories: number;
  participants: number;
  goals: number;
  transactions: number;
  transfers: number;
  goal_contributions: number;
  issues: ImportIssue[];
}

async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("transactions", file);
  // Не через api/client.ts: там на каждый запрос ставится
  // Content-Type: application/json, а multipart браузер обязан собрать сам,
  // вместе с границей блоков.
  const response = await fetch(`/api${path}`, { method: "POST", body, credentials: "same-origin" });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw) as { detail?: string };
      throw new Error(parsed.detail ?? raw);
    } catch (err) {
      throw err instanceof Error ? err : new Error(raw);
    }
  }
  return (await response.json()) as T;
}

/**
 * Перенос истории из табличного учёта.
 *
 * Два шага намеренно: сначала предпросмотр, который ничего не пишет, потом
 * применение. Импорт четырёх лет чужой истории делают один раз и не
 * откатывают — человек должен сначала увидеть, что получится.
 */
export function SpreadsheetImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (picked: File) => {
    setFile(picked);
    setPlan(null);
    setResult(null);
    setError(null);
    setBusy(true);
    try {
      setPlan(await upload<ImportPlan>("/import/spreadsheet/preview", picked));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await upload<ImportResult>("/import/spreadsheet/apply", file));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("spreadsheet.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="max-w-2xl text-sm text-text-muted">{t("spreadsheet.intro")}</p>

          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(event) => {
              const picked = event.target.files?.[0];
              if (picked) void handleFile(picked);
            }}
          />
          <Button onClick={() => fileInput.current?.click()} disabled={busy} className="gap-1.5">
            <FileUp size={15} />
            {file ? file.name : t("spreadsheet.pickFile")}
          </Button>

          {error && <p className="text-sm text-danger">{error}</p>}
        </CardContent>
      </Card>

      {plan && !result && (
        <Card>
          <CardHeader>
            <CardTitle>{t("spreadsheet.planTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              <Row label={t("spreadsheet.incomes")} value={plan.incomes} />
              <Row label={t("spreadsheet.expenses")} value={plan.expenses} />
              <Row label={t("spreadsheet.transfers")} value={plan.transfers} />
              <Row label={t("spreadsheet.goalMoves")} value={plan.goal_contributions} />
              <Row label={t("spreadsheet.excluded")} value={plan.excluded} />
              <Row label={t("spreadsheet.accounts")} value={plan.accounts.length} />
              <Row label={t("spreadsheet.categories")} value={`${plan.categories} / ${plan.subcategories}`} />
              <Row label={t("spreadsheet.goals")} value={plan.goals} />
              <Row label={t("spreadsheet.totalRows")} value={plan.total_rows} />
            </dl>

            {Object.keys(plan.opening_balances).length > 0 && (
              <div className="rounded border border-gridline p-3">
                <p className="mb-1 text-sm font-medium text-text-primary">{t("spreadsheet.openingTitle")}</p>
                <p className="mb-2 text-xs text-text-muted">{t("spreadsheet.openingHint")}</p>
                <ul className="space-y-0.5 text-sm">
                  {Object.entries(plan.opening_balances).map(([name, amount]) => (
                    <li key={name} className="flex justify-between gap-4">
                      <span className="text-text-muted">{name}</span>
                      <span className="tabular-nums text-text-primary">{amount}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {plan.issues.length > 0 && (
              <div className="rounded border border-gridline p-3">
                <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-text-primary">
                  <AlertTriangle size={15} className="text-warning" />
                  {t("spreadsheet.issuesTitle", { count: plan.issues.length })}
                </p>
                <ul className="max-h-48 space-y-0.5 overflow-y-auto text-xs text-text-muted">
                  {plan.issues.slice(0, 50).map((issue) => (
                    <li key={`${issue.row}-${issue.reason}`}>
                      {t("spreadsheet.issueRow", { row: issue.row })} — {issue.reason} {issue.detail}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {plan.can_apply ? (
              <Button onClick={() => void handleApply()} disabled={busy}>
                {busy ? t("spreadsheet.applying") : t("spreadsheet.apply")}
              </Button>
            ) : (
              <p className="text-sm text-danger">
                {t("spreadsheet.blocked", { count: plan.existing_transactions })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <CheckCircle2 size={17} className="text-success" />
              {t("spreadsheet.doneTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              <Row label={t("spreadsheet.accounts")} value={result.accounts} />
              <Row label={t("spreadsheet.categoriesCreated")} value={result.categories} />
              <Row label={t("spreadsheet.participants")} value={result.participants} />
              <Row label={t("spreadsheet.goals")} value={result.goals} />
              <Row label={t("spreadsheet.transactionsCreated")} value={result.transactions} />
              <Row label={t("spreadsheet.transfers")} value={result.transfers} />
              <Row label={t("spreadsheet.goalMoves")} value={result.goal_contributions} />
            </dl>
            <p className="text-sm text-text-muted">{t("spreadsheet.doneHint")}</p>
            <Button onClick={() => navigate("/transactions")}>{t("spreadsheet.openTransactions")}</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-gridline pb-1">
      <dt className="text-text-muted">{label}</dt>
      <dd className="tabular-nums font-medium text-text-primary">{value}</dd>
    </div>
  );
}

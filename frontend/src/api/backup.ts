import { api } from "@/api/client";
import { t } from "@/lib/i18n";

export async function exportBackup(): Promise<void> {
  // Прямой fetch, а не request() из api/client.ts: ответ — файл, а не JSON.
  // Заголовок авторизации собирать больше не нужно, сессия живёт в куке —
  // но credentials указать обязательно, иначе браузер её не приложит и
  // выгрузка вернётся с 401.
  const response = await fetch("/api/backup/export", { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const date = new Date().toISOString().slice(0, 10);

  const link = document.createElement("a");
  link.href = url;
  link.download = `aurum-backup-${date}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function importBackup(file: File): Promise<void> {
  const text = await file.text();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(t("backup.invalidFile"));
  }
  await api.post<{ status: string }>("/backup/import", payload);
}

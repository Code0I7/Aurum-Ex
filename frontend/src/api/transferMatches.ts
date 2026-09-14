import { api } from "@/api/client";
import type { TransactionType, TransferCounterpart, TransferMatch } from "@/types";

/**
 * Перевод между своими счетами, записанный дважды: по выписке отправителя и
 * по выписке получателя. Сервер находит такие пары и только предлагает их
 * склеить — см. backend services/transfer_match_service.py.
 */
const BASE = "/transactions/transfer-matches";

export function fetchTransferMatches() {
  return api.get<TransferMatch[]>(BASE);
}

/** Сложилась бы вводимая операция в пару с уже записанной. Спрашивается
 * формой перед записью — как и проверка повторов дня. */
export function checkTransferMatch(params: {
  type: TransactionType;
  account_id: number;
  amount: string;
  date: string;
  transfer_account_id?: number | null;
  transfer_amount?: string | null;
}) {
  const query = new URLSearchParams({
    type: params.type,
    account_id: String(params.account_id),
    amount: params.amount,
    date: params.date,
  });
  if (params.transfer_account_id) query.set("transfer_account_id", String(params.transfer_account_id));
  if (params.transfer_amount) query.set("transfer_amount", params.transfer_amount);
  return api.get<TransferCounterpart[]>(`${BASE}/check?${query.toString()}`);
}

export function mergeTransferMatch(firstId: number, secondId: number) {
  return api.post<{ kept_id: number }>(`${BASE}/merge`, { first_id: firstId, second_id: secondId });
}

export function dismissTransferMatch(firstId: number, secondId: number) {
  return api.post<void>(`${BASE}/dismiss`, { first_id: firstId, second_id: secondId });
}

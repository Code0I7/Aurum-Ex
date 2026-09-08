import { api } from "@/api/client";
import type {
  InvestmentHolding,
  InvestmentHoldingDetail,
  InvestmentHoldingInput,
  InvestmentPortfolio,
  InvestmentPortfolioInput,
  InvestmentTrade,
  InvestmentTradeInput,
} from "@/types";

export function fetchPortfolios() {
  return api.get<InvestmentPortfolio[]>("/investments/portfolios");
}

export function createPortfolio(input: InvestmentPortfolioInput) {
  return api.post<InvestmentPortfolio>("/investments/portfolios", input);
}

export function updatePortfolio(id: number, input: Partial<InvestmentPortfolioInput>) {
  return api.patch<InvestmentPortfolio>(`/investments/portfolios/${id}`, input);
}

export function deletePortfolio(id: number) {
  return api.delete<void>(`/investments/portfolios/${id}`);
}

export function fetchHoldings(portfolioId?: number) {
  const query = portfolioId ? `?portfolio_id=${portfolioId}` : "";
  return api.get<InvestmentHolding[]>(`/investments/holdings${query}`);
}

export function fetchHolding(id: number) {
  return api.get<InvestmentHoldingDetail>(`/investments/holdings/${id}`);
}

export function createHolding(input: InvestmentHoldingInput) {
  return api.post<InvestmentHolding>("/investments/holdings", input);
}

export function updateHolding(id: number, input: Partial<InvestmentHoldingInput>) {
  return api.patch<InvestmentHolding>(`/investments/holdings/${id}`, input);
}

export function deleteHolding(id: number) {
  return api.delete<void>(`/investments/holdings/${id}`);
}

export function fetchTrades(holdingId: number) {
  return api.get<InvestmentTrade[]>(`/investments/holdings/${holdingId}/trades`);
}

export function addTrade(holdingId: number, input: InvestmentTradeInput) {
  return api.post<InvestmentHolding>(`/investments/holdings/${holdingId}/trades`, input);
}

export function deleteTrade(tradeId: number) {
  return api.delete<InvestmentHolding>(`/investments/trades/${tradeId}`);
}

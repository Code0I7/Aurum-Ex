import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addTrade,
  createHolding,
  createPortfolio,
  deleteHolding,
  deletePortfolio,
  deleteTrade,
  fetchHolding,
  fetchHoldings,
  fetchPortfolios,
  fetchTrades,
  updateHolding,
} from "@/api/investments";
import type { InvestmentHoldingInput, InvestmentPortfolioInput, InvestmentTradeInput } from "@/types";

// Сделка меняет позицию, список позиций и итог портфеля — сбрасывается всё
// дерево запросов раздела, а не один ключ.
function useInvalidateInvestments() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["investments"] });
}

export function useInvestmentPortfolios() {
  return useQuery({ queryKey: ["investments", "portfolios"], queryFn: fetchPortfolios });
}

export function useInvestmentHoldings(portfolioId?: number) {
  return useQuery({
    queryKey: ["investments", "holdings", portfolioId ?? null],
    queryFn: () => fetchHoldings(portfolioId),
  });
}

export function useInvestmentHolding(holdingId: number | null) {
  return useQuery({
    queryKey: ["investments", "holding", holdingId],
    queryFn: () => fetchHolding(holdingId as number),
    enabled: holdingId !== null,
  });
}

export function useInvestmentTrades(holdingId: number | null) {
  return useQuery({
    queryKey: ["investments", "trades", holdingId],
    queryFn: () => fetchTrades(holdingId as number),
    enabled: holdingId !== null,
  });
}

export function useCreatePortfolio() {
  const invalidate = useInvalidateInvestments();
  return useMutation({
    mutationFn: (input: InvestmentPortfolioInput) => createPortfolio(input),
    onSuccess: invalidate,
  });
}

export function useDeletePortfolio() {
  const invalidate = useInvalidateInvestments();
  return useMutation({ mutationFn: (id: number) => deletePortfolio(id), onSuccess: invalidate });
}

export function useCreateHolding() {
  const invalidate = useInvalidateInvestments();
  return useMutation({
    mutationFn: (input: InvestmentHoldingInput) => createHolding(input),
    onSuccess: invalidate,
  });
}

export function useUpdateHolding() {
  const invalidate = useInvalidateInvestments();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<InvestmentHoldingInput> }) =>
      updateHolding(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteHolding() {
  const invalidate = useInvalidateInvestments();
  return useMutation({ mutationFn: (id: number) => deleteHolding(id), onSuccess: invalidate });
}

export function useAddTrade() {
  const invalidate = useInvalidateInvestments();
  return useMutation({
    mutationFn: ({ holdingId, input }: { holdingId: number; input: InvestmentTradeInput }) =>
      addTrade(holdingId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteTrade() {
  const invalidate = useInvalidateInvestments();
  return useMutation({ mutationFn: (tradeId: number) => deleteTrade(tradeId), onSuccess: invalidate });
}

import { api } from "@/api/client";
import type {
  Asset,
  AssetInput,
  AssetUpdateInput,
  AssetValuation,
  AssetValuationInput,
  AssetValuationUpdateInput,
} from "@/types";

export function fetchAssets() {
  return api.get<Asset[]>("/assets");
}

export function createAsset(input: AssetInput) {
  return api.post<Asset>("/assets", input);
}

export function updateAsset(id: number, input: AssetUpdateInput) {
  return api.patch<Asset>(`/assets/${id}`, input);
}

export function addAssetValuation(id: number, input: AssetValuationInput) {
  return api.post<Asset>(`/assets/${id}/valuations`, input);
}

export function fetchAssetValuations(id: number) {
  return api.get<AssetValuation[]>(`/assets/${id}/valuations`);
}

export function updateAssetValuation(
  id: number,
  valuationId: number,
  input: AssetValuationUpdateInput,
) {
  return api.patch<Asset>(`/assets/${id}/valuations/${valuationId}`, input);
}

export function deleteAssetValuation(id: number, valuationId: number) {
  return api.delete<void>(`/assets/${id}/valuations/${valuationId}`);
}

export function deleteAsset(id: number) {
  return api.delete<void>(`/assets/${id}`);
}

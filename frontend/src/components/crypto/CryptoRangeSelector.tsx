import { PillSelector } from "@/components/layout/PillSelector";
import { useTranslation } from "@/lib/i18n";
import type { CryptoRange } from "@/types";

interface CryptoRangeSelectorProps {
  value: CryptoRange;
  onChange: (value: CryptoRange) => void;
}

export function CryptoRangeSelector({ value, onChange }: CryptoRangeSelectorProps) {
  const { t } = useTranslation();
  const ranges: Array<{ value: CryptoRange; label: string }> = [
    { value: "7d", label: "7D" },
    { value: "30d", label: "30D" },
    { value: "90d", label: "90D" },
    { value: "all", label: t("common.allShort") },
  ];

  return <PillSelector options={ranges} value={value} onChange={onChange} />;
}

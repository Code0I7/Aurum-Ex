import { PillSelector } from "@/components/layout/PillSelector";
import { useTranslation } from "@/lib/i18n";
import type { NetWorthRange } from "@/types";

interface RangeSelectorProps {
  value: NetWorthRange;
  onChange: (value: NetWorthRange) => void;
}

export function RangeSelector({ value, onChange }: RangeSelectorProps) {
  const { t } = useTranslation();
  const ranges: Array<{ value: NetWorthRange; label: string }> = [
    { value: "30d", label: "30D" },
    { value: "90d", label: "90D" },
    { value: "1y", label: "1Y" },
    { value: "5y", label: "5Y" },
    { value: "all", label: t("common.allShort") },
    // Свой период последним: готовые отвечают на «как было в последнее
    // время», этот — на «а что было тогда-то», и спрашивают его реже.
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  return <PillSelector options={ranges} value={value} onChange={onChange} />;
}

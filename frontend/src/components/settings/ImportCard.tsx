import { Link } from "react-router-dom";
import { FileUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useTranslation } from "@/lib/i18n";

/**
 * Перенос данных извне — в настройках, а не на вкладке операций.
 *
 * Там стояли две кнопки рядом, и обе назывались импортом: со стороны это
 * выглядело как одно и то же, сделанное дважды. На самом деле они разные и
 * нужны в разные моменты жизни:
 *
 *   перенос таблицы — один раз, на пустой установке, целиком: категории,
 *     счета, планы, вся история;
 *   выписка CSV — регулярно, дополняет уже накопленное операциями за месяц.
 *
 * Обе разовые для вкладки, где каждый день заводят операции, поэтому место
 * им здесь: рядом с резервной копией, среди действий над данными целиком.
 */
export function ImportCard() {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          {t("settings.importTitle")}
          <HelpBadge hintKey="help.import" />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-text-primary">{t("settings.importCsvTitle")}</p>
          <p className="text-xs leading-relaxed text-text-secondary">{t("settings.importCsvHint")}</p>
          <Link to="/transactions/import" className="inline-block">
            <Button variant="secondary">
              <FileUp size={16} />
              {t("transactions.importButton")}
            </Button>
          </Link>
        </div>

        <div className="space-y-2 border-t border-border pt-4">
          <p className="text-sm font-medium text-text-primary">{t("settings.importSheetTitle")}</p>
          <p className="text-xs leading-relaxed text-text-secondary">{t("settings.importSheetHint")}</p>
          <Link to="/transactions/import-spreadsheet" className="inline-block">
            <Button variant="ghost">
              <FileUp size={16} />
              {t("spreadsheet.buttonShort")}
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

import { Card, CardContent } from "@/components/ui/Card";
import { PillSelector } from "@/components/layout/PillSelector";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useTranslation, type Language } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";
import { DESIGNS, useDesign, type Design } from "@/lib/design";
import { SCALES, useScale, type Scale } from "@/lib/scale";

/** Язык, тема и оформление рядом — всё это чисто клиентские настройки
 * показа (в отличие от валюты, которая хранится на сервере), и вместе они
 * занимают одну карточку вместо трёх. На телефоне складываются в столбик.
 *
 * Тема и оформление — две независимые оси, и разводить их по разным
 * карточкам было бы честнее, но человек меняет их вместе: сначала выбирает
 * характер, потом светло или темно. */
export function PreferencesCard() {
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();
  const { design, setDesign } = useDesign();
  const { scale, setScale } = useScale();

  const languageOptions: Array<{ value: Language; label: string }> = [
    { value: "ru", label: t("settings.languageRussian") },
    { value: "en", label: t("settings.languageEnglish") },
  ];
  const themeOptions: Array<{ value: Theme; label: string }> = [
    { value: "light", label: t("settings.themeLight") },
    { value: "dark", label: t("settings.themeDark") },
    { value: "system", label: t("settings.themeSystem") },
  ];
  // Порядок задаётся в lib/design.ts: legacy там последним намеренно.
  const designLabels: Record<Design, string> = {
    gold: t("settings.designGold"),
    modern: t("settings.designModern"),
    legacy: t("settings.designLegacy"),
  };
  const designOptions = DESIGNS.map((value) => ({ value, label: designLabels[value] }));
  const scaleOptions: Array<{ value: Scale; label: string }> = SCALES.map((value) => ({
    value,
    label: `${value}%`,
  }));

  return (
    <Card>
      <CardContent className="grid grid-cols-1 gap-5 divide-y divide-border pt-4 sm:grid-cols-2 sm:gap-6 sm:divide-x sm:divide-y-0 sm:pt-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("settings.language")}</p>
          <div className="mt-2">
            <PillSelector options={languageOptions} value={language} onChange={setLanguage} />
          </div>
        </div>
        <div className="pt-5 sm:pl-6 sm:pt-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("settings.theme")}</p>
          <div className="mt-2">
            <PillSelector options={themeOptions} value={theme} onChange={setTheme} />
          </div>
        </div>
        {/* Оформление во всю ширину: названий три и они длиннее, чем
            «Светлая / Тёмная», — в половине карточки они переносились бы. */}
        <div className="pt-5 sm:col-span-2 sm:pt-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("settings.design")}</p>
          <div className="mt-2">
            <PillSelector options={designOptions} value={design} onChange={setDesign} />
          </div>
          <p className="mt-2 text-xs text-text-muted">{t(`settings.designHint.${design}` as never)}</p>
        </div>

        {/* Масштаб во всю ширину: пять значений в половине карточки
            сжимаются в нечитаемые огрызки. */}
        <div className="pt-5 sm:col-span-2 sm:pt-5">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
            {t("settings.scale")}
            <HelpBadge hintKey="help.scale" />
          </p>
          <div className="mt-2">
            <PillSelector options={scaleOptions} value={scale} onChange={setScale} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

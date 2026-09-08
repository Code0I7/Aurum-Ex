from pydantic import BaseModel


class FinancialAlert(BaseModel):
    key: str
    severity: str
    # Machine-readable params for the frontend to interpolate into its own
    # localized message template (keyed by `key`) — keeps alert copy out of
    # the backend so it can be translated without an API change.
    #
    # Строки допускаются наравне с числами: оповещение о платеже называет
    # счёт по имени, а перечислять имена в переводах нельзя — они у каждого
    # свои.
    params: dict[str, int | str]


class AlertsResponse(BaseModel):
    alerts: list[FinancialAlert]

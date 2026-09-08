from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_user
from app.api.routes import (
    accounts,
    auth,
    advice,
    assets,
    backup,
    budgets,
    cash_flow,
    categories,
    credits,
    currencies,
    crypto,
    dashboard,
    directories,
    goals,
    insights,
    investments,
    net_worth,
    plans,
    products,
    recurring,
    reports,
    settings as settings_routes,
    settlements,
    tags,
    transactions,
    work_periods,
    spreadsheet_import,
)
from app.core.config import APP_VERSION, get_settings
from app.db.seed import (
    seed_default_account,
    seed_default_app_settings,
    seed_default_categories,
    seed_default_currencies,
    seed_default_units,
)
from app.db.session import AsyncSessionLocal
from app.services.auth_service import seed_admin_from_env

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_default_categories(session)
        # Валюты и единицы засеваются до счёта: у счёта есть валюта, а у
        # позиции чека — единица, и ссылаться им должно быть на что.
        await seed_default_currencies(session)
        await seed_default_units(session)
        await seed_default_account(session)
        await seed_default_app_settings(session)
        # Учётная запись из .env, если она там задана. Пароль не задан —
        # приложение поднимается в режиме первичной настройки.
        await seed_admin_from_env(session)
    yield


app = FastAPI(
    title="Aurum-Ex API",
    version=APP_VERSION,
    lifespan=lifespan,
    # Docs live under /api/* because nginx only proxies that prefix to the
    # backend (see frontend/nginx.conf) — everything else falls through to
    # the SPA's index.html, which is why the defaults (/docs, /openapi.json)
    # would silently 404 through the reverse proxy.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS stays off unless someone deliberately opens it, and credentials are
# only granted to a pinned list. Starlette answers a credentialed "*" by
# echoing back whatever Origin asked instead of a literal "*" — so the two
# together turn any page the user happens to have open into an authenticated
# client of their instance, which is exactly what the README's "fine if it's
# only reachable from localhost" advice assumes can't happen.
cors_origins = settings.cors_origins_list
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials="*" not in cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Единственный незащищённый роутер: войти, не войдя, иначе нельзя. Каждый
# его метод защищает себя сам — см. routes/auth.py.
app.include_router(auth.router, prefix="/api")

# Всё остальное закрыто одной зависимостью на include_router, а не по
# эндпоинтам: забытая проверка на одном роуте открыла бы доступ ко всем
# финансам, и заметить такое можно слишком поздно.
_protected = [Depends(require_user)]

app.include_router(dashboard.router, prefix="/api", dependencies=_protected)
app.include_router(directories.router, prefix="/api", dependencies=_protected)
app.include_router(accounts.router, prefix="/api", dependencies=_protected)
app.include_router(categories.router, prefix="/api", dependencies=_protected)
app.include_router(currencies.router, prefix="/api", dependencies=_protected)
app.include_router(transactions.router, prefix="/api", dependencies=_protected)
app.include_router(assets.router, prefix="/api", dependencies=_protected)
app.include_router(net_worth.router, prefix="/api", dependencies=_protected)
app.include_router(backup.router, prefix="/api", dependencies=_protected)
app.include_router(reports.router, prefix="/api", dependencies=_protected)
app.include_router(insights.router, prefix="/api", dependencies=_protected)
app.include_router(settings_routes.router, prefix="/api", dependencies=_protected)
app.include_router(settlements.router, prefix="/api", dependencies=_protected)
app.include_router(credits.router, prefix="/api", dependencies=_protected)
app.include_router(plans.router, prefix="/api", dependencies=_protected)
app.include_router(products.router, prefix="/api", dependencies=_protected)
app.include_router(investments.router, prefix="/api", dependencies=_protected)
app.include_router(work_periods.router, prefix="/api", dependencies=_protected)
app.include_router(budgets.router, prefix="/api", dependencies=_protected)
app.include_router(advice.router, prefix="/api", dependencies=_protected)
app.include_router(goals.router, prefix="/api", dependencies=_protected)
app.include_router(recurring.router, prefix="/api", dependencies=_protected)
app.include_router(cash_flow.router, prefix="/api", dependencies=_protected)
app.include_router(tags.router, prefix="/api", dependencies=_protected)
app.include_router(spreadsheet_import.router, prefix="/api", dependencies=_protected)
app.include_router(crypto.router, prefix="/api", dependencies=_protected)


@app.get("/api/health")
async def health() -> dict[str, str]:
    # version rides along so the frontend's Settings page can show which
    # release is actually running without a separate authenticated endpoint —
    # this route is already auth_basic-exempt for Docker's HEALTHCHECK.
    return {"status": "ok", "version": APP_VERSION}

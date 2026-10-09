from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.base import Base
from app import models  # noqa: F401 - register all ORM models for Alembic metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if settings.database_url is None:
    raise RuntimeError(
        "DATABASE_URL is required for Alembic. Configure it in the environment."
    )

config.set_main_option("sqlalchemy_url", settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    migration_url = settings.database_url.replace(
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        1,
    )
    connectable = create_engine(
        migration_url,
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

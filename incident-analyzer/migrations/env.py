import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, engine_from_config, pool

from app.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def migration_url() -> str:
    url = URL.create(
        drivername="mysql+pymysql",
        username=os.environ["INCIDENT_DB_MIGRATION_USERNAME"],
        password=os.environ["INCIDENT_DB_MIGRATION_PASSWORD"],
        host=os.getenv("INCIDENT_DB_HOST", "mysql"),
        port=int(os.getenv("INCIDENT_DB_PORT", "3306")),
        database=os.getenv("INCIDENT_DB_NAME", "membershipflow_incident"),
        query={"charset": "utf8mb4"},
    )
    return url.render_as_string(hide_password=False).replace("%", "%%")


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = migration_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

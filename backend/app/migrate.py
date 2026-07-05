"""数据库迁移辅助。

在应用启动时执行必要的 ALTER TABLE，确保旧数据库兼容新代码。
兼容 SQLite（测试）和 PostgreSQL（生产）。
"""

import logging

from sqlalchemy import text as sa_text

logger = logging.getLogger("nanping.migrate")


MIGRATIONS = [
    # (表名, 列名, 列定义: SQLite 格式, PostgreSQL 格式)
    ("user", "is_admin", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("review", "ai_rated", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
]


async def run_migrations(conn) -> None:
    """检查并执行所有待执行的列迁移。"""
    # 检测数据库类型
    dialect = conn.engine.url.get_backend_name()

    for table, column, def_sqlite, def_pg in MIGRATIONS:
        if dialect == "sqlite":
            result = await conn.execute(sa_text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result.fetchall()]
        else:
            result = await conn.execute(
                sa_text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = :table"
                ),
                {"table": table},
            )
            columns = [row[0] for row in result.fetchall()]

        if column not in columns:
            definition = def_sqlite if dialect == "sqlite" else def_pg
            logger.info("迁移: ALTER TABLE %s ADD COLUMN %s %s", table, column, definition)
            await conn.execute(
                sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            )
        else:
            logger.debug("列 %s.%s 已存在，跳过", table, column)

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

# PG 外键 ON DELETE 约束修复（SQLite 不强制 FK，跳过）
FK_MIGRATIONS = [
    # (表名, 约束名, 重建 SQL)
    ("activity_log", "activity_log_user_id_fkey",
     "ALTER TABLE activity_log ADD CONSTRAINT activity_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES \"user\"(id) ON DELETE SET NULL"),
    ("review", "review_user_id_fkey",
     "ALTER TABLE review ADD CONSTRAINT review_user_id_fkey FOREIGN KEY (user_id) REFERENCES \"user\"(id) ON DELETE SET NULL"),
    ("review", "review_course_id_fkey",
     "ALTER TABLE review ADD CONSTRAINT review_course_id_fkey FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE"),
    ("course_offering", "course_offering_course_id_fkey",
     "ALTER TABLE course_offering ADD CONSTRAINT course_offering_course_id_fkey FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE"),
]


async def run_migrations(conn) -> None:
    """检查并执行所有待执行的迁移。"""
    dialect = conn.engine.url.get_backend_name()

    # ---- 列迁移 ----
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

    # ---- FK 约束迁移（仅 PG） ----
    if dialect != "sqlite":
        for table, constraint_name, rebuild_sql in FK_MIGRATIONS:
            result = await conn.execute(
                sa_text(
                    "SELECT 1 FROM information_schema.table_constraints"
                    " WHERE constraint_name = :name"
                ),
                {"name": constraint_name},
            )
            if result.fetchone():
                logger.info("迁移: 修复 FK 约束 %s", constraint_name)
                await conn.execute(
                    sa_text(f"ALTER TABLE {table} DROP CONSTRAINT {constraint_name}")
                )
                await conn.execute(sa_text(rebuild_sql))
            else:
                logger.debug("FK 约束 %s 不存在，跳过", constraint_name)

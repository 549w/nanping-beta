"""用课程名（+ 教师消歧）匹配导入评价。

适用场景：all_reviews.xlsx 中无课程号（或课程号匹配不上），但有课程名的记录。

匹配逻辑：
  1. 课程名精确匹配 → 唯一 course → 直接导入
  2. 课程名精确匹配 → 多条 course → 教师名子串/包含消歧 → 导入
  3. 均失败 → 跳过，留在 xlsx 中

匹配一条从 xlsx 删一条。统计报告输出到 docs/。

用法：
    cd nanping
    source .venv/bin/activate
    python backend/scripts/import_reviews_by_name.py
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import select

# ---------- 配置 ----------

DB_PATH = "data/nanping.db"
REVIEWS_PATH = Path("data/reviews_normalized/all_reviews.xlsx")
REPORT_PATH = Path("docs/import_by_name_report.md")

# ---------- 独立模型 ----------


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "course"
    id = Column(Integer, primary_key=True)
    code = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    teacher = Column(Text, nullable=False)
    department = Column(Text)
    credits = Column(Float)
    created_at = Column(Text, nullable=False)


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, nullable=False, unique=True)
    password = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)


class Review(Base):
    __tablename__ = "review"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    rating = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    semester = Column(Text, nullable=True)
    is_anonymous = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Integer, nullable=False, default=0)
    source = Column(Text, nullable=False, default="native")
    created_at = Column(Text, nullable=False)


# ---------- 引擎 ----------

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_system_user(session: AsyncSession) -> int:
    result = await session.execute(
        select(User).where(User.email == "system@nanping")
    )
    user = result.scalar_one_or_none()
    if user:
        return user.id
    now = _now()
    sys_user = User(email="system@nanping", password="", created_at=now)
    session.add(sys_user)
    await session.flush()
    return sys_user.id


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def teacher_matches(review_teacher: str, course_teacher: str) -> bool:
    """review_teacher 是否为 course_teacher 中某个教师的子串或反之。"""
    if not review_teacher or not course_teacher:
        return False
    rt = review_teacher.strip()
    ct_names = [t.strip() for t in course_teacher.split(",") if t.strip()]
    for ct in ct_names:
        if rt in ct or ct in rt:
            return True
    return False


async def lookup_by_name(session: AsyncSession, name: str,
                         teacher: str) -> tuple[int | None, str]:
    """课程名精确匹配，唯一命中直接返回，多条用教师消歧。"""
    name = name.strip()
    result = await session.execute(select(Course).where(Course.name == name))
    courses = result.scalars().all()

    if not courses:
        return None, "not_found"

    if len(courses) == 1:
        return courses[0].id, "name_exact"

    # 多条同名 → 教师消歧
    if teacher:
        for c in courses:
            if teacher_matches(teacher.strip(), c.teacher):
                return c.id, "teacher"

    teachers = ", ".join(c.teacher for c in courses[:5])
    return None, f"ambiguous_{len(courses)}"


# ---------- 主流程 ----------

async def main():
    await create_tables()

    async with async_session() as session:
        sys_user_id = await ensure_system_user(session)
        await session.commit()
    print(f"系统用户 ID = {sys_user_id}\n")

    # ---- 读取 all_reviews.xlsx ----
    df = pd.read_excel(REVIEWS_PATH)
    print(f"all_reviews.xlsx: {len(df)} 行")

    # 筛选有课程名的行
    name_mask = (df["course_name"].notna() &
                 (df["course_name"].astype(str).str.strip() != "") &
                 (df["course_name"].astype(str).str.strip() != "nan"))
    total_with_name = name_mask.sum()
    print(f"其中有课程名: {total_with_name} 行\n")

    # 统计
    stats_exact = 0          # 课程名唯一命中
    stats_teacher = 0        # 教师消歧成功
    stats_not_found = 0      # 课程名不在 DB
    stats_ambiguous = 0      # 多条但教师消歧失败
    matched_indices = []
    not_found_names: dict[str, int] = {}
    ambiguous_names: dict[str, int] = {}

    # 按来源/学期统计
    source_stats: dict[str, dict] = {}   # source_file -> {semester -> count}

    now = _now()

    async with async_session() as session:
        for idx in df[name_mask].index:
            row = df.loc[idx]
            name = str(row["course_name"]).strip()
            teacher = str(row["teacher"]).strip() if pd.notna(row["teacher"]) else ""
            semester = str(row["semester"]).strip() if pd.notna(row["semester"]) else ""
            content = str(row["content"]).strip()
            source_file = str(row["source_file"]).strip() if pd.notna(row["source_file"]) else ""

            course_id, match_type = await lookup_by_name(session, name, teacher)

            if course_id is None:
                if match_type == "not_found":
                    stats_not_found += 1
                    not_found_names[name] = not_found_names.get(name, 0) + 1
                else:
                    stats_ambiguous += 1
                    ambiguous_names[name] = ambiguous_names.get(name, 0) + 1
                continue

            # 匹配成功 → 入库
            session.add(Review(
                course_id=course_id,
                user_id=sys_user_id,
                content=content,
                semester=semester if semester else None,
                source=source_file,
                created_at=now,
            ))
            matched_indices.append(idx)

            if match_type == "name_exact":
                stats_exact += 1
            else:
                stats_teacher += 1

            # 来源学期统计
            if source_file not in source_stats:
                source_stats[source_file] = {}
            source_stats[source_file][semester] = \
                source_stats[source_file].get(semester, 0) + 1

        await session.commit()

    matched_count = len(matched_indices)
    print(f"匹配成功: {matched_count} 条")
    print(f"  课程名唯一命中: {stats_exact}")
    print(f"  教师消歧成功:   {stats_teacher}")
    print(f"未匹配: {stats_not_found + stats_ambiguous} 条")
    print(f"  课程名不在 DB:  {stats_not_found}（{len(not_found_names)} 个不同课程名）")
    print(f"  多名但消歧失败: {stats_ambiguous}（{len(ambiguous_names)} 个不同课程名）")

    # 从 xlsx 删除已匹配行
    if matched_indices:
        df = df.drop(matched_indices)
        df.to_excel(REVIEWS_PATH, index=False, engine="openpyxl")
        print(f"\n已从 all_reviews.xlsx 删除 {matched_count} 行，剩余 {len(df)} 行")

    # ---- 生成 Markdown 报告 ----
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# 课程名匹配导入报告\n")
    lines.append(f"**执行时间**：{_now()}\n")
    lines.append(f"**脚本**：`backend/scripts/import_reviews_by_name.py`\n")
    lines.append("---\n")

    lines.append("## 总体统计\n")
    lines.append(f"| 指标 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 导入前 xlsx 总行数 | {len(df) + matched_count} |")
    lines.append(f"| 有课程名的行数 | {total_with_name} |")
    lines.append(f"| 匹配成功导入 | **{matched_count}** |")
    lines.append(f"| 课程名唯一命中 | {stats_exact} |")
    lines.append(f"| 教师消歧成功 | {stats_teacher} |")
    lines.append(f"| 未匹配（留在 xlsx） | {stats_not_found + stats_ambiguous} |")
    lines.append(f"| 导入后 xlsx 剩余 | {len(df)} |")
    lines.append("")

    if source_stats:
        lines.append("## 按来源 / 学期分布\n")
        lines.append("| 来源文件 | 学期 | 导入条数 |")
        lines.append("|----------|------|----------|")
        for src in sorted(source_stats.keys()):
            for sem in sorted(source_stats[src].keys()):
                cnt = source_stats[src][sem]
                lines.append(f"| {src} | {sem or '(空)'} | {cnt} |")
        lines.append("")

    if not_found_names:
        lines.append("## 未匹配：课程名不在 DB 中\n")
        lines.append(f"共 {stats_not_found} 条，涉及 {len(not_found_names)} 个不同课程名。\n")
        lines.append("| 课程名 | 条数 |")
        lines.append("|--------|------|")
        for name, cnt in sorted(not_found_names.items(), key=lambda x: (-x[1], x[0]))[:50]:
            lines.append(f"| {name} | {cnt} |")
        if len(not_found_names) > 50:
            lines.append(f"| ... | （共 {len(not_found_names)} 个，仅列前 50） |")
        lines.append("")

    if ambiguous_names:
        lines.append("## 未匹配：课程名存在但教师消歧失败\n")
        lines.append(f"共 {stats_ambiguous} 条，涉及 {len(ambiguous_names)} 个不同课程名。\n")
        lines.append("| 课程名 | 条数 |")
        lines.append("|--------|------|")
        for name, cnt in sorted(ambiguous_names.items(), key=lambda x: (-x[1], x[0]))[:50]:
            lines.append(f"| {name} | {cnt} |")
        if len(ambiguous_names) > 50:
            lines.append(f"| ... | （共 {len(ambiguous_names)} 个，仅列前 50） |")
        lines.append("")

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

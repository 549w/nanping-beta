"""将原始 Excel 评价数据转换为统一 XLSX 格式。

用法：
    cd nanping
    source .venv/bin/activate
    python backend/scripts/convert_reviews.py

输出：data/reviews_normalized/all_reviews.tsv

列：
    course_code | course_name | teacher | semester | content | extra_tag | source_file | source_row
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data/raw_reviews")
OUTPUT_DIR = Path("data/reviews_normalized")
OUTPUT_DIR.mkdir(exist_ok=True)

ALL_ROWS = []


def add(course_name, teacher, content, semester, source_file, source_row,
        course_code="", extra_tag=""):
    """添加一条标准化记录。"""
    course_name = str(course_name).strip() if pd.notna(course_name) else ""
    teacher = str(teacher).strip() if pd.notna(teacher) else ""
    content = str(content).strip() if pd.notna(content) else ""
    if not course_name or not content:
        return
    ALL_ROWS.append({
        "course_code": course_code,
        "course_name": course_name,
        "teacher": teacher,
        "semester": semester,
        "content": content,
        "extra_tag": str(extra_tag).strip() if pd.notna(extra_tag) else "",
        "source_file": source_file,
        "source_row": source_row,
    })


def looks_like_review(text, teacher_col=False):
    """判断文本是否像一条评论（而非教师名/元数据）。

    教师名特征：短（≤6字符），或逗号分隔的多教师列表。
    评论特征：长句，含标点、换行。
    """
    if pd.isna(text) or not str(text).strip():
        return False
    t = str(text).strip()
    # 元数据行
    if t in ("说明", "表格视图 | 画册视图", "乡土"):
        return False
    if t.startswith("↓") and "区域" in t:
        return False
    # 教师名列：短名或逗号分隔
    if teacher_col:
        if len(t) <= 6:
            return False  # 短名 → 是老师
        if "," in t or "，" in t or "/" in t:
            return False  # 多教师 → 是老师
    return True


# ============================================================
# 红黑榜_2020.xlsx
# ============================================================
def process_2020():
    print("处理 红黑榜_2020.xlsx ...")
    path = DATA_DIR / "红黑榜_2020.xlsx"
    df = pd.read_excel(path, sheet_name="2020", header=None)

    # row 0 = header, row 1+ = data (with category rows)
    course_name = ""
    for i in range(2, len(df)):
        row = df.iloc[i]
        cat = row.iloc[0]
        cn = row.iloc[1]
        teacher = row.iloc[2]

        # 类别行：只有第0列有值 → 跳过（如"思政"）
        if pd.notna(cat) and pd.isna(cn) and pd.isna(teacher):
            continue

        # 向前填充课程名
        if pd.notna(cn) and str(cn).strip():
            course_name = str(cn).strip()

        if pd.isna(teacher) or not str(teacher).strip():
            continue
        if not course_name:
            continue

        teacher_str = str(teacher).strip()
        for col in range(3, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                add(course_name, teacher_str, content, "2020",
                    "红黑榜_2020.xlsx", i + 1)


# ============================================================
# 红黑榜_2020.xlsx —— 后半部分（148行起，格式不同）
# ============================================================
PART2_ROWS = []


def add_part2(course_name, teacher, content, source_row, course_code="",
              extra_tag="", schedule=""):
    """添加一条 2020-part2 记录。"""
    course_name = str(course_name).strip() if pd.notna(course_name) else ""
    teacher = str(teacher).strip() if pd.notna(teacher) else ""
    content = str(content).strip() if pd.notna(content) else ""
    if not course_name or not content:
        return
    PART2_ROWS.append({
        "course_code": course_code,
        "course_name": course_name,
        "teacher": teacher,
        "content": content,
        "extra_tag": extra_tag,
        "schedule": schedule,
        "source_row": source_row + 1,   # 1-indexed
    })


def process_2020_part2():
    """处理 2020 文件 148 行之后的两段特殊格式。

    148-346 行：课程目录格式
        col 0 = 课程号, col 2 = 课程名, col 5 = 教师,
        col 4 = 上课时间, col 7 = 容量, col 8+ = 评价

    347-404 行：悦读评价格式
        col 0 = 子类别（前向填充）, col 1 = 课程名（前向填充）,
        col 2 = 教师, col 3+ = 评价
    """
    print("处理 红黑榜_2020.xlsx 后半部分（148行起）...")
    path = DATA_DIR / "红黑榜_2020.xlsx"
    df = pd.read_excel(path, sheet_name="2020", header=None)

    # ---------- 子段 A：课程目录（148-346）----------
    for i in range(148, 347):
        row = df.iloc[i]
        code = row.iloc[0]
        name = row.iloc[2]
        schedule = row.iloc[4]
        teacher = row.iloc[5]

        if pd.isna(name) or not str(name).strip():
            continue
        if pd.isna(teacher) or not str(teacher).strip():
            continue

        code_str = str(int(code)).strip() if pd.notna(code) and str(code).strip().isdigit() else str(code).strip() if pd.notna(code) else ""
        name_str = str(name).strip()
        teacher_str = str(teacher).strip()
        schedule_str = str(schedule).strip() if pd.notna(schedule) else ""

        for col in range(8, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                add_part2(name_str, teacher_str, content, i,
                          course_code=code_str, schedule=schedule_str)

    # ---------- 子段 B：悦读评价（347-404）----------
    # row 347 = "悦读" 标题行，跳过
    sub_cat = ""
    course_name = ""

    for i in range(348, len(df)):
        row = df.iloc[i]
        sc = row.iloc[0]
        cn = row.iloc[1]
        teacher = row.iloc[2]

        # 纯类别行
        if pd.notna(sc) and pd.isna(cn) and pd.isna(teacher):
            continue

        if pd.notna(sc) and str(sc).strip():
            sub_cat = str(sc).strip()
        if pd.notna(cn) and str(cn).strip():
            course_name = str(cn).strip()

        if pd.isna(teacher) or not str(teacher).strip():
            continue
        if not course_name:
            continue

        teacher_str = str(teacher).strip()
        for col in range(3, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                add_part2(course_name, teacher_str, content, i,
                          extra_tag=sub_cat)

    # 输出
    out_path = OUTPUT_DIR / "2020_part2_reviews.xlsx"
    out_df = pd.DataFrame(PART2_ROWS)
    out_df.to_excel(out_path, index=False, engine="openpyxl")

    print(f"  课程目录段（148-346）评价：{len([r for r in PART2_ROWS if r['course_code']])} 条（含课程号）")
    print(f"  悦读段（347-404）评价：{len([r for r in PART2_ROWS if not r['course_code']])} 条")
    print(f"  输出：{out_path}")


# ============================================================
# 红黑榜_2021.xlsx
# ============================================================
def process_2021():
    print("处理 红黑榜_2021.xlsx ...")
    path = DATA_DIR / "红黑榜_2021.xlsx"
    df = pd.read_excel(path, sheet_name="2021", header=None)

    # row 0 = header, row 1 = notice (skip), row 2+ = data
    for i in range(2, len(df)):
        row = df.iloc[i]
        course_name = row.iloc[0]
        teacher = row.iloc[1]

        # 跳过空行或公告行
        if pd.isna(course_name) or str(course_name).strip().startswith("说明"):
            continue

        course_str = str(course_name).strip()
        teacher_str = str(teacher).strip() if pd.notna(teacher) else ""

        for col in range(2, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                # 列2是评价2, 列3是评价1, 都正常当评价取
                add(course_str, teacher_str, content, "2021",
                    "红黑榜_2021.xlsx", i + 1)


# ============================================================
# 红黑榜_2022.xlsx
# ============================================================
def process_2022():
    print("处理 红黑榜_2022.xlsx ...")
    path = DATA_DIR / "红黑榜_2022.xlsx"
    df = pd.read_excel(path, sheet_name="2022", header=None)

    sub_cat = ""
    course_name = ""

    for i in range(2, len(df)):
        row = df.iloc[i]
        sc = row.iloc[0]
        cn = row.iloc[1]
        teacher = row.iloc[2]

        # 纯类别行：第0列有值但第1-2列为空 → 顶层分类，跳过
        if pd.notna(sc) and pd.isna(cn) and pd.isna(teacher):
            continue

        if pd.notna(sc) and str(sc).strip():
            sub_cat = str(sc).strip()
        if pd.notna(cn) and str(cn).strip():
            course_name = str(cn).strip()

        if pd.isna(teacher) or not str(teacher).strip():
            continue
        if not course_name:
            continue

        teacher_str = str(teacher).strip()
        for col in range(3, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                add(course_name, teacher_str, content, "2022",
                    "红黑榜_2022.xlsx", i + 1, extra_tag=sub_cat)


# ============================================================
# 2023级红黑榜.xlsx (最大 sheet: 智能表3)
# ============================================================
def process_2023():
    print("处理 2023级红黑榜.xlsx (智能表3) ...")
    path = DATA_DIR / "2023级红黑榜.xlsx"
    df = pd.read_excel(path, sheet_name="智能表3", header=None)

    # row 0: 表格视图 | 画册视图 (skip)
    # row 1: header (skip)
    # row 2-4: 说明/元数据 (skip)
    # row 5+: data
    for i in range(5, len(df)):
        row = df.iloc[i]
        code = row.iloc[0]
        name = row.iloc[1]
        teacher = row.iloc[2]

        # 跳过区域分隔行和全空行
        if pd.isna(name) or str(name).strip().startswith("↓"):
            continue

        code_str = str(code).strip() if pd.notna(code) else ""
        name_str = str(name).strip()

        # 教师列：判断是否为真教师名
        teacher_str = ""
        if pd.notna(teacher):
            t = str(teacher).strip()
            if t and t != " ":
                # 过滤明显是评论的教师列值（过长且不含逗号/斜杠）
                if len(t) <= 6 or "," in t or "，" in t or "/" in t:
                    teacher_str = t
                # else: 太长的无逗号文本 → 可能是评论，忽略

        for col in range(3, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip() and str(content).strip() != " ":
                add(name_str, teacher_str, content, "2023",
                    "2023级红黑榜.xlsx", i + 1, course_code=code_str)


# ============================================================
# 红黑榜_2024春 / 2024冬 / 2025春 (相同格式)
# ============================================================
def process_2024_2025(filename, sheet, semester):
    print(f"处理 {filename} ...")
    path = DATA_DIR / filename
    df = pd.read_excel(path, sheet_name=sheet, header=None)

    for i in range(1, len(df)):
        row = df.iloc[i]
        extra_tag = row.iloc[0]
        course_name = row.iloc[1]
        teacher = row.iloc[2]

        if pd.isna(course_name) or not str(course_name).strip():
            continue
        if pd.isna(teacher) or not str(teacher).strip():
            continue

        tag_str = str(extra_tag).strip() if pd.notna(extra_tag) else ""
        name_str = str(course_name).strip()
        teacher_str = str(teacher).strip()

        for col in range(3, df.shape[1]):
            content = row.iloc[col]
            if pd.notna(content) and str(content).strip():
                add(name_str, teacher_str, content, semester,
                    filename, i + 1, extra_tag=tag_str)


# ============================================================
# 红黑榜-fork25_2025秋 / 2026春 (简单三列格式)
# ============================================================
def process_fork(filename, sheet, semester):
    print(f"处理 {filename} ...")
    path = DATA_DIR / filename
    df = pd.read_excel(path, sheet_name=sheet, header=None)

    for i in range(1, len(df)):
        row = df.iloc[i]
        course_name = row.iloc[0]
        teacher = row.iloc[1]
        content = row.iloc[2]

        if pd.isna(course_name) or pd.isna(content):
            continue

        teacher_str = str(teacher).strip() if pd.notna(teacher) else ""
        add(str(course_name).strip(), teacher_str, content, semester,
            filename, i + 1)


# ============================================================
# 主流程
# ============================================================
def main():
    process_2020()
    process_2020_part2()
    process_2021()
    process_2022()
    process_2023()
    process_2024_2025("红黑榜_2024春.xlsx", "2024春", "2024春")
    process_2024_2025("红黑榜_2024冬.xlsx", "2024冬", "2024冬")
    process_2024_2025("红黑榜_2025春.xlsx", "2025春", "2025春")
    process_fork("红黑榜-fork25_2025秋.xlsx", "2025秋", "2025秋")
    process_fork("红黑榜-fork25_2026春.xlsx", "2026春", "2026春")

    # 输出
    out_path = OUTPUT_DIR / "all_reviews.xlsx"
    out_df = pd.DataFrame(ALL_ROWS)
    out_df.to_excel(out_path, index=False, engine="openpyxl")

    print(f"\n===== 完成 =====")
    print(f"输出：{out_path}")
    print(f"总计：{len(ALL_ROWS)} 条评价")
    print(f"\n各来源统计：")
    for src, cnt in out_df["source_file"].value_counts().items():
        print(f"  {src}: {cnt} 条")
    print(f"\n学期分布：")
    for sem, cnt in out_df["semester"].value_counts().items():
        print(f"  {sem}: {cnt} 条")
    print(f"\n有课程号的记录：{(out_df['course_code'] != '').sum()} 条")
    print(f"有教师名的记录：{(out_df['teacher'] != '').sum()} 条")


if __name__ == "__main__":
    main()

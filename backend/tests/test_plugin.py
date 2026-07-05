"""插件统一接口 v2 测试。

覆盖 POST /plugin 的响应结构：badge_html、panel_html、news_html、widgets。
"""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models import ActivityLog, News


@pytest_asyncio.fixture
async def test_news(db_session):
    """创建一条测试公告。"""
    news = News(
        title="测试公告",
        content="这是一条测试公告内容",
        is_active=1,
        created_at="2025-06-01T00:00:00",
    )
    db_session.add(news)
    await db_session.commit()
    await db_session.refresh(news)
    return news


class TestPluginV2:
    """POST /plugin v2 测试。"""

    @pytest.mark.asyncio
    async def test_badge_html_has_match(self, client: AsyncClient, test_course, test_review):
        """匹配成功时 badge_html 应包含评分、标签、按钮。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [
                    {
                        "code": "00010", "name": "测试课程", "teacher": "张三",
                        "credits": "3", "schedule": "周一 1-2节", "campus": "仙林",
                        "grade": "2024", "department": "计算机系",
                    }
                ],
                "username": "testuser",
                "gender": "men.png",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # v2 顶层结构
        assert "toast" in data
        assert "news_html" in data
        assert "courses" in data
        assert "widgets" in data

        # courses 按 query_index 排列
        assert len(data["courses"]) == 1
        course = data["courses"][0]

        # badge_html 应有评分
        badge = course["badge_html"]
        assert "np-badge-row" not in badge  # 外层由插件包裹
        assert "np-badge-rating" in badge or "np-star" in badge
        assert "np-badge-btn" in badge
        assert "查看评价" in badge

        # panel_html 应有课程信息
        panel = course["panel_html"]
        assert "np-course-card" in panel
        assert "测试课程" in panel
        assert "张三" in panel

        # exact_course_id
        assert course["exact_course_id"] == test_course.id

    @pytest.mark.asyncio
    async def test_badge_html_no_match(self, client: AsyncClient):
        """无匹配时 badge_html 应显示暂无评价。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [
                    {"code": "99999", "name": "不存在", "teacher": "nobody"}
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()

        badge = data["courses"][0]["badge_html"]
        assert "暂无评价" in badge
        assert data["courses"][0]["panel_html"] == ""
        assert data["courses"][0]["exact_course_id"] is None

    @pytest.mark.asyncio
    async def test_news_html(self, client: AsyncClient, test_news):
        """news_html 应包含公告信息。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [{"code": "99999", "name": "x", "teacher": "x"}],
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "np-news-card" in data["news_html"]
        assert "测试公告" in data["news_html"]
        assert "测试公告内容" in data["news_html"]

    @pytest.mark.asyncio
    async def test_news_html_empty(self, client: AsyncClient):
        """无公告时 news_html 应为空字符串。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [{"code": "99999", "name": "x", "teacher": "x"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["news_html"] == ""

    @pytest.mark.asyncio
    async def test_optional_fields_accepted(self, client: AsyncClient):
        """PluginQuery 所有字段均可选。"""
        response = await client.post(
            "/plugin",
            json={"queries": [{"code": "00010"}]},
        )
        assert response.status_code == 200
        assert len(response.json()["courses"]) == 1

    @pytest.mark.asyncio
    async def test_full_fields_sent(self, client: AsyncClient, test_course, test_review):
        """全量字段请求应正常返回。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [
                    {
                        "code": "00010",
                        "name": "测试课程",
                        "teacher": "张三",
                        "credits": "3.0",
                        "schedule": "周一 1-2节 1-18周 仙Ⅰ-101",
                        "campus": "仙林校区",
                        "grade": "2024",
                        "department": "计算机系",
                    }
                ],
                "username": "fulluser",
                "gender": "women.png",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["toast"]["success"] != ""
        assert len(data["courses"]) == 1

    @pytest.mark.asyncio
    async def test_toast_content(self, client: AsyncClient, test_course, test_review):
        """toast.success 应反映匹配数量。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [
                    {"code": "00010", "name": "测试课程", "teacher": "张三"},
                    {"code": "99999", "name": "无", "teacher": "x"},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "匹配到 1 条评价" in data["toast"]["success"]
        assert data["toast"]["loading"] == "「南评」正在加载评论..."
        assert data["toast"]["error"] == "加载失败，请检查网络连接"

    @pytest.mark.asyncio
    async def test_activity_logged(
        self, client: AsyncClient, db_session, test_course, test_review
    ):
        """POST /plugin 应写入活动日志。"""
        response = await client.post(
            "/plugin",
            json={
                "queries": [
                    {"code": "00010", "name": "测试课程", "teacher": "张三"}
                ],
                "username": "loguser",
                "gender": "women.png",
            },
        )
        assert response.status_code == 200
        await db_session.commit()

        result = await db_session.execute(
            select(ActivityLog)
            .where(ActivityLog.action == "plugin_query")
            .order_by(ActivityLog.created_at.desc())
            .limit(1)
        )
        log = result.scalar_one_or_none()
        assert log is not None
        detail = json.loads(log.details)
        assert detail["query_count"] == 1
        assert detail["matched_count"] == 1
        assert detail["username"] == "loguser"
        assert detail["gender"] == "women.png"


class TestExistingEndpointsUnaffected:
    """确保旧端点不受影响。"""

    @pytest.mark.asyncio
    async def test_courses_match_still_works(
        self, client: AsyncClient, test_course, test_review
    ):
        """POST /courses/match 应如常工作。"""
        response = await client.post(
            "/courses/match",
            json={
                "queries": [
                    {"code": "00010", "teacher": "张三", "name": "测试课程"}
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_news_still_works(self, client: AsyncClient, test_news):
        """GET /news 应如常工作。"""
        response = await client.get("/news", params={"limit": 2})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["title"] == "测试公告"

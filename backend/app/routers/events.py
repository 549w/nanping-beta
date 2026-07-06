"""事件上报路由。

POST /events/download — 记录插件下载事件。
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import log_activity
from ..database import get_db

logger = logging.getLogger("nanping.events")
router = APIRouter(prefix="/events", tags=["事件"])


@router.post("/download")
async def record_download(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """记录插件下载事件。

    无需登录，前端下载按钮点击时调用。
    记录 IP、User-Agent、时间戳到 activity_log 表。
    """
    await log_activity(
        db,
        request,
        action="download_extension",
        details={"page": str(request.url)},
    )
    logger.info("插件下载事件已记录")
    return {"ok": True}
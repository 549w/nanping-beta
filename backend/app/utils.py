"""通用工具函数。"""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP。

    优先从反向代理转发的 X-Forwarded-For / X-Real-IP 头中获取，
    回退到 request.client.host（直接连接场景）。

    在 Docker 部署中，nginx 通过端口映射转发流量到容器，
    request.client.host 会是 Docker 网桥网关 IP（如 172.20.0.1），
    因此必须信任代理头才能拿到真实客户端 IP。

    Args:
        request: FastAPI Request 对象。

    Returns:
        客户端真实 IP 字符串，无法获取时返回 "unknown"。
    """
    # X-Forwarded-For 格式: "client, proxy1, proxy2"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # 取第一个 IP，即原始客户端 IP
        return forwarded.split(",")[0].strip()

    # X-Real-IP 通常只包含客户端 IP（nginx 设置）
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 回退到直接连接 IP（本地开发或无代理场景）
    if request.client and request.client.host:
        return request.client.host

    return "unknown"
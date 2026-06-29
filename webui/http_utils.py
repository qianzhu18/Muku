"""HTTP 请求共享配置：代理、SSL 校验、超时。

让 OpenRouter / OpenAI 兼容服务的外呼能够通过环境变量显式配置代理，
避免依赖系统级 HTTP_PROXY/HTTPS_PROXY 透传导致的 SSL 错乱。
"""

import os

try:
    from .env_config import load_env_file
except ImportError:
    from env_config import load_env_file

load_env_file()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_proxies() -> dict[str, str] | None:
    """返回 requests 可用的 proxies 字典；未配置则返回 None。

    优先级：OPENROUTER_PROXY > HTTPS_PROXY/HTTP_PROXY。
    """
    explicit = os.environ.get("OPENROUTER_PROXY", "").strip()
    if explicit:
        return {"http": explicit, "https": explicit}

    https_proxy = os.environ.get("HTTPS_PROXY", "").strip() or os.environ.get("https_proxy", "").strip()
    http_proxy = os.environ.get("HTTP_PROXY", "").strip() or os.environ.get("http_proxy", "").strip()
    if https_proxy or http_proxy:
        return {
            "http": http_proxy or https_proxy,
            "https": https_proxy or http_proxy,
        }
    return None


def get_ssl_verify() -> bool:
    """是否启用 SSL 证书校验。默认启用；代理证书问题时可显式关闭。"""
    insecure = _env_bool("OPENROUTER_INSECURE_SKIP_VERIFY", False)
    return not insecure


def request_kwargs() -> dict:
    """组装 requests.post/get 的公共 kwargs（proxies / verify）。

    未配置代理且启用 SSL 校验时返回空 dict，行为与原生 requests 一致。
    """
    kwargs: dict = {}
    proxies = get_proxies()
    if proxies:
        kwargs["proxies"] = proxies
    verify = get_ssl_verify()
    if not verify:
        kwargs["verify"] = False
    return kwargs

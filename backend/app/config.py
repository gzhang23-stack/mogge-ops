from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


class Settings(BaseSettings):
    app_name: str = "募格双公众号 AI 内容运营系统"
    database_url: str = "sqlite:///./mogge_ops.db"
    frontend_origin: str = "http://localhost:3000"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    wechat_academic_app_id: str | None = None
    wechat_academic_app_secret: str | None = None
    wechat_recruit_app_id: str | None = None
    wechat_recruit_app_secret: str | None = None
    dingtalk_webhook: str | None = None
    dingtalk_secret: str | None = None
    monitor_auto_run_enabled: bool = False
    monitor_auto_run_interval_minutes: int = 60
    monitor_push_topic_limit: int = 8
    monitor_push_score_threshold: float = 0.68
    rsshub_base_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def wechat_credentials(self, account_name: str) -> dict[str, str | bool]:
        if account_name == "募格科聘":
            appid = self.wechat_recruit_app_id
            appsecret = self.wechat_recruit_app_secret
        else:
            appid = self.wechat_academic_app_id
            appsecret = self.wechat_academic_app_secret
        return {
            "account_name": account_name,
            "appid": appid or "",
            "appsecret": appsecret or "",
            "appid_masked": _mask_secret(appid),
            "appsecret_masked": _mask_secret(appsecret),
            "configured": bool(appid and appsecret),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()

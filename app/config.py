"""Application configuration — everything from environment, nothing hardcoded."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Blizzard
    blizzard_client_id: str = ""
    blizzard_client_secret: str = ""
    blizzard_region: str = "eu"
    blizzard_locale: str = "en_GB"

    # App
    secret_key: str  # Fernet key for token encryption + session signing
    base_url: str = "http://localhost:8000"
    database_url: str = "postgresql+asyncpg://wow:wow@postgres:5432/wow"

    # SimulationCraft
    simc_image_tag: str = "1201-2026-04-09-7a583f3"
    simc_path: str = "/usr/local/bin/simc"
    report_path: str = "/data/reports"

    # Simulation defaults
    raid_sim_iterations: int = 10000
    mplus_sim_iterations: int = 10000
    raid_target_error: float = 0.002
    mplus_target_error: float = 0.002
    raid_fight_style: str = "Patchwerk"
    raid_duration: int = 300
    mplus_fight_style: str = "DungeonSlice"
    mplus_duration: int = 300
    max_candidates_per_slot: int = 3
    sim_timeout_seconds: int = 3600

    # Scheduler
    cron_tz: str = "Europe/Warsaw"
    cron_report: str = "0 12 * * *"

    # Cache TTLs (seconds)
    cache_ttl_realm: int = 7 * 86400
    cache_ttl_content: int = 86400
    cache_ttl_journal: int = 86400
    cache_ttl_item: int = 7 * 86400

    @property
    def api_host(self) -> str:
        return f"{self.blizzard_region}.api.blizzard.com"

    @property
    def oauth_host(self) -> str:
        return "oauth.battle.net"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    ldap_host: str = '172.20.10.10'
    ldap_port: int = 389
    ldap_domain: str = 'htg.local'
    ldap_bind_user: str = 'CN=temp-next-ldap,OU=Service Accounts,OU=HTG,DC=HTG,DC=local'
    ldap_bind_password: SecretStr
    ldap_search_base: str = 'OU=Enabled Users,OU=User Accounts,OU=HTG,DC=HTG,DC=local'
    ldap_start_tls: bool = False
    ldap_ca_file: str | None = None
    database_url: str = 'sqlite:///' + (ROOT / 'ldap_users.db').as_posix()
    api_key: SecretStr

    @field_validator('ldap_bind_password', 'api_key')
    @classmethod
    def require_secret(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError('A non-empty secret is required')
        return value


@lru_cache
def get_settings():
    return Settings()

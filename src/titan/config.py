from __future__ import annotations

from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITAN_", env_file=".env", extra="ignore")

    app_name: str = "titan-aas"
    env: str = "dev"
    host: str = "0.0.0.0"  # nosec B104 - intentional for container deployments
    port: int = 8080

    # Instance ID for distributed deployments
    instance_id: str = Field(default_factory=lambda: str(uuid4())[:8])

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://titan:titan@localhost:5432/titan",
        validation_alias="DATABASE_URL",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # MQTT
    mqtt_broker: str | None = Field(default=None, validation_alias="MQTT_BROKER")
    mqtt_port: int = Field(default=1883, validation_alias="MQTT_PORT")

    # Event Bus
    event_bus_backend: str = Field(default="redis", validation_alias="EVENT_BUS_BACKEND")
    event_bus_stream_name: str = Field(default="titan:events", validation_alias="EVENT_BUS_STREAM")
    event_bus_consumer_group: str = Field(
        default="titan-workers", validation_alias="EVENT_BUS_GROUP"
    )
    event_bus_consumer_id: str | None = Field(
        default=None, validation_alias="EVENT_BUS_CONSUMER_ID"
    )

    # OIDC Authentication (optional)
    oidc_issuer: str | None = Field(default=None, validation_alias="OIDC_ISSUER")
    oidc_audience: str | None = Field(default=None, validation_alias="OIDC_AUDIENCE")
    oidc_client_id: str | None = Field(default=None, validation_alias="OIDC_CLIENT_ID")
    oidc_roles_claim: str | None = Field(default="roles", validation_alias="OIDC_ROLES_CLAIM")
    oidc_jwks_cache_seconds: int = Field(default=3600, validation_alias="OIDC_JWKS_CACHE_SECONDS")

    # Observability
    enable_tracing: bool = Field(default=True, validation_alias="ENABLE_TRACING")
    otlp_endpoint: str | None = Field(default=None, validation_alias="OTLP_ENDPOINT")
    enable_metrics: bool = Field(default=True, validation_alias="ENABLE_METRICS")
    log_level: str = "INFO"

    # Blob Storage
    blob_storage_type: str = Field(default="local", validation_alias="BLOB_STORAGE_TYPE")
    blob_storage_path: str = Field(
        default="/var/lib/titan/blobs", validation_alias="BLOB_STORAGE_PATH"
    )
    blob_inline_threshold: int = Field(
        default=65536, validation_alias="BLOB_INLINE_THRESHOLD"
    )  # 64KB

    # S3 Blob Storage (when blob_storage_type="s3")
    s3_bucket: str | None = Field(default=None, validation_alias="S3_BUCKET")
    s3_prefix: str = Field(default="", validation_alias="S3_PREFIX")
    s3_endpoint_url: str | None = Field(default=None, validation_alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    s3_access_key_id: str | None = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(default=None, validation_alias="AWS_SECRET_ACCESS_KEY")

    # GCS Blob Storage (when blob_storage_type="gcs")
    gcs_bucket: str | None = Field(default=None, validation_alias="GCS_BUCKET")
    gcs_prefix: str = Field(default="", validation_alias="GCS_PREFIX")
    gcs_project: str | None = Field(default=None, validation_alias="GCS_PROJECT")
    gcs_credentials_path: str | None = Field(
        default=None, validation_alias="GCS_CREDENTIALS_PATH"
    )

    # Azure Blob Storage (when blob_storage_type="azure")
    azure_container: str | None = Field(default=None, validation_alias="AZURE_CONTAINER")
    azure_prefix: str = Field(default="", validation_alias="AZURE_PREFIX")
    azure_connection_string: str | None = Field(
        default=None, validation_alias="AZURE_STORAGE_CONNECTION_STRING"
    )
    azure_account_url: str | None = Field(default=None, validation_alias="AZURE_ACCOUNT_URL")
    azure_account_key: str | None = Field(default=None, validation_alias="AZURE_ACCOUNT_KEY")
    azure_sas_token: str | None = Field(default=None, validation_alias="AZURE_SAS_TOKEN")

    # HTTP Caching
    enable_http_caching: bool = Field(default=True, validation_alias="ENABLE_HTTP_CACHING")
    cache_max_age: int = Field(default=60, validation_alias="CACHE_MAX_AGE")
    cache_stale_while_revalidate: int = Field(
        default=30, validation_alias="CACHE_STALE_WHILE_REVALIDATE"
    )

    # Compression
    enable_compression: bool = Field(default=True, validation_alias="ENABLE_COMPRESSION")
    compression_min_size: int = Field(default=500, validation_alias="COMPRESSION_MIN_SIZE")
    compression_level: int = Field(default=6, validation_alias="COMPRESSION_LEVEL")

    # Rate Limiting
    enable_rate_limiting: bool = Field(default=True, validation_alias="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(default=100, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=60, validation_alias="RATE_LIMIT_WINDOW")


settings = Settings()

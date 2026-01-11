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

    # Database connection pool (tuned for 15K+ RPS)
    db_pool_size: int = Field(default=40, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, validation_alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, validation_alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, validation_alias="DB_POOL_RECYCLE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # MQTT Connection
    mqtt_broker: str | None = Field(default=None, validation_alias="MQTT_BROKER")
    mqtt_port: int = Field(default=1883, validation_alias="MQTT_PORT")
    mqtt_username: str | None = Field(default=None, validation_alias="MQTT_USERNAME")
    mqtt_password: str | None = Field(default=None, validation_alias="MQTT_PASSWORD")
    mqtt_use_tls: bool = Field(default=False, validation_alias="MQTT_TLS")
    mqtt_client_id_prefix: str = Field(
        default="titan-aas", validation_alias="MQTT_CLIENT_ID_PREFIX"
    )

    # MQTT Reconnection
    mqtt_reconnect_delay_initial: float = Field(
        default=1.0, validation_alias="MQTT_RECONNECT_DELAY_INITIAL"
    )
    mqtt_reconnect_delay_max: float = Field(
        default=60.0, validation_alias="MQTT_RECONNECT_DELAY_MAX"
    )
    mqtt_reconnect_delay_multiplier: float = Field(
        default=2.0, validation_alias="MQTT_RECONNECT_MULTIPLIER"
    )
    mqtt_max_reconnect_attempts: int = Field(
        default=10, validation_alias="MQTT_MAX_RECONNECT_ATTEMPTS"
    )

    # MQTT Publishing
    mqtt_default_qos: int = Field(default=1, validation_alias="MQTT_DEFAULT_QOS")
    mqtt_retain_events: bool = Field(default=False, validation_alias="MQTT_RETAIN_EVENTS")

    # MQTT Subscriber
    mqtt_subscribe_enabled: bool = Field(default=True, validation_alias="MQTT_SUBSCRIBE_ENABLED")
    mqtt_subscribe_topics: str = Field(
        default="titan/+/+/command/#,titan/element/+/+/value",
        validation_alias="MQTT_SUBSCRIBE_TOPICS",
    )

    # OPC-UA Configuration
    opcua_enabled: bool = Field(default=False, validation_alias="OPCUA_ENABLED")
    opcua_endpoint: str | None = Field(default=None, validation_alias="OPCUA_ENDPOINT")
    opcua_security_mode: str = Field(default="None", validation_alias="OPCUA_SECURITY_MODE")
    opcua_username: str | None = Field(default=None, validation_alias="OPCUA_USERNAME")
    opcua_password: str | None = Field(default=None, validation_alias="OPCUA_PASSWORD")
    opcua_timeout: int = Field(default=5, validation_alias="OPCUA_TIMEOUT")
    opcua_reconnect_delay_initial: float = Field(
        default=1.0, validation_alias="OPCUA_RECONNECT_DELAY_INITIAL"
    )
    opcua_reconnect_delay_max: float = Field(
        default=60.0, validation_alias="OPCUA_RECONNECT_DELAY_MAX"
    )
    opcua_reconnect_delay_multiplier: float = Field(
        default=2.0, validation_alias="OPCUA_RECONNECT_MULTIPLIER"
    )
    opcua_max_reconnect_attempts: int = Field(
        default=10, validation_alias="OPCUA_MAX_RECONNECT_ATTEMPTS"
    )

    # Modbus Configuration
    modbus_enabled: bool = Field(default=False, validation_alias="MODBUS_ENABLED")
    modbus_host: str | None = Field(default=None, validation_alias="MODBUS_HOST")
    modbus_port: int = Field(default=502, validation_alias="MODBUS_PORT")
    modbus_mode: str = Field(default="tcp", validation_alias="MODBUS_MODE")  # tcp or rtu
    modbus_unit_id: int = Field(default=1, validation_alias="MODBUS_UNIT_ID")
    modbus_timeout: float = Field(default=3.0, validation_alias="MODBUS_TIMEOUT")
    modbus_reconnect_interval: float = Field(
        default=5.0, validation_alias="MODBUS_RECONNECT_INTERVAL"
    )
    modbus_mapping_config: str | None = Field(
        default=None, validation_alias="MODBUS_MAPPING_CONFIG"
    )
    # RTU-specific
    modbus_serial_port: str | None = Field(default=None, validation_alias="MODBUS_SERIAL_PORT")
    modbus_baudrate: int = Field(default=9600, validation_alias="MODBUS_BAUDRATE")

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
    gcs_credentials_path: str | None = Field(default=None, validation_alias="GCS_CREDENTIALS_PATH")

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

    # Security Headers
    enable_security_headers: bool = Field(default=True, validation_alias="ENABLE_SECURITY_HEADERS")
    # HSTS enabled by default for production security
    enable_hsts: bool = Field(default=True, validation_alias="ENABLE_HSTS")
    hsts_max_age: int = Field(default=31536000, validation_alias="HSTS_MAX_AGE")  # 1 year
    hsts_include_subdomains: bool = Field(default=True, validation_alias="HSTS_INCLUDE_SUBDOMAINS")
    hsts_preload: bool = Field(default=False, validation_alias="HSTS_PRELOAD")
    csp_policy: str | None = Field(default=None, validation_alias="CSP_POLICY")
    permissions_policy: str | None = Field(default=None, validation_alias="PERMISSIONS_POLICY")

    # ABAC (Attribute-Based Access Control)
    enable_abac: bool = Field(default=False, validation_alias="ENABLE_ABAC")
    abac_default_deny: bool = Field(default=True, validation_alias="ABAC_DEFAULT_DENY")


settings = Settings()

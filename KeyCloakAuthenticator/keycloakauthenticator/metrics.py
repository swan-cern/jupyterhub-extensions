from prometheus_client import Histogram

# Customize default buckets to include more buckets between 10s-infinity
_buckets = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    30.0,
    float("inf"),
)


_DURATION_SECONDS = Histogram(
    "keycloak_authenticator_duration_seconds",
    "Histogram of KeyCloakAuthenticator durations",
    labelnames=["method"],
    buckets=_buckets,
)

metric_refresh_user = _DURATION_SECONDS.labels("refresh_user")
metric_exchange_token = _DURATION_SECONDS.labels("exchange_token")
metric_refresh_token = _DURATION_SECONDS.labels("refresh_token")
metric_authenticate = _DURATION_SECONDS.labels("authenticate")
metric_pre_spawn_start = _DURATION_SECONDS.labels("pre_spawn_start")

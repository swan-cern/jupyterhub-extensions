"""
Defines custom prometheus metrics recording durations of actions in the KeyCloakAuthenticator

These metrics are scraped by prometheus from the /hub/metrics endpoint
"""

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


_METHOD_DURATION_SECONDS = Histogram(
    "keycloak_authenticator_method_duration_seconds",
    "Histogram of durations of methods in the KeyCloakAuthenticator",
    labelnames=["method"],
    buckets=_buckets,
)

_REQUEST_DURATION_SECONDS = Histogram(
    "keycloak_authenticator_request_duration_seconds",
    "Histogram of durations of outgoing requests made by the KeyCloakAuthenticator",
    labelnames=["request"],
    buckets=_buckets,
)

metric_refresh_user = _METHOD_DURATION_SECONDS.labels("refresh_user")
metric_authenticate = _METHOD_DURATION_SECONDS.labels("authenticate")
metric_pre_spawn_start = _METHOD_DURATION_SECONDS.labels("pre_spawn_start")

metric_exchange_token  = _REQUEST_DURATION_SECONDS # Label 'request' set dynamically
metric_refresh_token = _REQUEST_DURATION_SECONDS.labels("refresh_token")
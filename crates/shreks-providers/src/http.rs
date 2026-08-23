//! Shared HTTP failure classification for provider adapters.

use shreks_core::ProviderId;

use crate::{ProviderError, ProviderErrorKind};

/// Convert an HTTP failure into Shreks' stable provider error vocabulary.
pub fn classify_http_failure(
    provider: ProviderId,
    status: u16,
    retry_after: Option<&str>,
    body: &str,
) -> ProviderError {
    let kind = match status {
        401 | 403 => ProviderErrorKind::Unauthorized,
        404 => ProviderErrorKind::NotFound,
        429 => ProviderErrorKind::RateLimited,
        500..=599 => ProviderErrorKind::Unavailable,
        _ => ProviderErrorKind::InvalidRequest,
    };

    let message = if body.trim().is_empty() {
        format!("HTTP {status}")
    } else {
        format!("HTTP {status}: {}", body.trim())
    };

    let error = ProviderError::new(provider, kind, message);

    if status == 429 {
        if let Some(milliseconds) = retry_after
            .and_then(|value| value.trim().parse::<u64>().ok())
            .and_then(|seconds| seconds.checked_mul(1_000))
        {
            return error.with_retry_after_ms(milliseconds);
        }
    }

    error
}

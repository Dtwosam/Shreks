use std::{error::Error, time::Duration};

use shreks_observer::ObserverError;
use tokio::task::JoinHandle;

pub async fn finish_realtime_writer_shutdown(
    writer: &mut JoinHandle<Result<usize, ObserverError>>,
    _drain_timeout: Duration,
) -> Result<Option<usize>, Box<dyn Error>> {
    let result = writer.await;
    let rows = result.map_err(boxed_error)?.map_err(boxed_error)?;
    Ok(Some(rows))
}

fn boxed_error<E>(error: E) -> Box<dyn Error>
where
    E: Error + 'static,
{
    Box::new(error)
}

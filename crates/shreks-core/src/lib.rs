//! Shared domain primitives for Shreks.

use std::{error::Error, fmt, str::FromStr};

/// Operating mode for the Shreks runtime.
///
/// Live execution is represented here as a state only. Permission to enter
/// `Live` will be guarded by later risk and promotion gates.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum RuntimeMode {
    #[default]
    Observe,
    Paper,
    Shadow,
    Live,
    Halted,
}

impl RuntimeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observe => "observe",
            Self::Paper => "paper",
            Self::Shadow => "shadow",
            Self::Live => "live",
            Self::Halted => "halted",
        }
    }
}

impl fmt::Display for RuntimeMode {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseRuntimeModeError {
    value: String,
}

impl ParseRuntimeModeError {
    fn new(value: &str) -> Self {
        Self {
            value: value.to_owned(),
        }
    }
}

impl fmt::Display for ParseRuntimeModeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "unsupported Shreks runtime mode '{}'; expected observe, paper, shadow, live, or halted",
            self.value
        )
    }
}

impl Error for ParseRuntimeModeError {}

impl FromStr for RuntimeMode {
    type Err = ParseRuntimeModeError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "observe" => Ok(Self::Observe),
            "paper" => Ok(Self::Paper),
            "shadow" => Ok(Self::Shadow),
            "live" => Ok(Self::Live),
            "halted" => Ok(Self::Halted),
            other => Err(ParseRuntimeModeError::new(other)),
        }
    }
}

// rustfmt resolves nested modules for the `shreks-observe` bin beneath the
// bin stem directory, while rustc resolves the historical module from
// `src/bin/observer_v2`. Keep one source of truth and let rustfmt traverse it.
include!("../observer_v2/sampler.rs");

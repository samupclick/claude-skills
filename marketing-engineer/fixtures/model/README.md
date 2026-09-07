# Model fixtures (MODEL_BACKEND=fixture)

One file per `task` name passed to `generate_json(task=...)`: `<task>.json`. Either a single JSON object,
or `{"outputs": [obj, obj, ...]}` replayed in call order (wrapping around). Every output is validated
against the schema the caller passes, so a stale fixture fails loudly. Record fixtures by running the
worker once with `MODEL_BACKEND=claude` and saving the validated output; never hand-write values that
look real.

# dict formats, used for writing and displaying ODE integration data
class DataFormatKeys:
    ZIPPED = "zipped"
    VARIABLES = "variables"


# dynamic (step size integration) variables)
class DynamicVariables:
    DYNAMIC_MAX_STEPS = 10000
    DYNAMIC_INITIAL_H = 0.01


class RunKeys:
    RESULT_DATA = "result_data"
    METRICS = "metrics"
    RUN_METADATA = "run_metadata"


class RunMetadataKeys:
    METRIC_NAMES = "metric_names"
    CALLBACK_NAMES = "callback_names"
    DIM_NAMES = "dim_names"
    VARIABLE_NAMES = "variable_names"
    TIMESTAMP = "timestamp"

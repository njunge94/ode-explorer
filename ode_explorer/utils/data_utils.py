import os
from typing import List, Dict, Text, Any

import pandas as pd

from ode_explorer.constants import ModelMetadataKeys
from ode_explorer.types import ModelState
from ode_explorer.utils.helpers import is_scalar

__all__ = ["initialize_dim_names", "convert_to_dict", "write_result_to_csv"]


def initialize_dim_names(variable_names: List[Text], state: ModelState):
    var_dims = []

    for k, v in zip(variable_names, state):
        dim = 1 if is_scalar(v) else len(v)

        var_dims.append((k, dim))

    dim_names = []
    for i, (name, dim) in enumerate(var_dims):
        if dim == 1:
            dim_names += [name]
        else:
            dim_names += ["{0}_{1}".format(name, i) for i in range(1, dim + 1)]

    return dim_names


def convert_to_dict(state: ModelState, model_metadata: Dict[Text, Any]):
    output_dict = dict()

    variable_names = model_metadata[ModelMetadataKeys.VARIABLE_NAMES]
    dim_names = model_metadata.get(ModelMetadataKeys.DIM_NAMES,
                                   initialize_dim_names(variable_names, state))

    idx = 0
    for i, name in enumerate(variable_names):
        v = state[i]

        if is_scalar(v):
            k = dim_names[idx]
            output_dict.update({k: v})
            idx += 1
        else:
            k = dim_names[idx:idx + len(v)]
            output_dict.update(dict(zip(k, v)))
            idx += len(v)

    return output_dict


def write_result_to_csv(result: List[Any],
                        out_dir: Text,
                        outfile_name: Text,
                        **kwargs) -> None:
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    file_ext = ".csv"

    # convert result_list to data frame, fast construction from list
    result_df = pd.DataFrame(data=result)

    out_file = os.path.join(out_dir, outfile_name)

    result_df.to_csv(out_file + file_ext, **kwargs)

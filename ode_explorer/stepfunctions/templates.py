import logging

import numpy as np
from scipy.optimize import root

from ode_explorer.models import ODEModel
from ode_explorer.types import StateVariable, ModelState
from ode_explorer.utils.helpers import is_scalar

logger = logging.getLogger(__name__)

__all__ = ["SingleStepMethod",
           "MultiStepMethod",
           "ExplicitRungeKuttaMethod",
           "ImplicitRungeKuttaMethod",
           "ExplicitMultiStepMethod",
           "ImplicitMultiStepMethod"]


class SingleStepMethod:
    """
    Base class for all ODE step functions.
    """

    def __init__(self, order: int = 0):
        # order of the method
        self.order = order
        self.model_dim = 0
        self.num_stages = 0

    def _adjust_dims(self, y: StateVariable):
        scalar_ode = is_scalar(y)

        if scalar_ode:
            model_dim = 1
            shape = (self.num_stages,)
        else:
            model_dim = len(y)
            shape = (self.num_stages, model_dim)

        self.model_dim = model_dim
        self.k = np.zeros(shape=shape)

    def _get_shape(self, y: StateVariable):
        return (self.num_stages,) if is_scalar(y) else (self.num_stages, len(y))

    @staticmethod
    def get_data_from_state(state: ModelState):
        return state

    @staticmethod
    def make_new_state(t: StateVariable, y: StateVariable) -> ModelState:
        return t, y

    def forward(self,
                model: ODEModel,
                state_dict: ModelState,
                h: float,
                **kwargs) -> ModelState:
        raise NotImplementedError


class MultiStepMethod:
    """
    Base class for explicit multi-step ODE solving methods.
    """

    def __init__(self,
                 startup: SingleStepMethod,
                 a_coeffs: np.ndarray,
                 b_coeffs: np.ndarray,
                 order: int = 0,
                 reverse: bool = True):

        self.order = order

        # startup calculation variables, only for multi-step methods
        self.ready = False
        self._cache_idx = 1
        self.startup = startup

        if reverse:
            self.a_coeffs = np.flip(a_coeffs)
            self.b_coeffs = np.flip(b_coeffs)
        else:
            self.a_coeffs = a_coeffs
            self.b_coeffs = b_coeffs

        # TODO: This is not good
        self.num_previous = max(len(b_coeffs), len(a_coeffs))

        # side cache for additional steps
        self.f_cache = np.zeros(self.num_previous)
        self.t_cache = np.zeros(self.num_previous)
        self.y_cache = np.zeros(self.num_previous)

    @staticmethod
    def get_data_from_state(state: ModelState):
        return state

    @staticmethod
    def make_new_state(t: StateVariable, y: StateVariable) -> ModelState:
        return t, y

    def _adjust_dims(self, y: StateVariable):
        scalar_ode = is_scalar(y)

        if scalar_ode:
            model_dim = 1
            shape = (self.num_previous,)

        else:
            model_dim = len(y)
            shape = (self.num_previous, model_dim)

        self.model_dim = model_dim
        self.f_cache = np.zeros(shape=shape)
        self.y_cache = np.zeros(shape=shape)

    def _get_shape(self, y: StateVariable):
        return (self.num_previous,) if is_scalar(y) else (self.num_previous, len(y))

    def _increment_cache_idx(self):
        self._cache_idx += 1

    def reset(self):
        # Resets the run so that next time the step function is called,
        # new startup values will be calculated with the saved startup step
        # function. Useful if the step function is supposed to be reused in
        # multiple non-consecutive runs.
        self.ready = False
        self._cache_idx = 1

    def perform_startup_calculation(self,
                                    model: ODEModel,
                                    state: ModelState,
                                    h: float,
                                    **kwargs):

        t, y = self.get_data_from_state(state=state)

        if self._get_shape(y) != self.y_cache.shape:
            self._adjust_dims(y)

        # fill function evaluation cache
        self.t_cache[0], self.y_cache[0], self.f_cache[0] = t, y, model(t, y)

        for i in range(1, self.num_previous):
            startup_state = self.startup.forward(model=model,
                                                 state=state,
                                                 h=h,
                                                 **kwargs)

            self.t_cache[i], self.y_cache[i] = startup_state
            self.f_cache[i] = model(self.t_cache[i], self.y_cache[i])
            state = startup_state

        self.ready = True
        self._increment_cache_idx()

    def get_cached_state(self):
        idx = self._cache_idx
        self._increment_cache_idx()
        return self.make_new_state(t=self.t_cache[idx], y=self.y_cache[idx])

    def forward(self,
                model: ODEModel,
                state: ModelState,
                h: float,
                **kwargs) -> ModelState:
        raise NotImplementedError


class ExplicitRungeKuttaMethod(SingleStepMethod):
    def __init__(self,
                 alphas: np.ndarray,
                 betas: np.ndarray,
                 gammas: np.ndarray,
                 order: int = 0):

        super(ExplicitRungeKuttaMethod, self).__init__(order=order)

        self.validate_butcher_tableau(alphas=alphas, betas=betas, gammas=gammas)

        self.alphas = alphas
        self.betas = betas
        self.gammas = gammas
        self.num_stages = len(self.alphas)
        self.k = np.zeros(betas.shape[0])

    @staticmethod
    def validate_butcher_tableau(alphas: np.ndarray,
                                 betas: np.ndarray,
                                 gammas: np.ndarray) -> None:
        _error_msg = []
        if len(alphas) != len(gammas):
            _error_msg.append("Alpha and gamma vectors are not the same length")

        if betas.shape[0] != betas.shape[1]:
            _error_msg.append("Betas must be a quadratic matrix with the same "
                              "dimension as the alphas/gammas arrays")

        # for an explicit method, betas must be lower triangular
        if not np.allclose(betas, np.tril(betas, k=-1)):
            _error_msg.append("The beta matrix has to be lower triangular for "
                              "an explicit Runge-Kutta method, i.e. "
                              "b_ij = 0 for i <= j")

        if _error_msg:
            raise ValueError("An error occurred while validating the input "
                             "Butcher tableau. More information: "
                             "{}.".format(",".join(_error_msg)))

    def forward(self,
                model: ODEModel,
                state: ModelState,
                h: float,
                **kwargs) -> ModelState:

        t, y = self.get_data_from_state(state=state)

        if self._get_shape(y) != self.k.shape:
            self._adjust_dims(y)

        self.k[0] = model(t, y)

        for i in range(1, self.num_stages):
            # first row of betas is a zero row because it is an explicit RK
            self.k[i] = model(t + h * self.alphas[i], y + h * np.dot(self.betas[i], self.k))

        y_new = y + h * np.dot(self.gammas, self.k)

        return self.make_new_state(t=t + h, y=y_new)


class ImplicitRungeKuttaMethod(SingleStepMethod):
    def __init__(self,
                 alphas: np.ndarray,
                 betas: np.ndarray,
                 gammas: np.ndarray,
                 order: int = 0,
                 **kwargs):

        super(ImplicitRungeKuttaMethod, self).__init__(order=order)

        self.validate_butcher_tableau(alphas=alphas, betas=betas, gammas=gammas)

        self.alphas = alphas
        self.betas = betas
        self.gammas = gammas
        self.num_stages = len(self.alphas)
        self.k = np.zeros(betas.shape[0])

        # scipy.optimize.root options
        self.solver_kwargs = kwargs

    @staticmethod
    def validate_butcher_tableau(alphas: np.ndarray,
                                 betas: np.ndarray,
                                 gammas: np.ndarray) -> None:
        _error_msg = []
        if len(alphas) != len(gammas):
            _error_msg.append("Alpha and gamma vectors are "
                              "not the same length")

        if betas.shape[0] != betas.shape[1]:
            _error_msg.append("Betas must be a quadratic matrix with the same "
                              "dimension as the alphas/gammas arrays")

        if betas.shape[0] == 1:
            _error_msg.append("You have supplied a single-stage implicit RK method. Please use the "
                              "builtin BackwardEuler class instead.")

        if _error_msg:
            raise ValueError("An error occurred while validating the input "
                             "Butcher tableau. More information: "
                             "{}.".format(",".join(_error_msg)))

    def forward(self,
                model: ODEModel,
                state: ModelState,
                h: float,
                **kwargs) -> ModelState:

        t, y = self.get_data_from_state(state=state)

        if self._get_shape(y) != self.k.shape:
            self._adjust_dims(y)

        initial_shape = self.k.shape
        shape_prod = np.prod(initial_shape)

        def F(x: np.ndarray) -> np.ndarray:
            # kwargs are not allowed in scipy.optimize, so pass tuple instead
            model_stack = np.concatenate([model(t + h * self.alphas[i],
                                                y + h * np.dot(self.betas[i], x.reshape(initial_shape)))
                                          for i in range(self.num_stages)])

            return model_stack - x

        # sort the kwargs before putting them into the tuple passed to root
        if kwargs:
            args = tuple(kwargs[arg] for arg in model.fn_args.keys())
        else:
            args = ()

        # TODO: Retry here in case of convergence failure?
        root_res = root(F, x0=self.k.reshape((shape_prod,)), args=args, **self.solver_kwargs)

        y_new = y + h * np.dot(self.gammas, root_res.x.reshape(initial_shape))

        return self.make_new_state(t=t + h, y=y_new)


class ExplicitMultiStepMethod(MultiStepMethod):
    """
    Base class for explicit multi-step ODE solving methods.
    """

    def __init__(self,
                 startup: SingleStepMethod,
                 a_coeffs: np.ndarray,
                 b_coeffs: np.ndarray,
                 order: int = 0,
                 reverse: bool = True):

        super(ExplicitMultiStepMethod, self).__init__(startup=startup,
                                                      a_coeffs=a_coeffs,
                                                      b_coeffs=b_coeffs,
                                                      order=order,
                                                      reverse=reverse)

    def forward(self,
                model: ODEModel,
                state: ModelState,
                h: float,
                **kwargs) -> ModelState:
        if not self.ready:
            # startup calculation to the multi-step method,
            # fills the y-, t- and f-caches
            self.perform_startup_calculation(model=model,
                                             state=state,
                                             h=h,
                                             **kwargs)

            return self.make_new_state(self.t_cache[1], self.y_cache[1])

        t, y = self.get_data_from_state(state=state)

        if self._cache_idx < self.num_previous:
            return self.get_cached_state()

        y_new = y + h * np.dot(self.b_coeffs, self.f_cache)

        self.f_cache = np.roll(self.f_cache, shift=-1, axis=0)
        self.f_cache[-1] = model(t + h, y_new)

        return self.make_new_state(t=t + h, y=y_new)


class ImplicitMultiStepMethod(MultiStepMethod):
    """
    Adams-Bashforth Method of order 2 for ODE solving.
    """

    def __init__(self,
                 startup: SingleStepMethod,
                 a_coeffs: np.ndarray,
                 b_coeffs: np.ndarray,
                 order: int = 0,
                 reverse: bool = True,
                 **kwargs):

        super(ImplicitMultiStepMethod, self).__init__(startup=startup,
                                                      a_coeffs=a_coeffs,
                                                      b_coeffs=b_coeffs,
                                                      order=order,
                                                      reverse=reverse)

        # scipy.optimize.root options
        self.solver_kwargs = kwargs

    def forward(self,
                model: ODEModel,
                state: ModelState,
                h: float,
                **kwargs) -> ModelState:

        if not self.ready:
            # startup calculation to the multi-step method,
            # fills the state and f-caches
            self.perform_startup_calculation(model=model,
                                             state=state,
                                             h=h,
                                             **kwargs)

            # first cached value
            return self.make_new_state(self.t_cache[1], self.y_cache[1])

        b = self.b_coeffs[-1]

        t, y = self.get_data_from_state(state=state)

        if self._cache_idx < self.num_previous:
            return self.get_cached_state()

        def F(x: StateVariable) -> StateVariable:
            return x + np.dot(self.a_coeffs, self.y_cache) - h * b * model(t + h, x)

        if kwargs:
            args = tuple(kwargs[arg] for arg in model.fn_args.keys())
        else:
            args = ()

        # TODO: Retry here in case of convergence failure?
        root_res = root(F, x0=y, args=args, **self.solver_kwargs)

        y_new = root_res.x

        self.y_cache = np.roll(self.y_cache, shift=-1, axis=0)
        self.y_cache[-1] = y_new

        return self.make_new_state(t=t + h, y=y_new)

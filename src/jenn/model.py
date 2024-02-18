"""Model.
=========

This module contains the main class to train a neural net and make
predictions. It acts as an interface between the user and the core 
functions doing computations under-the-hood. 

.. code-block:: python

    #################
    # Example Usage #
    #################

    import jenn 

    # Fit model
    nn = jenn.model.NeuralNet(
        layer_sizes=[
            x_train.shape[0],  # input layer 
            7, 7,              # hidden layer(s) -- user defined
            y_train.shape[0]   # output layer 
         ],  
        ).fit(
            x_train, y_train, dydx_train, **kwargs # note: user must provide this
        )

    # Predict response only 
    y_pred = nn.predict(x_test)

    # Predict partials only 
    dydx_pred = nn.predict_partials(x_train)

    # Predict response and partials in one step (preferred)
    y_pred, dydx_pred = nn.evaluate(x_test) 

.. Note::
    The method `evaluate()` is preferred over separately 
    calling `predict()` followed by `predict_partials()` 
    whenever both the response and its partials are needed at the same point. 
    This saves computations since, in the latter approach, forward propagation 
    is unecessarily performed twice. Similarly, to avoid unecessary partial
    deerivative calculations, the `predict()` method should be preferred whenever
    only response values are needed. The method `predict_partials()` is provided 
    for those situations where it is necessary to separate out Jacobian predictions, 
    due to how some target optimization software architected for example.  
"""  # noqa: W291

from pathlib import Path
from typing import Any, Self

import numpy as np

from .core.cache import Cache
from .core.data import Dataset, denormalize, denormalize_partials, normalize
from .core.parameters import Parameters
from .core.propagation import model_forward, model_partials_forward, partials_forward
from .core.training import train_model

__all__ = ["NeuralNet"]


class NeuralNet:
    """Neural network model.

    :param layer_sizes: number of nodes in each layer (including
        input/output layers)
    :param hidden_activation: activation function used in hidden layers
    :param output_activation: activation function used in output layer
    """

    def __init__(
        self,
        layer_sizes: list[int],
        hidden_activation: str = "tanh",
        output_activation: str = "linear",
    ):  # noqa D107
        self.history: dict[Any, Any] | None = None
        self.parameters = Parameters(
            layer_sizes,
            hidden_activation,
            output_activation,
        )

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        dydx: np.ndarray | None = None,
        is_normalize: bool = False,
        alpha: float = 0.050,
        lambd: float = 0.000,
        gamma: float = 1.000,
        beta1: float = 0.900,
        beta2: float = 0.999,
        epochs: int = 1,
        batch_size: int | None = None,
        max_iter: int = 200,
        shuffle: bool = True,
        random_state: int | None = None,
        is_backtracking: bool = False,
        is_verbose: bool = False,
    ) -> Self:  # noqa: PLR0913
        r"""Train neural network.

        :param x: training data inputs, array of shape (n_x, m)
        :param y: training data outputs, array of shape (n_y, m)
        :param dydx: training data Jacobian, array of shape (n_y, n_x, m)
        :param is_normalize: normalize training by mean and variance
        :param alpha: optimizer learning rate for line search
        :param lambd: regularization coefficient to avoid overfitting
        :param gamma: jacobian-enhancement regularization coefficient
        :param beta1: `ADAM <https://arxiv.org/abs/1412.6980>`_ optimizer hyperparameter to control momentum
        :param beta2: ADAM optimizer hyperparameter to control momentum
        :param epochs: number of passes through data
        :param batch_size: size of each batch for minibatch
        :param max_iter: max number of optimizer iterations
        :param shuffle: shuffle minibatches or not
        :param random_state: control repeatability
        :param is_backtracking: use backtracking line search or not
        :param is_verbose: print out progress for each (iteration, batch, epoch)
        :return: NeuralNet instance (self)

        .. warning::
                Normalization usually helps, except when the training
                data is made up of very small numbers. In that case,
                normalizing by the variance has the undesirable effect
                of dividing by a very small number and should not be used.
        """
        data = Dataset(x, y, dydx)
        params = self.parameters
        params.mu_x[:] = 0.0
        params.mu_y[:] = 0.0
        params.sigma_x[:] = 1.0
        params.sigma_y[:] = 1.0
        if is_normalize:
            params.mu_x[:] = data.avg_x
            params.mu_y[:] = data.avg_y
            params.sigma_x[:] = data.std_x
            params.sigma_y[:] = data.std_y
            data = data.normalize()
        self.history = train_model(
            data,
            params,
            # hyperparameters
            alpha=alpha,
            lambd=lambd,
            gamma=gamma,
            beta1=beta1,
            beta2=beta2,
            # options
            epochs=epochs,
            max_iter=max_iter,
            batch_size=batch_size,
            shuffle=shuffle,
            random_state=random_state,
            is_backtracking=is_backtracking,
            is_verbose=is_verbose,
        )
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        r"""Predict responses.

        :param x: vectorized inputs, array of shape (n_x, m)
        :return: predicted response(s), array of shape (n_y, m)
        """
        params = self.parameters
        cache = Cache(params.layer_sizes, m=x.shape[1])
        x_norm = normalize(x, params.mu_x, params.sigma_x)
        y_norm = model_forward(x_norm, params, cache)
        y = denormalize(y_norm, params.mu_y, params.sigma_y)
        return y

    def predict_partials(self, x: np.ndarray) -> np.ndarray:
        r"""Predict partials.

        :param x: vectorized inputs, array of shape (n_x, m)
        :return: predicted partial(s), array of shape (n_y, n_x, m)
        """
        params = self.parameters
        cache = Cache(params.layer_sizes, m=x.shape[1])
        x_norm = normalize(x, params.mu_x, params.sigma_x)
        dydx_norm = partials_forward(x_norm, params, cache)
        dydx = denormalize_partials(dydx_norm, params.sigma_x, params.sigma_y)
        return dydx

    def evaluate(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r"""Predict responses and their partials.

        :param x: vectorized inputs, array of shape (n_x, m)
        :return: predicted response(s), array of shape (n_y, m)
        :return: predicted partial(s), array of shape (n_y, n_x, m)
        """
        params = self.parameters
        cache = Cache(params.layer_sizes, m=x.shape[1])
        x_norm = normalize(x, params.mu_x, params.sigma_x)
        y_norm, dydx_norm = model_partials_forward(x_norm, params, cache)
        y = denormalize(y_norm, params.mu_y, params.sigma_y)
        dydx = denormalize_partials(dydx_norm, params.sigma_x, params.sigma_y)
        return y, dydx

    def save(self, file: str | Path = "parameters.json") -> None:
        """Serialize parameters and save to JSON file."""
        self.parameters.save(file)

    def load(self, file: str | Path = "parameters.json") -> Self:
        """Load previously saved parameters from json file."""
        self.parameters.load(file)
        return self
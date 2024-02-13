"""Neural network model.

This module contains the main class to train a neural net and make
predictions. It is in charge of setting up and calling the right support
functions to accomplish these various tasks.
"""

from pathlib import Path
from typing import Any, Self

import numpy as np

from .core.cache import Cache
from .core.data import Dataset, denormalize, denormalize_partials, normalize
from .core.parameters import Parameters
from .core.propagation import model_forward, model_partials_forward, partials_forward
from .core.training import train_model
from .utils.decorators import timeit

__all__ = ["NeuralNet"]


class NeuralNet:
    """Neural network model.

    Parameters
    ----------
    layer_sizes: list[int]
        The number of nodes in each layer of the neural
        network, including input and output layers.

    hidden_activation: str, optional
        The activation function to use for hidden layers.
        Default is "tanh". Options are: "relu", "linear", "tanh"

    output_activation: str, optional
        The activation function to use for the output layer.
        Default is "linear". Options are: "relu", "linear", "tanh"
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
        is_timed: bool = False,
    ) -> Self:  # noqa: PLR0913
        r"""Train neural network.

        Parameters
        ----------
        x: numpy.ndarray
            Training data inputs. Array of shape (n_x, m)

            .. math::
                \boldsymbol{X}
                =
                \left(
                \begin{matrix}
                x_1^{(1)} & \dots & x_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                x_{n_x}^{(1)} & \dots & x_{n_x}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_x \times m}

        y: numpy.ndarray
            Training data outputs. Array of shape (n_y, m)

            .. math::
                \boldsymbol{Y}
                =
                \left(
                \begin{matrix}
                y_1^{(1)} & \dots & y_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                y_{n_y}^{(1)} & \dots & y_{n_y}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times m}

        dydx: numpy.ndarray
            Training data gradients. Array of shape (n_y, n_x, m)

            .. math::
                \boldsymbol{J}
                =
                \left(
                \begin{matrix}
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(1)}
                &
                \dots
                &
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(m)}
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times n_x \times m}

        is_normalize: bool, optional
            Normalize training data by mean and variance. Default is False.

            .. math::
                \bar{x} = \frac{x - \mu_x}{\sigma_x}
                \qquad
                \bar{y} = \frac{y - \mu_y}{\sigma_y}
                \qquad
                \frac{\partial \bar{y}}{\partial \bar{x}} = \frac{\sigma_y}{\sigma_x} \frac{\partial y}{\partial x}

            .. warning::
                Use this option wisely! Normalization usually helps,
                except when the training data is made up of very small
                numbers. In that case, normalizing by the variance
                has the undesirable effect of dividing by a very small number.

        alpha: float, optional
            Learning rate to control step size during optimizer line search.
            Default is 0.05

            .. math::
                \theta := \theta - \alpha \frac{\partial \mathcal{J}}{\partial \theta}

        lambd: float, optional
            Regularization coefficient (controls how much to penalize
            objective function for over-fitting)
            Default is 0.0

        gamma: float, optional
            Gradient-enhancement coefficient (controls important of 1st-order
            accuracy errors in objective function.)
            Default is 1.0 (full gradient-enhancement)
            Note: only active when dydx is provided (ignored otherwise)

        beta1: float, optional
            Hyperparameter that controls momentum for
            [ADAM](https://arxiv.org/abs/1412.6980) optimizer.
            Default is 0.9

        beta2: float, optional
            Hyperparameter that controls momentum for
            [ADAM](https://arxiv.org/abs/1412.6980) optimizer.
            Default is 0.999

        epochs: int, optional
            Number of epochs (passes through data). Default is 1.
            Note: total number of objective function calls =
                    number of epochs
                        x number of batches
                            x number of iterations (search directions)
                                x number of evaluations along each line search

        batch_size: int, optional
            Size of each batch for minibatch, which is a routine that randomly
            splits the data into discrete batches to train faster (in cases
            where data is very large).
            Note: total number of objective function calls =
                    number of epochs
                        x number of batches
                            x number of iterations (search directions)
                                x number of evaluations along each line search

        max_iter: int, optional
            Maximum number of optimizer iterations. Default 200.
            Note: total number of objective function calls =
                    number of epochs
                        x number of batches
                            x number of iterations (search directions)
                                x number of evaluations along each line search

        shuffle: bool, optional
            Shuffle data for minibatch. Default is True.

        random_state: int, optional
            Random seed for minibatch repeatability. Default is None.

        is_backtracking: bool, optional
            Use backtracking line search, where step size is progressively
            reduced (multiple steps) until cost function no longer improves
            along search direction. Default is False (single step).
            Note: total number of objective function calls =
                    number of epochs
                        x number of batches
                            x number of iterations (search directions)
                                x number of evaluations along each line search

        is_verbose: bool, optional
            Print out progress for each iteration, each batch, each epoch.
            Default is False.

        is_timed: bool, optional
            Print elapsed time. Default is False.
        """

        @timeit
        def fit(*args) -> NeuralNet:  # type: ignore[no-untyped-def]
            return self.fit(*args)

        if is_timed:
            return fit(
                x,
                y,
                dydx,
                is_normalize,
                alpha,
                lambd,
                gamma,
                beta1,
                beta2,
                epochs,
                batch_size,
                max_iter,
                shuffle,
                random_state,
                is_backtracking,
                is_verbose,
            )
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

        Parameters
        ----------
        x: numpy.ndarray
            Training data inputs. Array of shape (n_x, m)

            .. math::
                \boldsymbol{X}
                =
                \left(
                \begin{matrix}
                x_1^{(1)} & \dots & x_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                x_{n_x}^{(1)} & \dots & x_{n_x}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_x \times m}

        Return
        ------
        y: numpy.ndarray
            Training data outputs. Array of shape (n_y, m)

            .. math::
                \boldsymbol{Y}
                =
                \left(
                \begin{matrix}
                y_1^{(1)} & \dots & y_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                y_{n_y}^{(1)} & \dots & y_{n_y}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times m}
        """
        params = self.parameters
        cache = Cache(params.layer_sizes, m=x.shape[1])
        x_norm = normalize(x, params.mu_x, params.sigma_x)
        y_norm = model_forward(x_norm, params, cache)
        y = denormalize(y_norm, params.mu_y, params.sigma_y)
        return y

    def predict_partials(self, x: np.ndarray) -> np.ndarray:
        r"""Predict partials.

        Note:
            This function needs to call model_forward before
            calling partials_forward because partials require
            information computed during model_forward. Consider
            using 'evaluate(x)' instead if both partials and function
            evaluations are needed at the same x (its more
            efficient than running predict(x) followed by predict_partials(x)
            which would end up running model_forward(x) twice under the hood)

        Parameters
        ----------
        x: numpy.ndarray
            Training data inputs. Array of shape (n_x, m)

            .. math::
                \boldsymbol{X}
                =
                \left(
                \begin{matrix}
                x_1^{(1)} & \dots & x_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                x_{n_x}^{(1)} & \dots & x_{n_x}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_x \times m}

        Returns
        -------
        dydx: numpy.ndarray
            Training data gradients. Array of shape (n_y, n_x, m)

            .. math::
                \boldsymbol{J}
                =
                \left(
                \begin{matrix}
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(1)}
                &
                \dots
                &
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(m)}
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times n_x \times m}
        """
        params = self.parameters
        cache = Cache(params.layer_sizes, m=x.shape[1])
        x_norm = normalize(x, params.mu_x, params.sigma_x)
        dydx_norm = partials_forward(x_norm, params, cache)
        dydx = denormalize_partials(dydx_norm, params.sigma_x, params.sigma_y)
        return dydx

    def evaluate(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r"""Predict responses and their partials.

        .. note::
            This is the preferred method whenever y and dy/dx are both
            needed. It is more efficient than separately calling
            `predict(x)` followed by `predict_partials(x)` which, under the hood,
            would unecessarily require running `model_forward(x)` twice.

        Parameters
        ----------
        x: numpy.ndarray
            Training data inputs. Array of shape (n_x, m)

            .. math::
                \boldsymbol{X}
                =
                \left(
                \begin{matrix}
                x_1^{(1)} & \dots & x_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                x_{n_x}^{(1)} & \dots & x_{n_x}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_x \times m}

        Returns
        -------
        y: numpy.ndarray
            Training data outputs. Array of shape (n_y, m)

            .. math::
                \boldsymbol{Y}
                =
                \left(
                \begin{matrix}
                y_1^{(1)} & \dots & y_1^{(m)} \\
                \vdots & \ddots & \vdots \\
                y_{n_y}^{(1)} & \dots & y_{n_y}^{(m)} \\
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times m}

        dydx: numpy.ndarray
            Training data gradients. Array of shape (n_y, n_x, m)

            .. math::
                \boldsymbol{J}
                =
                \left(
                \begin{matrix}
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(1)}
                &
                \dots
                &
                {\left(
                \begin{matrix}
                \frac{\partial y_1}{\partial x_1} & \dots & \frac{\partial y_1}{\partial x_{n_x}}  \\
                \vdots & \ddots & \vdots \\
                \frac{\partial y_{n_y}}{\partial x_1} & \dots & \frac{\partial y_{n_y}}{\partial x_{n_x}}  \\
                \end{matrix}
                \right)}^{(m)}
                \end{matrix}
                \right)
                \in
                \mathbb{R}^{n_y \times n_x \times m}
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
        """Load parameters from specified json file."""
        self.parameters.load(file)
        return self

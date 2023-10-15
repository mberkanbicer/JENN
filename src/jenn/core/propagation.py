"""Forward and backward propagation."""
import numpy as np
from.cache import Cache

from .activation import Relu, Tanh, Linear


ACTIVATIONS = dict(
    relu=Relu,
    tanh=Tanh,
    linear=Linear,
)


def _eye(n_x, m):
    I = np.eye(n_x, dtype=float)
    return np.repeat(I.reshape((n_x, n_x, 1)), m, axis=2)


def first_layer_forward(X, cache: Cache = None):
    """Compute input layer activations."""
    cache.A[0][:] = X


def first_layer_partials(X, cache: Cache = None):
    """Compute input layer partials."""
    n_x, m = X.shape
    cache.A_prime[0][:] = _eye(n_x, m)


def next_layer_partials(layer, parameters, cache: Cache = None):
    """Compute j^th partial for one layer."""
    r = layer
    s = layer - 1
    W = parameters.W[layer]
    g = ACTIVATIONS[parameters.a[layer]]
    cache.G_prime[r][:] = g.first_derivative(cache.Z[r], cache.A[r])
    for j in range(parameters.n_x):
        cache.Z_prime[r][:, j, :] = np.dot(W, cache.A_prime[s][:, j, :])
        cache.A_prime[r][:, j, :] = cache.G_prime[r] * np.dot(W, cache.A_prime[s][:, j, :])
    return cache.A_prime[r]


def next_layer_forward(layer, parameters, cache):
    """Propagate forward through one layer."""
    r = layer
    s = layer - 1
    W = parameters.W[r]
    b = parameters.b[r]
    g = ACTIVATIONS[parameters.a[r]]
    Z = cache.Z[r]
    A = cache.A[r]
    np.dot(W, cache.A[s], out=Z)
    Z += b
    g.evaluate(Z, A)


def model_partials_forward(X, parameters, cache: Cache):
    """Propagate forward through all layers, including partials."""
    first_layer_forward(X, cache)
    first_layer_partials(X, cache)
    for layer in parameters.layers[1:]:
        next_layer_forward(layer, parameters, cache)
        next_layer_partials(layer, parameters, cache)
    return cache.A[-1], cache.A_prime[-1]


def model_forward(X, parameters, cache: Cache):
    """Propagate forward through all layers, but don't compute partials."""
    first_layer_forward(X, cache)
    for layer in parameters.layers[1:]:
        next_layer_forward(layer, parameters, cache)
    return cache.A[-1]


def partials_forward(X, parameters, cache: Cache):
    """Propagate forward through all layers, but return only partials."""
    return model_partials_forward(X, parameters, cache)[-1]


def last_layer_backward(cache, data):
    """Propagate backward through last layer."""
    cache.dA[-1][:] = cache.A[-1] - data.Y
    if data.J is not None:
        cache.dA_prime[-1][:] = cache.A_prime[-1] - data.J
    else:
        cache.dA_prime[-1][:] = np.zeros((data.n_y, data.n_x, data.m))


def next_layer_backward(layer, parameters, cache, data, lambd):
    """Propagate backward through next layer."""
    cache = cache
    parameters = parameters
    r = layer
    s = layer - 1
    g = ACTIVATIONS[parameters.a[r]]
    g.first_derivative(cache.Z[r], cache.A[r], cache.G_prime[r])
    np.dot(cache.G_prime[r] * cache.dA[r], cache.A[s].T, out=parameters.dW[r])
    parameters.dW[r] /= data.m
    parameters.dW[r] += lambd / data.m * parameters.W[r]
    np.sum(cache.G_prime[r] * cache.dA[r], axis=1, keepdims=True, out=parameters.db[r])
    parameters.db[r] /= data.m
    np.dot(parameters.W[r].T, cache.G_prime[r] * cache.dA[r], out=cache.dA[s])


def gradient_enhancement(layer, parameters, cache, data, gamma):
    """Modify layer partials for gradient enhancement."""
    if np.allclose(gamma, 0.0):
        return
    r = layer
    s = layer - 1
    g = ACTIVATIONS[parameters.a[r]]
    cache.G_prime_prime[r][:] = g.second_derivative(cache.Z[r], cache.A[r], cache.G_prime[r])
    for j in range(parameters.n_x):
        parameters.dW[r] += gamma / data.m * (np.dot(cache.dA_prime[r][:, j, :] * cache.G_prime_prime[r] * cache.Z_prime[r][:, j, :], cache.A[s].T) + np.dot(cache.dA_prime[r][:, j, :] * cache.G_prime[r], cache.A_prime[s][:, j, :].T))
        parameters.db[r] += gamma / data.m * np.sum(cache.dA_prime[r][:, j, :] * cache.G_prime_prime[r] * cache.Z_prime[r][:, j, :], axis=1, keepdims=True)
        cache.dA[s] += gamma * np.dot(parameters.W[r].T, cache.dA_prime[r][:, j, :] * cache.G_prime_prime[r] * cache.Z_prime[r][:, j, :])
        cache.dA_prime[s][:, j, :] = gamma * np.dot(parameters.W[r].T, cache.dA_prime[r][:, j, :] * cache.G_prime[r])


def model_backward(data, parameters, cache, lambd=0.0, gamma=0.0):
    """Propagate backward through all layers."""
    last_layer_backward(cache, data)
    for layer in reversed(parameters.layers):
        if layer > 0:
            next_layer_backward(layer, parameters, cache, data, lambd)
            gradient_enhancement(layer, parameters, cache, data, gamma)

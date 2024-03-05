import numpy as np
import dctkit as dt
import jax.numpy as jnp
from jax import jit, grad, Array
from dctkit.math.opt import optctrl
from scipy import sparse
import os
from dctkit.physics import elastica as el
import numpy.typing as npt
from dctkit.dec import cochain as C
from typing import Tuple


def compute_transform_theta_xy(num_nodes: int) -> npt.NDArray:
    # bidiagonal matrix to transform theta in (x,y)
    diag = [1]*(num_nodes)
    upper_diag = [-1]*(num_nodes-1)
    upper_diag[0] = 0
    diags = [diag, upper_diag]
    transform = sparse.diags(diags, [0, -1]).toarray()
    transform[1, 0] = -1
    return transform


def reconstruct_xy(theta: Array, h: float, num_nodes: int) -> Tuple[Array, Array]:
    transform = compute_transform_theta_xy(num_nodes)
    cos_theta = h*jnp.cos(theta)
    sin_theta = h*jnp.sin(theta)
    b_x = jnp.insert(cos_theta, 0, 0)
    b_y = jnp.insert(sin_theta, 0, 0)
    x = jnp.linalg.solve(transform, b_x)
    y = jnp.linalg.solve(transform, b_y)
    return x, y


def compute_true_solution(data: npt.NDArray, sampling: int,
                          num_elements: int) -> Tuple[npt.NDArray, npt.NDArray,
                                                      npt.NDArray]:
    x_true = data[:, 1][::sampling]
    y_true = data[:, 2][::sampling]
    theta_true = np.empty(num_elements, dtype=dt.float_dtype)
    for i in range(num_elements):
        theta_true[i] = np.arctan(
            (y_true[i+1]-y_true[i])/(x_true[i+1]-x_true[i]))

    return theta_true, x_true, y_true


def test_elastica_energy(setup_test):
    data = "data/xy_F_20.txt"
    F = -20.
    np.random.seed(42)

    # load true data
    filename = os.path.join(os.path.dirname(__file__), data)
    data = np.genfromtxt(filename)

    # sampling factor for true data
    sampling = 10

    num_elements = 10

    L = 1
    h = L/(num_elements)

    ela = el.Elastica(num_elements=num_elements, L=L)
    num_nodes = ela.S.num_nodes

    # initial guess for the angles (EXCEPT THE FIRST ANGLE, FIXED BY BC)
    theta_in = 0.1*np.random.rand(num_elements-1).astype(dt.float_dtype)

    B_in = 1.

    # compute true solution
    theta_true, x_true, y_true = compute_true_solution(data, sampling, num_elements)

    energy_grad = jit(grad(ela.energy))

    # state function: stationarity conditions of the elastic energy
    def statefun(x: npt.NDArray, theta_0: float, F: float) -> Array:
        theta = x[:-1]
        B = x[-1]
        return energy_grad(theta, B=B, theta_0=theta_0, F=F)

    # define extra_args
    constraint_args = {'theta_0': theta_true[0], 'F': F}
    obj_args = {'theta_true': theta_true}

    def obj(x: npt.NDArray, theta_true: npt.NDArray) -> Array:
        theta_guess = x[:-1]
        B_guess = x[-1]
        return ela.obj_stiffness(theta_guess, B_guess, theta_true)

    prb = optctrl.OptimalControlProblem(objfun=obj,
                                        statefun=statefun,
                                        state_dim=num_elements-1,
                                        nparams=num_elements,
                                        constraint_args=constraint_args,
                                        obj_args=obj_args)

    # initial guess for the bending stiffness
    B_in = 1*np.ones(1, dtype=dt.float_dtype)
    x0 = np.concatenate((theta_in, B_in))
    x = prb.solve(x0=x0)

    # extend solution array with boundary element
    theta = x[:-1]
    theta = np.insert(theta, 0, theta_true[0])

    x, y = reconstruct_xy(theta, h, num_nodes)

    error = np.linalg.norm(x - x_true) + np.linalg.norm(y - y_true)
    assert error <= 2e-2


def test_elastica_residual(setup_test):
    data = "data/xy_F_35.txt"
    F = -35.
    np.random.seed(42)

    # load true data
    filename = os.path.join(os.path.dirname(__file__), data)
    data = np.genfromtxt(filename)

    # sampling factor for true data
    sampling = 10

    num_elements = 10

    L = 1
    h = L/(num_elements)

    B = 7.854

    A = F*L**2/B

    ela = el.Elastica(num_elements=num_elements, L=L)
    num_nodes = ela.S.num_nodes

    # compute true solution
    theta_true, x_true, y_true = compute_true_solution(data, sampling, num_elements)

    # initial guess for the angles (EXCEPT PRESCRIBED ANGLE AT LEFT END)
    theta_0 = np.zeros(num_elements-1, dtype=dt.float_dtype)

    # internal cochain
    intc = np.ones(num_nodes, dtype=dt.float_dtype)
    intc[0] = 0.
    intc[-1] = 0.
    int_coch = C.CochainP0(ela.S, intc)

    # cochain to zero residual on elements where BC is prescribed
    mask = np.ones(num_elements, dtype=dt.float_dtype)
    mask[0] = 0.

    def obj(x: npt.NDArray) -> Array:
        # apply Dirichlet BC at left end
        theta = jnp.insert(x, 0, theta_true[0])
        theta_coch = C.CochainD0(ela.S, theta)

        # dimensionless curvature at primal nodes (primal 0-cochain)
        dtheta = C.coboundary(theta_coch)
        curv = C.cochain_mul(int_coch, C.star(dtheta))

        load = C.scalar_mul(C.cos(theta_coch), A)

        # dimensionless bending moment
        moment = curv

        residual = C.sub(C.codifferential(C.star(moment)), load)

        return jnp.linalg.norm(residual.coeffs[1:])

    prb = optctrl.OptimizationProblem(
        dim=num_elements-1, state_dim=num_elements-1, objfun=obj)

    prb.set_obj_args({})
    sol = prb.solve(x0=theta_0)
    theta = jnp.insert(sol, 0, theta_true[0])

    x, y = reconstruct_xy(theta, h, num_nodes)

    error = np.linalg.norm(x - x_true) + np.linalg.norm(y - y_true)
    assert error <= 2e-2


def test_elastica_residual_tuneB(setup_test):
    data = "data/xy_F_35.txt"
    F = -35.
    np.random.seed(42)

    # load true data
    filename = os.path.join(os.path.dirname(__file__), data)
    data = np.genfromtxt(filename)

    # sampling factor for true data
    sampling = 10

    num_elements = 10

    L = 1
    h = L/(num_elements)

    ela = el.Elastica(num_elements=num_elements, L=L)
    num_nodes = ela.S.num_nodes

    # initial guess for the angles (EXCEPT THE FIRST ANGLE, FIXED BY BC)
    theta_in = np.zeros(num_elements-1, dtype=dt.float_dtype)

    B_in = 1.

    # compute true solution
    theta_true, x_true, y_true = compute_true_solution(data, sampling, num_elements)

    # internal cochain
    intc = np.ones(num_nodes, dtype=dt.float_dtype)
    intc[0] = 0.
    intc[-1] = 0.
    int_coch = C.CochainP0(ela.S, intc)

    # cochain to zero residual on elements where BC is prescribed
    mask = np.ones(num_elements, dtype=dt.float_dtype)
    mask[0] = 0.

    def energy(theta: npt.NDArray, B, theta_0, F) -> Array:
        # apply Dirichlet BC at left end
        theta = jnp.insert(theta, 0, theta_0)
        theta_coch = C.CochainD0(ela.S, theta)

        # dimensionless curvature at primal nodes (primal 0-cochain)
        dtheta = C.coboundary(theta_coch)
        curv = C.cochain_mul(int_coch, C.star(dtheta))

        A = F*L**2/B

        A_coch = C.CochainD0(ela.S, A*jnp.ones(num_elements, dtype=dt.float_dtype))

        load = C.cochain_mul(C.cos(theta_coch), A_coch)

        # dimensionless bending moment
        moment = curv

        residual = C.sub(C.codifferential(C.star(moment)), load)

        return residual.coeffs.flatten()[1:]

    energy_grad = energy

    # state function: stationarity conditions of the elastic energy

    def statefun(x: npt.NDArray, theta_0: float, F: float) -> Array:
        theta = x[:-1]
        B = x[-1]
        return energy_grad(theta, B=B, theta_0=theta_0, F=F)

    # define extra_args
    constraint_args = {'theta_0': theta_true[0], 'F': F}
    obj_args = {'theta_true': theta_true}

    def obj(x: npt.NDArray, theta_true: npt.NDArray) -> Array:
        theta_guess = x[:-1]
        B_guess = x[-1]
        return ela.obj_stiffness(theta_guess, B_guess, theta_true)

    prb = optctrl.OptimalControlProblem(objfun=obj,
                                        statefun=statefun,
                                        state_dim=num_elements-1,
                                        nparams=num_elements,
                                        constraint_args=constraint_args,
                                        obj_args=obj_args)

    # initial guess for the bending stiffness
    B_in = 1*np.ones(1, dtype=dt.float_dtype)
    x0 = np.concatenate((theta_in, B_in))
    x = prb.solve(x0=x0)

    print(x[-1])
    # extend solution array with boundary element
    theta = x[:-1]
    theta = np.insert(theta, 0, theta_true[0])

    x, y = reconstruct_xy(theta, h, num_nodes)

    error = np.linalg.norm(x - x_true) + np.linalg.norm(y - y_true)
    assert error <= 2e-2

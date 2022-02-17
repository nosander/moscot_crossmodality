from typing import Type, Tuple, Union, Optional

from conftest import Geom_t
import pytest

from ott.core import LinearProblem
from ott.geometry import PointCloud
from ott.core.sinkhorn import sinkhorn
from ott.core.sinkhorn_lr import LRSinkhorn
from ott.core.gromov_wasserstein import gromov_wasserstein
import numpy as np
import jax.numpy as jnp

from moscot.backends.ott import GWSolver, FGWSolver, SinkhornSolver
from moscot.solvers._output import BaseSolverOutput
from moscot.backends.ott._output import GWOutput, SinkhornOutput, LRSinkhornOutput
from moscot.solvers._base_solver import BaseSolver

_RTOL = 1e-6
_ATOL = 1e-6


class TestSinkhorn:
    @pytest.mark.parametrize("jit", [False, True])
    @pytest.mark.parametrize("eps", [None, 1e-2, 1e-1])
    def test_matches_ott(self, x: Geom_t, eps: Optional[float], jit: bool):
        gt = sinkhorn(PointCloud(x, epsilon=eps), jit=jit)
        pred = SinkhornSolver(jit=jit)(x, x, eps=eps)

        assert isinstance(pred, SinkhornOutput)
        np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)

    @pytest.mark.parametrize("rank", [5, 10])
    def test_rank(self, y: Geom_t, rank: Optional[int]):
        eps = 1e-2
        lr_sinkhorn = LRSinkhorn(rank=rank)
        problem = LinearProblem(PointCloud(y, y, epsilon=eps))

        gt = lr_sinkhorn(problem)
        pred = SinkhornSolver(rank=rank)(y, y, eps=eps)

        assert isinstance(pred, LRSinkhornOutput)
        np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)

    @pytest.mark.parametrize("inner_iterations", [1, 10])
    def test_rank_in_call(self, x: Geom_t, inner_iterations: int):
        eps = 1e-2

        solver = SinkhornSolver(inner_iterations=inner_iterations)
        assert not solver.is_low_rank

        for rank in (7, 15):
            lr_sinkhorn = LRSinkhorn(rank=rank, inner_iterations=inner_iterations)
            problem = LinearProblem(PointCloud(x, x, epsilon=eps))

            gt = lr_sinkhorn(problem)
            pred = solver(x, x, eps=eps, rank=rank)

            assert isinstance(pred, LRSinkhornOutput)
            assert solver.rank == rank
            np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)


class TestGW:
    @pytest.mark.parametrize("jit", [False, True])
    @pytest.mark.parametrize("eps", [None, 1e-2, 1e-1])
    def test_matches_ott(self, x: Geom_t, y: Geom_t, eps: Optional[float], jit: bool):
        gt = gromov_wasserstein(PointCloud(x, epsilon=eps), PointCloud(y, epsilon=eps))
        pred = GWSolver()(x, y, eps=eps)

        assert isinstance(pred, GWOutput)
        np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)


class TestFGW:
    @pytest.mark.parametrize("alpha", [0.25, 0.75])
    @pytest.mark.parametrize("eps", [None, 1e-2, 1e-1])
    def test_matches_ott(self, x: Geom_t, y: Geom_t, xy: Geom_t, eps: Optional[float], alpha: float):
        xx, yy = xy

        gt = gromov_wasserstein(
            geom_xx=PointCloud(x, epsilon=eps),
            geom_yy=PointCloud(y, epsilon=eps),
            geom_xy=PointCloud(xx, yy, epsilon=eps),
            fused_penalty=FGWSolver._alpha_to_fused_penalty(alpha),
        )
        pred = FGWSolver()(x, y, xx=xx, yy=yy, alpha=alpha, eps=eps)

        assert isinstance(pred, GWOutput)
        np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)

    def test_alpha_in_call(self, x: Geom_t, y: Geom_t, xy: Geom_t):
        eps = 1e-1
        xx, yy = xy

        solver = FGWSolver()

        for alpha in (0.1, 0.9):
            gt = gromov_wasserstein(
                geom_xx=PointCloud(x, epsilon=eps),
                geom_yy=PointCloud(y, epsilon=eps),
                geom_xy=PointCloud(xx, yy, epsilon=eps),
                fused_penalty=FGWSolver._alpha_to_fused_penalty(alpha),
            )
            pred = solver(x, y, xx=xx, yy=yy, alpha=alpha, eps=eps)

            assert isinstance(pred, GWOutput)
            np.testing.assert_allclose(gt.matrix, pred.transport_matrix, rtol=_RTOL, atol=_ATOL)


class TestSolverOutput:
    def test_properties(self, x: Geom_t, y: Geom_t):
        solver = SinkhornSolver()

        out = solver(x, y, eps=1e-1)
        a, b = out.a, out.b

        assert isinstance(a, jnp.ndarray)
        assert a.shape == (out.shape[0],)
        assert isinstance(b, jnp.ndarray)
        assert b.shape == (out.shape[1],)

        assert isinstance(out.converged, bool)
        assert isinstance(out.cost, float)
        assert out.cost >= 0
        assert out.shape == (x.shape[0], y.shape[0])

    @pytest.mark.parametrize("batched", [False, True])
    @pytest.mark.parametrize("solver_t", [SinkhornSolver, 5])
    def test_push(
        self,
        x: Geom_t,
        y: Geom_t,
        ab: Tuple[np.ndarray, np.ndarray],
        solver_t: Union[int, Type[BaseSolver]],
        batched: bool,
    ):
        a, ndim = (ab[0], ab[0].shape[1]) if batched else (ab[0][:, 0], None)
        rank = solver_t if isinstance(solver_t, int) else None
        solver = SinkhornSolver(rank=rank)

        out = solver(x, y)
        p = out.push(a, scale_by_marginals=False)

        assert isinstance(out, BaseSolverOutput)
        assert isinstance(p, jnp.ndarray)
        if batched:
            assert p.shape == (out.shape[1], ndim)
        else:
            assert p.shape == (out.shape[1],)

    @pytest.mark.parametrize("batched", [False, True])
    @pytest.mark.parametrize("solver_t", [GWSolver, FGWSolver])
    def test_pull(
        self,
        x: Geom_t,
        y: Geom_t,
        xy: Geom_t,
        ab: Tuple[np.ndarray, np.ndarray],
        solver_t: Type[BaseSolver],
        batched: bool,
    ):
        b, ndim = (ab[1], ab[1].shape[1]) if batched else (ab[1][:, 0], None)
        xx, yy = xy
        solver = solver_t()

        out = solver(x, y, xx=xx, yy=yy)
        p = out.pull(b, scale_by_marginals=False)

        assert isinstance(out, BaseSolverOutput)
        assert isinstance(p, jnp.ndarray)
        if batched:
            assert p.shape == (out.shape[0], ndim)
        else:
            assert p.shape == (out.shape[0],)

    @pytest.mark.parametrize("batched", [False, True])
    @pytest.mark.parametrize("forward", [False, True])
    def test_scale_by_marginals(self, x: Geom_t, ab: Tuple[np.ndarray, np.ndarray], forward: bool, batched: bool):
        solver = SinkhornSolver()
        z = ab[0] if batched else ab[0][:, 0]

        out = solver(x)
        p = (out.push if forward else out.pull)(z, scale_by_marginals=True)

        if batched:
            np.testing.assert_allclose(p.sum(axis=0), z.sum(axis=0))
        else:
            np.testing.assert_allclose(p.sum(), z.sum())

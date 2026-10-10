import functools
import logging
from scipy.optimize import minimize as _ORIGINAL_MINIMIZE

logger = logging.getLogger("goangel.penaltyblog_patch")

_NO_CONSTRAINT_METHODS = frozenset({"Powell", "Nelder-Mead", "CG", "BFGS"})
_NO_BOUNDS_METHODS = frozenset({"Nelder-Mead", "CG", "BFGS"})

_PATCH_APPLIED = False


def _patched_minimize(
    fun, x0, args=(), method=None, jac=None, hess=None, hessp=None,
    bounds=None, constraints=(), tol=None, callback=None, options=None,
):
    if method is None:
        method = "SLSQP"

    if method in _NO_CONSTRAINT_METHODS:
        if constraints:
            logger.debug("Penaltyblog patch : %s ne supporte pas les contraintes → retirées", method)
        constraints = ()

    if method in _NO_BOUNDS_METHODS:
        if bounds:
            logger.debug("Penaltyblog patch : %s ne supporte pas les bounds → retirés", method)
        bounds = None

    return _ORIGINAL_MINIMIZE(
        fun=fun, x0=x0, args=args, method=method, jac=jac,
        hess=hess, hessp=hessp, bounds=bounds, constraints=constraints,
        tol=tol, callback=callback, options=options,
    )


def apply_patch() -> bool:
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return True
    import scipy.optimize
    scipy.optimize.minimize = _patched_minimize
    _PATCH_APPLIED = True
    logger.info("✅ penaltyblog_method_patch appliqué")
    return True

r"""
This module contains all the equilibrium calculations according to the explained by [1]_ and [2]_. It solves the
constrained optimization problem:

.. math::
    \min\,\overline{G} = \sum_{i = 1}^{np} \sum_{j = 1}^{nc} n_{ij} \ln{f_{ij}(\mathbf{x}_{i})}

subject to

.. math::
    0 \leq n_{ij} \leq n_{feed}

where np and nc means number of phases and number of components, respectively.

Following [2]_, the problem's decision variable is changed for a proper choice which automatically solves material
balance. To do so, a :math:`\beta` is introduced as decision variable such that

.. math::
    n_{1j} = \beta_{1j} z_j F, \qquad j = 1, 2, \ldots, nc

    n_{kj} = \beta_{kj} \left(z_j F - \sum_{i = 1}^{k - 1} n_{ij}\right), \qquad k = 2, 3, \ldots, np - 1, \quad
    j = 1, 2, \ldots, nc

    n_{kj} = z_j F - \sum_{i = 1}^{k - 1} n_{ij}, \qquad k = np, j = 1, 2, \ldots, nc

where :math:`F` denotes the feed rate, which will be referred here as the molar base for calculations and :math:`z` is
the feed (or overall) composition. Given :math:`\beta` after the minimization procedure, the number of moles of each
component in each phase is obtained by the formulas provided above. With the number of moles, phase molar fractions and
component molar fractions are then calculated as

* Phase fractions (:math:`F_i`, for a phase :math:`i`):

    .. math::
        F_i = \dfrac{\sum_{j = 1}^{nc} n_{ij}}{F}, \qquad i = 1, 2, \ldots, np

* Component molar fractions:

    .. math::
        X \equiv x_ij =  \dfrac{n_{ij}}{\sum_{l = 1}^{nc} x_{il}}, \qquad i = 1, 2, \ldots, np,
        \quad j = 1, 2, \ldots, nc

References
------------

.. [1] Nichita, D. V., Gomez, S., and Luna, E. (2002). Multiphase equilibria calculation by direct minimization of Gibbs
    free energy with a global optimization method. Computers & chemical engineering, 26(12), 1703-1724.

.. [2] Srinivas, M., and Rangaiah, G. P. (2007). Differential evolution with tabu list for global optimization and its
    application to phase equilibrium and parameter estimation problems. Industrial & engineering chemistry research,
    46(10), 3410-3421.

.. module:: equilibrium
   :platform: Unix, Windows and Mac
   :synopsis: Equilibrium calculations (compositions and phase distributions).
.. moduleauthor:: Diego T. Volpatto <dtvolpatto@gmail.com>
"""
import attr
import numpy as np

from scipy.optimize import differential_evolution as de


@attr.s(auto_attribs=True)
class ResultEquilibrium:
    """
    Class for storage the results from equilibrium calculations.

    Members
    ----------

    :ivar numpy.ndarray F:
        Phase molar fractions.

    :ivar numpy.ndarray X:
        Component molar fractions in each phase.

    :ivar float reduced_gibbs_free_energy:
        Reduced Gibbs free energy minimum.

    :ivar int number_of_phases:
        Number of present phases.

    :ivar str status:
        Status of succeed or failure according to the outcome of phase equilibrium calculation.
    """
    F: np.ndarray
    X: np.ndarray
    reduced_gibbs_free_energy: float
    number_of_phases: int
    status: str


def calculate_equilibrium(model, P, T, z, number_of_trial_phases=3, compare_trial_phases=False, molar_base=1.0,
    strategy='best1bin', recombination=0.3, mutation=0.6, tol=1e-5, seed=np.random.RandomState(), workers=1,
    monitor=False, polish=True):
    """
    Given a mixture modeled by an EoS at a known PT-conditions, calculate the thermodynamical equilibrium.

    Parameters
    ----------

    :param model:
        The thermodynamical model.

    :param float P:
        Pressure in Pa.

    :param float T:
        Temperature in K.

    :param numpy.ndarray z:
        Mixture overall composition.

    :param int number_of_trial_phases:
        Number of phases which will be used in the calculations.

    :param bool compare_trial_phases:
        Calculate equilibria from 2 up to the number of trial phases and compare the reduced Gibbs free energy to
        decide which phase is true number of phases in equilibrium.

    :param float molar_base:
        Molar feed rate or molar base.

    :param str strategy:
        The differential evolution strategy to use. Should be one of: - 'best1bin' - 'best1exp' - 'rand1exp' -
        'randtobest1exp' - 'currenttobest1exp' - 'best2exp' - 'rand2exp' - 'randtobest1bin' - 'currenttobest1bin' -
        'best2bin' - 'rand2bin' - 'rand1bin' The default is 'best1bin'.

    :param float recombination:
        The recombination constant, should be in the range [0, 1]. In the literature this is also known as the crossover
        probability, being denoted by CR. Increasing this value allows a larger number of mutants to progress into the
        next generation, but at the risk of population stability.

    :param float mutation:
        The mutation constant. In the literature this is also known as differential weight, being denoted by F. If
        specified as a float it should be in the range [0, 2].

    :param float tol:
        Relative tolerance for convergence, the solving stops when `np.std(pop) = atol + tol * np.abs(np.mean(population_energies))`,
        where and `atol` and `tol` are the absolute and relative tolerance respectively.

    :param int|numpy.random.RandomState seed:
        If `seed` is not specified the `np.RandomState` singleton is used. If `seed` is an int, a new
        `np.random.RandomState` instance is used, seeded with seed. If `seed` is already a `np.random.RandomState instance`,
        then that `np.random.RandomState` instance is used. Specify `seed` for repeatable minimizations.

    :param int workers:
        If `workers` is an int the population is subdivided into `workers` sections and evaluated in parallel
        (uses `multiprocessing.Pool`). Supply -1 to use all available CPU cores. Alternatively supply a map-like
        callable, such as `multiprocessing.Pool.map` for evaluating the population in parallel. This evaluation is
        carried out as `workers(func, iterable)`.

    :param bool monitor:
        Display status messages during optimization iterations.

    :param polish:
        If True (default), then `scipy.optimize.minimize` with the `L-BFGS-B` method is used to polish the best
        population member at the end, which can improve the minimization slightly.

    :return:
        The equilibrium result, providing the phase molar fractions, compositions in each phase and number of
        phases.
    :rtype: ResultEquilibrium
    """
    if number_of_trial_phases <= 1:
        raise ValueError("Invalid number of trial phases: input must be equal or greater than two trial phases.")
    if number_of_trial_phases > 4:
        raise ValueError("Number of trial phases is too large. The limit is four trial phases.")
    if not 0 < recombination <= 1:
        raise ValueError('Recombination must be a value between 0 and 1.')
    if type(mutation) == tuple:
        mutation_dithering_array = np.array(mutation)
        if len(mutation) > 2:
            raise ValueError('Mutation can be a tuple with two numbers, not more.')
        if mutation_dithering_array.min() < 0 or mutation_dithering_array.max() > 2:
            raise ValueError('Mutation must be floats between 0 and 2.')
        elif mutation_dithering_array.min() == mutation_dithering_array.max():
            raise ValueError("Values for mutation dithering can't be equal.")
    else:
        if type(mutation) != int and type(mutation) != float:
            raise TypeError('When mutation is provided as a single number, it must be a float or an int.')
        if not 0 < mutation < 2:
            raise ValueError('Mutation must be a number between 0 and 2.')
    if tol < 0:
        raise ValueError('Tolerance must be a positive float.')

    number_of_components = model.number_of_components
    number_of_phases = number_of_trial_phases

    if number_of_trial_phases == 2 or not compare_trial_phases:
        number_of_decision_variables = number_of_components * (number_of_trial_phases - 1)
        search_space = [(0, 1)] * number_of_decision_variables

        population_size = _define_differential_evolution_population_size(number_of_decision_variables)

        result = de(
            _calculate_gibbs_free_energy_reduced,
            bounds=search_space,
            args=[number_of_components, number_of_trial_phases, model, P, T, z, molar_base],
            strategy=strategy,
            popsize=population_size,
            recombination=recombination,
            mutation=mutation,
            tol=tol,
            disp=monitor,
            polish=polish,
            seed=seed,
            workers=workers
        )

        reduced_gibbs_free_energy = result.fun
        beta_solution_vector = result.x

    else:
        previous_reduced_gibbs_energy = np.inf
        for current_number_of_trial_phase in range(2, number_of_trial_phases + 1):
            number_of_decision_variables = number_of_components * (current_number_of_trial_phase - 1)
            search_space = [(0, 1)] * number_of_decision_variables

            population_size = _define_differential_evolution_population_size(number_of_decision_variables)

            trial_result = de(
                _calculate_gibbs_free_energy_reduced,
                bounds=search_space,
                args=[number_of_components, current_number_of_trial_phase, model, P, T, z, molar_base],
                strategy=strategy,
                popsize=population_size,
                recombination=recombination,
                mutation=mutation,
                tol=tol,
                disp=monitor,
                polish=polish,
                seed=seed,
                workers=workers
            )

            beta_trial_solution_vector = trial_result.x
            current_reduced_gibbs_free_energy = trial_result.fun
            beta_trial_solution = _transform_vector_data_in_matrix(
                beta_trial_solution_vector,
                number_of_components,
                current_number_of_trial_phase - 1
            )
            n_ij_trial_solution = _calculate_components_number_of_moles_from_beta(beta_trial_solution, z, molar_base)
            x_ij_trial_solution = _normalize_phase_molar_amount_to_fractions(
                n_ij_trial_solution,
                current_number_of_trial_phase
            )
            is_trial_phase_nonphysical = _check_phase_equilibrium_break_condition(
                x_ij_trial_solution,
                previous_reduced_gibbs_energy,
                current_reduced_gibbs_free_energy
            )
            if is_trial_phase_nonphysical and previous_reduced_gibbs_energy == np.inf:
                return ResultEquilibrium(
                    F=np.nan,
                    X=np.nan,
                    reduced_gibbs_free_energy=previous_reduced_gibbs_energy,
                    number_of_phases=1,
                    status='failure'
                )
            elif is_trial_phase_nonphysical:
                break
            else:
                reduced_gibbs_free_energy = current_reduced_gibbs_free_energy
                beta_solution_vector = trial_result.x
                number_of_phases = current_number_of_trial_phase
                previous_reduced_gibbs_energy = current_reduced_gibbs_free_energy

    beta_solution = _transform_vector_data_in_matrix(
        beta_solution_vector,
        number_of_components,
        number_of_phases - 1
    )
    n_ij_solution = _calculate_components_number_of_moles_from_beta(beta_solution, z, molar_base)
    x_ij_solution = _normalize_phase_molar_amount_to_fractions(
        n_ij_solution,
        number_of_phases
    )
    phase_fractions = _calculate_phase_molar_fractions(n_ij_solution, molar_base)

    return ResultEquilibrium(
        F=phase_fractions,
        X=x_ij_solution,
        reduced_gibbs_free_energy=reduced_gibbs_free_energy,
        number_of_phases=number_of_phases,
        status='succeed'
    )


def _calculate_gibbs_free_energy_reduced(
    beta_vector, number_of_components, number_of_phases, model, P, T, z, molar_base=1
):
    """
    Calculates the reduced Gibbs free energy. This function is used as objective function in the minimization procedure
    for equilibrium calculations.

    Parameters
    ----------

    :param numpy.ndarray N:
        TODO: update this argument
        Vector ordered component molar amount for each component, arranged in terms of phases. This array must
        be indexed as N[number_of_phases, number_of_components].

    :param int number_of_components:
        Number of components in the mixture.

    :param int number_of_phases:
        Number of trial phases.

    :param model:
        Equation of State or model.

    :param float P:
        Pressure value.

    :param float T:
        Temperature value.

    :param numpy.ndarray z:
        Mixture overall composition.

    :return:
        The evaluation of reduced Gibbs free energy.
    :rtype: float
    """
    if beta_vector.size != (number_of_phases - 1) * number_of_components:
        raise ValueError('Unexpected amount of storage for amount of mols in each phase.')

    beta = _transform_vector_data_in_matrix(beta_vector, number_of_components, number_of_phases - 1)
    n_ij = _calculate_components_number_of_moles_from_beta(beta, z, molar_base)
    x_ij = _normalize_phase_molar_amount_to_fractions(n_ij, number_of_phases)
    fugacities_matrix = _assemble_fugacity_matrix(x_ij, number_of_phases, model, P, T)
    ln_f_matrix = np.log(fugacities_matrix)

    reduced_gibbs_free_energy = np.tensordot(n_ij, ln_f_matrix)

    return reduced_gibbs_free_energy


def _transform_vector_data_in_matrix(N, number_of_components, number_of_phases):
    """
    Given a vector N containing ordered component molar amount for each component, arranged in terms of phases,
    return a matrix where its lines represents phases and columns are the components. In more details,
    N = (n_1, n_2, ..., n_np)^T, where n_j here is the molar composition vector for each component in the phase j.

    Parameters
    ----------

    :param numpy.ndarray N:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param int number_of_components:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param int number_of_phases:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :return:
        A matrix where its lines represents phases and columns are the components.
    :rtype: numpy.ndarray
    """
    n_ij = N.reshape((number_of_phases, number_of_components))
    return n_ij


def _assemble_fugacity_matrix(X, number_of_phases, model, P, T):
    """
    Assembles the fugacity matrix f_ij.

    Parameters
    ----------

    :param numpy.ndarray X:
        Vector ordered component molar fraction for each component, arranged in terms of phases. This array must
        be indexed as X[number_of_phases, number_of_components].

    :param int number_of_phases:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param model:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param float P:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param float T:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :return:
        The matrix f_ij containing all the fugacities for each component in each phase.
    :rtype: numpy.ndarray
    """
    fugacity_matrix = np.zeros(X.shape)
    for phase in range(number_of_phases):  # Unfortunately, this calculation can not be vectorized
        phase_composition = X[phase, :]
        phase_fugacities = model.fugacity(P, T, phase_composition)
        fugacity_matrix[phase, :] = phase_fugacities

    return fugacity_matrix


def _normalize_phase_molar_amount_to_fractions(
    n_ij, number_of_phases, tol=1e-5):
    """
    Converts the component molar amount matrix entries to molar fractions.

    Parameters
    ----------

    :param numpy.ndarray n_ij:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :param int number_of_phases:
        :func:`See here <gibbs.equilibrium.calculate_gibbs_free_energy_reduced>`.

    :return:
        The matrix X_ij containing all the mole fractions for each component in each phase.
    :rtype: numpy.ndarray
    """
    X = np.zeros(n_ij.shape)
    for phase in range(number_of_phases):  # This loop could be optimized
        n_ij_phase_sum = n_ij[phase, :].sum()
        if n_ij_phase_sum > tol:
            phase_composition = n_ij[phase, :] / n_ij_phase_sum
            X[phase, :] = phase_composition
        else:
            X[phase, :] = np.zeros(n_ij.shape[1])

    return X


def _calculate_components_number_of_moles_from_beta(beta, z, molar_base=1.0):
    r"""
    Calculate the component number of moles in each phase given a value :math:`\beta`. This calculation is performed
    according to [1]_. Below, a brief description is provided. First, we must solve for the phase 1
    (equation 7 in [1]_), then we calculate number of moles for the next phases using the previous computed number of
    moles (equation 8 in [1]_), then we calculate the number of moles for each component in the last phase, which is
    independent of :math:`\beta`.

    * Equation 7 from [1]_:

    .. math::
        n_{1j} = \beta_{1j} z_j F, \qquad j = 1, 2, \ldots, nc

    * Equation 8 from [1]_:

    .. math::

        n_{kj} = \beta_{kj} \left(z_j F - \sum_{i = 1}^{k - 1} n_{ij}\right), \qquad k = 2, 3, \ldots, np - 1, \quad
        j = 1, 2, \ldots, nc

    * Equation 9 from [1]_:

    .. math::

        n_{kj} = z_j F - \sum_{i = 1}^{k - 1} n_{ij}, \qquad k = np, j = 1, 2, \ldots, nc

    References
    ------------

    .. [1] Srinivas, M., and Rangaiah, G. P. (2007). Differential evolution with tabu list for global optimization and its
        application to phase equilibrium and parameter estimation problems. Industrial & engineering chemistry research,
        46(10), 3410-3421.

    Parameters
    ----------

    :param numpy.ndarray beta:
        The decision variable written as matrix.

    :param numpy.ndarray z:
        Mixture overall composition.

    :param float molar_base:
        Molar feed rate or molar base.

    :return:
        The number of moles of each component in each phase.
    :rtype: numpy.ndarray
    """
    number_of_phases = beta.shape[0] + 1
    number_of_components = beta.shape[1]
    N = np.zeros((number_of_phases, number_of_components))

    # Equation (7)
    N[0, :] = beta[0, :] * z * molar_base

    # The following loops probably have a more optimized way. Here, a lazy fashion is implemented.
    # Equation (8)
    for phase in range(1, number_of_phases - 1):
        for i in range(number_of_components):
            N[phase, i] = beta[phase, i] * (z[i] * molar_base - N[:phase, i].sum())

    # Equation (9)
    for i in range(number_of_components):
        N[-1, i] = z[i] * molar_base - N[:(number_of_phases - 1), i].sum()

    return N


def _calculate_phase_molar_fractions(N, molar_base=1.0):
    """
    Given the number of moles of each component in each phase, calculate the molar phase fractions.

    Parameters
    ----------

    :param numpy.ndarray N:
        A matrix containing the number of moles of each component in each phase.

    :param float molar_base:
        Molar feed rate or molar base.

    :return:
        Molar phase fractions.
    :rtype: numpy.ndarray
    """
    number_of_phases = N.shape[0]
    phase_fractions = np.zeros(number_of_phases)
    for phase in range(number_of_phases):
        phase_fractions[phase] = N[phase, :].sum() / molar_base

    return phase_fractions


def _check_phase_equilibrium_break_condition(X, previous_reduced_gibbs_free_energy, current_reduced_gibbs_free_energy, rtol=1e-2):
    number_of_phases = X.shape[0]

    is_nonphysical_phase = False

    for fixed_phase in range(number_of_phases):
        fixed_phase_composition = X[fixed_phase, :]
        for searching_phase in range(number_of_phases):
            if searching_phase == fixed_phase:
                continue

            searching_phase_composition = X[searching_phase, :]
            if np.allclose(fixed_phase_composition, searching_phase_composition, rtol=rtol):
                is_nonphysical_phase = True
                break

        if is_nonphysical_phase:
            break

    if not is_nonphysical_phase and current_reduced_gibbs_free_energy > previous_reduced_gibbs_free_energy:
        is_nonphysical_phase = True

    return is_nonphysical_phase


def _define_differential_evolution_population_size(
        number_of_decision_variables,
        population_size_for_each_variable=15,
        total_population_size_limit=100
):
    population_size = population_size_for_each_variable * number_of_decision_variables
    if population_size > total_population_size_limit:
        population_size = total_population_size_limit

    return population_size

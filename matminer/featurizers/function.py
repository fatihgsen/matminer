from __future__ import division

"""
This module includes code to featurize data based on
common mathematical expressions used as features.

Note that the approach here has opted for a sympy-based
parsing of string expressions, rather than explicit
python functions.  The primary reason this has been
done is to provide for better support for book-keeping
(e. g. with feature labels), substitution, and elimination
of symbolic reduncancy, which sympy is well-suited for.
"""

import numpy as np
from sympy.parsing.sympy_parser import parse_expr
import sympy as sp
import itertools
from six import string_types

from collections import OrderedDict

from matminer.featurizers.base import BaseFeaturizer


# Default expressions to include in function featurizer
default_exps = ["x", "1/x", "sqrt(x)", "1/sqrt(x)", "x**2", "x**-2", "x**3",
                "x**-3", "log(x)", "1/log(x)", "exp(x)", "exp(-x)"]


# TODO: feature labels might be latexified
# TODO: parallelization of substitution, think this might be
# TODO:     unnecessary because featurization already substituted
# TODO:     over rows
class FunctionFeaturizer(BaseFeaturizer):
    """
    This class featurizes a dataframe according to a set
    of expressions representing functions to apply to
    existing features
    """

    def __init__(self, expressions=None, multi_feature_depth=1,
                 combo_function=None):

        """
        Args:
            expressions ([str]): list of sympy-parseable expressions
                representing a function of a single variable x, e. g.
                ["1 / x", "x ** 2"], defaults to the list above
            multi_feature_depth (int): how many features to include if using
                multiple fields for functionalization, e. g. 2 will
                include pairwise combined features
            combo_function (function): function to combine multi-features,
                defaults to np.prod (i.e. cumulative product of expressions),
                note that a combo function must cleanly process sympy
                expressions
        """
        self.expressions = expressions or default_exps
        self.multi_feature_depth = multi_feature_depth
        self.combo_function = combo_function or np.prod

        # Generate lists of sympy expressions keyed by number of features
        self.exp_dict = OrderedDict(
            [(n, generate_expressions_combinations(self.expressions, n))
             for n in range(1, multi_feature_depth+1)])

    def featurize_dataframe(self, df, col_id, latexify_labels=False,
                            **kwargs):
        """
        Custom featurize class so we can rename columns

        Args:
            df (DataFrame): dataframe containing input data
            col_id (str or list of str): column label containing objects to
                featurize. Can be multiple labels if the featurize function
                requires multiple inputs
            latexify_labels (bool): whether or not to latexify feature labels
            **kwargs (kwargs): kwargs to BaseFeaturizer.featurize_dataframe,
                including featurizer kwargs

        Returns:
            updated DataFrame

        """
        if isinstance(col_id, string_types):
            col_id = [col_id]
        # Construct label properties
        label_props = {"col_id": col_id, "latexify_labels": latexify_labels}
        return super(FunctionFeaturizer, self).featurize_dataframe(
            df, col_id, label_props=label_props, **kwargs)


    def featurize(self, *args, postprocess=float):
        """
        Main featurizer function, essentially iterates over all
        of the functions in self.function_list to generate
        features for each argument.

        Args:
            *args: list of numbers to generate functional output
                features
            postprocess (function): postprocessing function, primarily
                used to recast data that's been run through the sympy
                expression, e. g. float, complex, etc.

        Returns:
            list of functional outputs corresponding to input args
        """
        return list(self._exp_iter(*args, postprocess=postprocess))


    def feature_labels(self, col_id, latexify_labels=False):
        """

        Args:
            col_id ([str]): column names
            latexify_labels (bool): whether to latexify labels
                in output feature labels

        Returns:
            Set of feature labels corresponding to expressions
                substituted with column names

        """
        postprocess = sp.latex if latexify_labels else str
        return list(self._exp_iter(*col_id, postprocess=postprocess))


    def _exp_iter(self, *args, postprocess=None):
        """
        Generates an iterator for substitution of a set
        of args into the set of expression corresponding
        to the featurizer, intended primarily to remove
        replicated code in featurize and feature labels

        Args:
            *args: args to loop over combinations and substitions for
            postprocess (function): postprocessing function, e. g.
                to cast to another type, float, str

        Returns:
            iterator for all substituted expressions

        """
        postprocess = postprocess or (lambda x: x)
        for n in range(1, self.multi_feature_depth + 1):
            for arg_combo in itertools.combinations(args, n):
                subs_dict = {"x{}".format(m) : arg
                             for m, arg in enumerate(arg_combo)}
                for exp in self.exp_dict[n]:
                    # TODO: this is a workaround for the problem
                    # TODO: postprocessing functional incompatility,
                    # TODO: e. g. sqrt(-1), 1 / 0
                    try:
                        yield postprocess(exp.subs(subs_dict))
                    except (TypeError, ValueError):
                        yield None



    def citations(self):
        return ["@article{Ramprasad2017,"
                "author = {Ramprasad, Rampi and Batra, Rohit and Pilania, Ghanshyam"
                          "and Mannodi-Kanakkithodi, Arun and Kim, Chiho,"
                "doi = {10.1038/s41524-017-0056-5},"
                "journal = {npj Computational Materials},"
                "title = {Machine learning in materials informatics: recent applications and prospects},"
                "volume = {3},number={1}, pages={54}, year={2017}}"]

    def implementors(self):
        return ['Joseph Montoya']



#TODO: Have this filter expressions that evaluate to things without vars,
#TODO:      # e. g. floats/ints
def generate_expressions_combinations(expressions, combo_depth=2,
                                      combo_function=np.prod):
    """
    This function takes a list of strings representing functions
    of x, converts them to sympy expressions, and combines
    them according to the combo_depth parameter.  Also filters
    resultant expressions for any redundant ones determined
    by sympy expression equivalence.

    Args:
        expressions (strings): all of the sympy-parseable strings
            to be converted to expressions and combined, e. g.
            ["1 / x", "x ** 2"], must be functions of x
        combo_depth (int): the number of independent variables to consider
        combo_function (function): the function which combines the
            the respective expressions provided, defaults to np.prod,
            i. e. the cumulative product of the expressions

    Returns:
        list of unique non-trivial expressions for featurization
            of inputs
    """
    # Convert to array for simpler subsitution
    exp_array = sp.Array([parse_expr(exp) for exp in expressions])

    # Generate all of the combinations
    combo_exps = []
    all_arrays = [exp_array.subs({"x": "x{}".format(n)})
                  for n in range(combo_depth)]
    # Get all sets of expressions
    for exp_set in itertools.product(*all_arrays):
        # Get all permutations of each set
        for exp_perm in itertools.permutations(exp_set):
            combo_exps.append(combo_function(exp_perm))

    # Filter for unique combinations, also remove identity
    unique_exps = list(set(combo_exps) - set([parse_expr('x0')]t ))
    return unique_exps
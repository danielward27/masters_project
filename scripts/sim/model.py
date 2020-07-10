
"""
Script contains class that describes models of Scottish wildcat evolution. Scottish wildcats have
undergone extensive hybridisation with domestic cats. This model consists of a backwards in time coalescent simulation
with msprime (https://msprime.readthedocs.io/en/stable/)to estimate ancestral variation (ancvar) in wildcat and
domestic cats prior to hybridisation. A 500 generation forwards Wright-Fisher model can then be run from these two
ancestral populations using SLiM (https://messerlab.org/slim/), in which hybridisation occurs
between the two populations and a captive wildcat population is established.
"""

import msprime
import numpy as np
import pandas as pd
import pyslim
from subprocess import run
import os
from dataclasses import dataclass


@dataclass
class SeqFeatures:
    """Contains the fixed parameters in the model relating to the features of the sequence simulated"""
    length: int         # Length of sequence to simulate in base pairs.
    recombination_rate: float = 2e-8  # Recombination rate per base pair.
    mutation_rate: float = 6.7e-8     # Mutation rate per base pair.


class WildcatSimulation:
    """Class outlines the model and parameters. Recommended that the directory "../../output/" is set up so
    the default output paths work.

    Attributes:
        pop_size_domestic_1, pop_size_wild_1, pop_size_captive (int): Number of diploid domestic, wild or captive cats.
        seq_features (object): instance of SeqFeatures dataclass
        random_seed (int): Random seed.
        suffix (bool): Adds _{random_seed} to filenames to avoid overwriting files.
        _decap_trees_filename (str): filename of the decapitated tree sequence outputted by SLiM.
    """

    def __init__(self, seq_features, random_seed=None, suffix=True):
        self.seq_features = seq_features
        self.random_seed = random_seed
        self.suffix = suffix
        self._decap_trees_filename = None
        self._pop_size_domestic_1 = None
        self._pop_size_wild_1 = None
        self._pop_size_captive = None

    def add_suffix(self, filename):
        """Helper function adds _{random_seed} before the last dot in certain filenames.
        Avoids clashes in filenames for example when running things in parallel."""
        dot_index = filename.rfind('.')
        filename = "{}_{}{}".format(filename[:dot_index], self.random_seed, filename[dot_index:])
        return filename

    def slim_command(self, pop_size_domestic_1, pop_size_wild_1, pop_size_captive,
                     migration_length_1, migration_rate_1, captive_time,
                     decap_trees_filename="../output/decap.trees",
                     slim_script_filename='slim_model.slim',
                     template_filename='slim_command_template.txt'):
        """Uses a template slim command text file and replaces placeholders
        with parameter values to get a runnable command. Returns str."""

        self._pop_size_domestic_1 = pop_size_domestic_1
        self._pop_size_wild_1 = pop_size_wild_1
        self._pop_size_captive = pop_size_captive

        if self.suffix:
            self._decap_trees_filename = self.add_suffix(decap_trees_filename)
        else:
            self._decap_trees_filename = decap_trees_filename

        replacements_dict = {
            'p_pop_size_domestic_1': str(self._pop_size_domestic_1),  # Placeholders prefixed with p_ in template
            'p_pop_size_wild_1': str(self._pop_size_wild_1),
            'p_pop_size_captive': str(self._pop_size_captive),
            'p_length': str(self.seq_features.length),
            'p_recombination_rate': str(self.seq_features.recombination_rate),
            'p_migration_length_1': str(migration_length_1),
            'p_migration_rate_1': str(migration_rate_1),
            'p_captive_time': str(captive_time),
            'p_random_seed': str(self.random_seed),
            'p_slim_script_filename': slim_script_filename,
            'p_decap_trees_filename': self._decap_trees_filename,
        }

        with open(template_filename) as f:
            command = f.read()
            for placeholder, value in replacements_dict.items():
                if placeholder in command:
                    command = command.replace(placeholder, value)
                else:
                    print('Warning: the the placeholder {} could not be found in template file'.format(placeholder))
        return command

    def run_slim(self, command):
        """Runs SLiM simulation from command line to get the decapitated tree sequence."""
        command_f = self.add_suffix("_temporary_command.txt")

        with open(command_f, 'w') as f:  # Running from file limits 'quoting games' (see SLiM manual pg. 425).
            f.write(command)
        run(['bash', command_f])
        tree_seq = pyslim.load(self._decap_trees_filename)
        os.remove(command_f)  # No need to keep the command file (can always print to standard out)
        os.remove(self._decap_trees_filename)  # We will delete the decapitated trees (don't need them).

        return tree_seq

    @staticmethod
    def demographic_model(pop_size_domestic_2, pop_size_wild_2, div_time, migration_rate_2,
                          migration_length_2, bottleneck_time_wild, bottleneck_strength_wild,
                          bottleneck_time_domestic, bottleneck_strength_domestic):
        """Model for recapitation, including bottlenecks, population size changes and migration.
        Returns list of demographic events sorted in time order. Note that if parameters are drawn from priors this
        could have unexpected consequences on the demography. sim.utils.test_prior() should mitigate this issue."""
        domestic, wild = 0, 1

        migration_time_2 = div_time-migration_length_2

        demographic_events = [
            msprime.PopulationParametersChange(time=bottleneck_time_domestic, initial_size=pop_size_domestic_2,
                                               population_id=domestic),  # pop size change executes "before" bottleneck
            msprime.InstantaneousBottleneck(time=bottleneck_time_domestic, strength=bottleneck_strength_domestic,
                                            population_id=domestic),
            msprime.PopulationParametersChange(time=bottleneck_time_wild, initial_size=pop_size_wild_2,
                                               population_id=wild),
            msprime.InstantaneousBottleneck(time=bottleneck_time_wild, strength=bottleneck_strength_wild,
                                            population_id=wild),
            msprime.MigrationRateChange(time=migration_time_2, rate=migration_rate_2, matrix_index=(domestic, wild)),
            msprime.MigrationRateChange(time=migration_time_2, rate=migration_rate_2, matrix_index=(wild, domestic)),
            msprime.MassMigration(time=div_time, source=domestic, dest=wild, proportion=1)]

        demographic_events.sort(key=lambda event: event.time, reverse=False)  # Ensure time sorted (required by msprime)
        return demographic_events

    def recapitate(self, decap_trees, demographic_events, demography_debugger=False):
        """Recapitates tree sequence under model specified by demographic events. Returns tskit.tree_sequence."""
        population_configurations = [
            msprime.PopulationConfiguration(initial_size=self._pop_size_domestic_1),  # msprime uses diploid Ne
            msprime.PopulationConfiguration(initial_size=self._pop_size_wild_1),
            msprime.PopulationConfiguration(initial_size=self._pop_size_captive)]

        tree_seq = decap_trees.recapitate(recombination_rate=self.seq_features.recombination_rate,
                                          population_configurations=population_configurations,
                                          demographic_events=demographic_events, random_seed=self.random_seed)

        tree_seq = pyslim.SlimTreeSequence(msprime.mutate(tree_seq, rate=self.seq_features.mutation_rate,
                                                          random_seed=self.random_seed))
        tree_seq = tree_seq.simplify()

        if demography_debugger:
            dd = msprime.DemographyDebugger(
                population_configurations=population_configurations,
                demographic_events=demographic_events)
            dd.print_history()

        return tree_seq

    def sample_nodes(self, tree_seq, sample_sizes):
        """Get an initial sample of nodes from the populations that can be used for simplification.
        Sample_sizes provided in order [dom, wild, captive]. Note the node IDs are not consistent after
        simplification, although they can be accessed using the sampled_nodes function in SummaryStatistics class.
        """
        ind_df = individuals_df(tree_seq)
        sample_nodes = []
        for pop_num, samp_size in enumerate(sample_sizes):
            pop_df = ind_df[ind_df["population"] == pop_num]
            pop_sample = pop_df.sample(samp_size, random_state=self.random_seed)
            pop_sample_nodes = pop_sample["node_0"].tolist() + pop_sample["node_1"].tolist()
            sample_nodes.append(pop_sample_nodes)
        return np.array(sample_nodes)


def individuals_df(tree_seq):
    """Returns pd.DataFrame of individuals population and node indices."""
    individuals = tree_seq.individuals_alive_at(0)
    ind_dict = {
        "population": [],
        "node_0": [],
        "node_1": [],
    }
    for individual in individuals:
        ind = tree_seq.individual(individual)
        ind_dict["population"].append(ind.population)
        ind_dict["node_0"].append(ind.nodes[0])
        ind_dict["node_1"].append(ind.nodes[1])

    ind_df = pd.DataFrame(ind_dict)
    return ind_df


def tree_summary(tree_seq):
    """Prints summary of a tree sequence"""
    tree_heights = []
    for tree in tree_seq.trees():
        for root in tree.roots:
            tree_heights.append(tree.time(root))
    print("Number of trees: {}".format(tree_seq.num_trees))
    print("Trees coalesced: {}".format(sum([t.num_roots == 1 for t in tree_seq.trees()])))
    print("Tree heights: max={}, min={}, median={}".format(max(tree_heights), min(tree_heights),
                                                           np.median(tree_heights)))
    print("Number of alive individuals: {}".format(len(tree_seq.individuals_alive_at(0))))
    print("Number of samples: {}".format(tree_seq.num_samples))
    print("Number of populations: {}".format(tree_seq.num_populations))
    print("Number of variants: {}".format(tree_seq.num_mutations))
    print("Sequence length: {}".format(tree_seq.sequence_length))
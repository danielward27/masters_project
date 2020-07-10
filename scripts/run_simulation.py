"""Script runs an instance of the model using ms format to link msprime and slim.
Model structure is specified in classes.py"""

from sim.model import WildcatSimulation, SeqFeatures, tree_summary
import time
import tskit

start_time = time.time()

seq_features = SeqFeatures(length=int(10e6), recombination_rate=1.8e-8, mutation_rate=6e-8)

slim_parameters = {
    'pop_size_domestic_1': 1000,  # Population sizes are diploid.
    'pop_size_wild_1': 1000,
    'pop_size_captive': 100,
    'migration_length_1': 50,   # Generations in SLiM before migration begins
    'migration_rate_1': 0.05,  # Rate of migration from domestic -> wildcats
    'captive_time': 50,          # Time captive population established in SLiM
}

recapitate_parameters = {
    'pop_size_domestic_2': 8000,
    'pop_size_wild_2': 8000,
    'div_time': 40000,                  # Divergence of lybica and silvestris in generations
    'migration_rate_2': 0.1,     # Reciprocal migration rate between lybica and silvestris following divergence
    'migration_length_2': 20000,  # Time that reciprocal migration stops
    'bottleneck_time_wild': 3000,       # Generations ago that continental wildcats came to Britain
    'bottleneck_strength_wild': 10000,  # Time that drives equal coalescence with constant pop sizes and no mutations.
    'bottleneck_time_domestic': 3000,   # Generations ago that continental wildcats came to Britain
    'bottleneck_strength_domestic': 10000,
}

# Run model
sim = WildcatSimulation(seq_features, random_seed=2)
command = sim.slim_command(**slim_parameters)
decap_trees = sim.run_slim(command)
demographic_events = sim.demographic_model(**recapitate_parameters)
tree_seq = sim.recapitate(decap_trees, demographic_events, demography_debugger=True)

# Print out useful bits and bobs
print(tree_summary(tree_seq))
print("Simulation finished in {:.2f} s".format(time.time()-start_time))
print("Command ran:")
print(command)
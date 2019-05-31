"""
This script decomposes a gene set into subsets and evaluates them in order to
identify the subsets with the highest classification potential.
"""
import argparse
import itertools
import numpy as np
import operator
import os
import pandas as pd
import random

import utils



def select_subsets(prev_subsets, genes, n_subsets=50, r=0.5):
	# sort previous subsets by score (descending)
	prev_subsets.sort(key=operator.itemgetter(1), reverse=True)
	prev_subsets = [s[0] for s in prev_subsets]

	# select the highest scoring subsets from prev subsets
	seed_subsets = prev_subsets[0:n_subsets]
	prev_subsets = prev_subsets[n_subsets:]

	# additionally select random subsets from the remaining prev subsets
	n_random = min(int(r * n_subsets), len(prev_subsets))
	seed_subsets += random.sample(prev_subsets, n_random)

	# generate new subsets by augmenting the seed subsets with individual genes
	subsets = []

	for seed_subset in seed_subsets:
		# determine the set of genes not in the seed subset
		extra_genes = list(set(genes) - set(seed_subset))
		
		# generate new subsets by appending each extra gene to seed subset
		subsets += [(seed_subset + [gene]) for gene in extra_genes]

	# remove duplicate sets
	subsets = [sorted(subset) for subset in subsets]
	subsets = [list(s) for s in set(tuple(s) for s in subsets)]

	return subsets



if __name__ == "__main__":
	# parse command-line arguments
	parser = argparse.ArgumentParser(description="Generate and evaluate subsets of a gene set.")
	parser.add_argument("--dataset", help="input dataset (samples x genes)", required=True)
	parser.add_argument("--labels", help="list of sample labels", required=True)
	parser.add_argument("--model-config", help="model configuration file (JSON)", required=True)
	parser.add_argument("--model", help="classifier model to use", default="mlp")
	parser.add_argument("--gene-sets", help="list of curated gene sets")
	parser.add_argument("--random", help="Evaluate random gene sets", action="store_true")
	parser.add_argument("--random-range", help="range of random gene sizes to evaluate", nargs=2, type=int)
	parser.add_argument("--logdir", help="directory where logs are stored", required=True)

	args = parser.parse_args()

	# load input data
	print("loading input dataset...")

	df = utils.load_dataframe(args.dataset)
	df_samples = df.index
	df_genes = df.columns

	labels = utils.load_labels(args.labels)

	print("loaded input dataset (%s genes, %s samples)" % (df.shape[1], df.shape[0]))

	# initialize classifier
	print("initializing classifier...")

	clf = utils.load_classifier(args.model_config, args.model)

	print("initialized %s classifier" % args.model)

	# load gene sets file if it was provided
	if args.gene_sets != None:
		print("loading gene sets...")

		gene_sets = utils.load_gene_sets(args.gene_sets)

		print("loaded %d gene sets" % (len(gene_sets)))

		# remove genes which do not exist in the dataset
		genes = list(set(sum([genes for (name, genes) in gene_sets], [])))
		missing_genes = [g for g in genes if g not in df_genes]

		gene_sets = [(name, [g for g in genes if g in df_genes]) for (name, genes) in gene_sets]

		print("%d / %d (%0.1f%%) genes from gene sets were not found in the input dataset" % (
			len(missing_genes),
			len(genes),
			len(missing_genes) / len(genes) * 100))
	else:
		gene_sets = []

	# generate random gene sets if specified
	if args.random:
		# determine random set sizes from range
		if args.random_range != None:
			print("initializing random set sizes from range...")
			random_sets = range(args.random_range[0], args.random_range[1] + 1)

		# determine random set sizes from gene sets
		elif args.gene_sets != None:
			print("initializing random set sizes from gene sets...")
			random_sets = sorted(set([len(genes) for (name, genes) in gene_sets]))

		# print error and exit
		else:
			print("error: --gene-sets or --random-range must be provided to determine random set sizes")
			sys.exit(1)

		# generate random gene sets
		for n_genes in random_sets:
			name = "random-%d" % n_genes
			genes = random.sample(list(df_genes), n_genes)

			gene_sets.append((name, genes))

	# perform combinatorial analysis on each gene set
	for name, genes in gene_sets:
		print()
		print("decomposing %s..." % name)

		# initialize log directory
		logdir = "%s/%s" % (args.logdir, name)

		os.makedirs(logdir, exist_ok=True)

		# write gene list to a file
		f = open("%s/genes.txt" % logdir, "w")
		f.write("\n".join(genes))
		f.close()

		# perform combinatorial analysis
		n_genes = len(genes)

		for k in range(1, n_genes + 1):
			print("iteration %d" % k)

			print("  generating subsets...")

			# generate all combinations of size k
			if k <= 3 or n_genes - k <= 1:
				subsets = [list(s) for s in itertools.combinations(genes, k)]

			# or select some combinations using a heuristic
			else:
				# load subsets from previous iteration
				logfile = "%s/scores_%03d.txt" % (logdir, k - 1)
				lines = [line.strip() for line in open(logfile, "r")]
				lines = [line.split("\t") for line in lines]

				# generate new subsets of size k from previous subsets
				prev_subsets = [(line[0].split(","), float(line[1])) for line in lines]
				subsets = select_subsets(prev_subsets, genes)

			print("  evaluating %d subsets..." % len(subsets))

			# initialize log file
			logfile = open("%s/scores_%03d.txt" % (logdir, k), "w")

			# evaluate each subset
			for subset in subsets:
				# evaluate subset
				scores = utils.evaluate_gene_set(df, labels, clf, subset)

				# write results to file
				logfile.write("%s\t%0.3f\n" % (",".join(subset), scores[0]))
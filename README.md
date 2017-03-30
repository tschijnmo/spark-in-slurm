# spark-in-slurm
Utility script to start stand-alone Spark cluster inside SLURM jobs


## Introduction

Apache Spark and SLURM are designed with very different deployment models in
mind.  This project aims to help running Spark within a SLURM batch/interactive
job environment.  Different from common Spark deployment schemes, similar to
common conventions in SLURM jobs, here run-time files of Spark are attempted to
be put in the current working directly, rather than some location in the Spark
installation tree.  Also the resources allocated to the job will be attempted
to be used as much as possible.


## Usage

The SLURM job need to be allocated a homogeneous array of compute nodes, with
each process set to use all CPUs on the nodes.  This can be easily achieved by
setting `-N` to the number of nodes and `-c` to the number of physical core on
the nodes.

Within the SLURM job, the script `start-spark-in-slurm.py` can be invoked so
that a stand-alone Spark cluster will be started.  To fine tune the behaviour,
we have the following options,


* `-l/--log-level` The log level for Spark, default to `FATAL`.

* `-f/--parallel-factor` The factor for default Spark parallelism wrt the
  number of CPUs in all workers, default `1`.

* `-a/--cpus-aside` The number of CPUs reserved for Spark and driver, default
  to four CPUs to be conservative.

The output from the script can be passed to bash `eval`, then the
`spark-submit` command can next be used to submit the actual job, possibly with
additional customization.

Before calling this script, the environmental variables `SPARK_HOME`,
`JAVA_HOME`, and `PYTHONPATH` need to be set correctly.  And the Python
interpreter used for the script will also be used for the Spark job.

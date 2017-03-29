# spark-in-slurm
Utility script to start stand-alone Spark cluster inside SLURM jobs

Apache Spark and SLURM are designed with very different deployment models in
mind.  This project aims to help running Spark within a SLURM batch job
environment.

By running the script `start-spark-in-slurm.sh` *within* the current shell, a
stand-alone Spark cluster will be started.  The `spark-submit` command can next
be used to submit the actual job.

Before calling this script, the environmental variables `SPARK_HOME`,
`JAVA_HOME`, and `PYTHONPATH` need to be set correctly.  And the program
`python3` in `PATH` need to point to the Python interpreter intended to be
used.

`SPARK_LOG_LEVEL` can be used to tune the logging level for Spark, by default,
only errors are logged due to performance reasons.

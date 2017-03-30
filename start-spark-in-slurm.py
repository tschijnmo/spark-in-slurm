"""Start stand-alone Spark cluster inside SLURM jobs.
"""

import argparse
import json
import json.decoder
import os
import os.path
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request


class EnvError(Exception):
    """Error in the environment."""
    pass


class JobEnv:
    """The environment for the current job.
    """

    def __init__(self):
        """Initialize the environment."""

        self.spark_home = os.environ.get('SPARK_HOME')
        if self.spark_home is None:
            raise EnvError('SPARK_HOME is not set!')

        self.job_name = os.environ.get('SLURM_JOB_NAME')
        self.job_id = os.environ.get('SLURM_JOB_ID')
        if self.job_name is None or self.job_id is None:
            raise EnvError('Not inside a SLURM job!')

        self.n_tasks = int(os.environ.get('SLURM_NTASKS'))
        n_cpu_per_task = os.environ.get('SLURM_CPUS_PER_TASK')
        if n_cpu_per_task is None:
            n_cpu_per_task = os.cpu_count()
            print((
                      '-c/--cpus-per-task is not explicitly set,'
                      ' assuming {}'
                  ).format(n_cpu_per_task), file=sys.stderr)

        self.python = sys.executable
        self.master_host = platform.node()
        self.n_cpus = self.n_tasks * n_cpu_per_task

        self.master_port = '7077'
        self.master_link = 'spark://{}:{}'.format(
            self.master_host, self.master_port
        )

    def make_dirs(self):
        """Make the directories and set attributes."""

        job_home = 'Spark-{}-{}'.format(self.job_name, self.job_id)
        self.job_home = job_home
        self.conf_dir = os.path.join(job_home, 'conf')
        self.worker_dir = os.path.join(job_home, 'worker')
        self.log_dir = os.path.join(job_home, 'log')

        for i in [self.job_home, self.conf_dir, self.worker_dir, self.log_dir]:
            os.makedirs(i, exist_ok=True)

        self.conf_file = open(
            os.path.join(self.conf_dir), 'spark-defaults.conf'
        )

    def gen_confs(self, parallel_factor, log_level):
        """Generate the configuration files."""

        spark_env = _SPARK_ENV.format(
            log_dir=self.log_dir, worker_dir=self.worker_dir,
            master_host=self.master_host, master_port=self.master_port,
            python=self.python
        )
        with open(os.path.join(self.conf_dir, 'spark-env.sh'), 'w') as fp:
            fp.write(spark_env)

        log_conf = _LOG_CONF.format(log_level=log_level)
        with open(os.path.join(self.conf_dir, 'log4j.properties'), 'w') as fp:
            fp.write(log_conf)

        self._add_conf('spark.app.name', self.job_name)
        self._add_conf('spark.master', self.master_link)
        self._add_conf(
            'spark.default.parallelism',
            int(parallel_factor * self.n_cpus)
        )

    def launch(self):
        """Launch the cluster."""

        with open(os.path.join(self.job_home, 'master.out'), 'w') as fp:
            subprocess.Popen(
                [
                    os.path.join(self.spark_home, 'sbin', 'start-master.sh'),
                    '-h', self.master_host, '-p', self.master_port
                ],
                stdin=subprocess.DEVNULL, stdout=fp, stderr=fp,
                start_new_session=True
            )
        self._wait_master(lambda x: True, 'Launching master')

        with open(os.path.join(self.job_home, 'workers.out'), 'w') as fp:
            subprocess.Popen(
                [
                    'srun', '--export={}'.format(_EXPORT_ENV),
                    os.path.join(self.spark_home, 'sbin', 'start-slave.sh'),
                    self.master_link,
                    '-d', self.worker_dir
                ],
                stdin=subprocess.DEVNULL, stdout=fp, stderr=fp,
                start_new_session=True
            )
        stat = self._wait_master(
            lambda x: len(x['workers']) == self.n_tasks,
            'Launching workers'
        )

        min_mem = min(i['memoryfree'] for i in stat['workers'])
        mem = '{}m'.format(min_mem)

        self._add_conf('spark.driver.memory', mem)
        self._add_conf('spark.executor.memory', mem)

    def _wait_master(self, pred, label, timeout=300):
        """Wait until the JSON status from the master satisfies the predicate.
        """

        begin_time = time.time()

        while time.time() - begin_time < timeout:
            try:
                stat = json.load(urllib.request.urlopen(
                    'http://{}:8080/json'.format(self.master_host)
                ))
            except urllib.error.URLError:
                pass
            except json.decoder.JSONDecodeError:
                pass
            else:
                if pred(stat):
                    break

            time.sleep(1)
        else:
            raise EnvError(label + ' timed out!')

        return stat

    def _add_conf(self, key, val):
        """Add an entry to Spark configuration file."""
        print('{} {}'.format(key, val), file=self.conf_file)
        return

    def __del__(self):
        self.conf_file.close()


_SPARK_ENV = """
export SPARK_LOG_DIR={log_dir}
export SPARK_WORKER_DIR={worker_dir}

export SPARK_MASTER_HOST={master_host}
export SPARK_MASTER_PORT={master_port}

export PYSPARK_PYTHON={python}
export PYSPARK_DRIVER_PYTHON={python}
export SPARK_NO_DAEMONIZE=1
"""

_LOG_CONF = """
log4j.rootCategory={log_level}, console
log4j.appender.console=org.apache.log4j.ConsoleAppender
log4j.appender.console.target=System.err
log4j.appender.console.layout=org.apache.log4j.PatternLayout
log4j.appender.console.layout.ConversionPattern=%d{{yy/MM/dd HH:mm:ss}} %p 
%c{{1}}: %m%n

# Set the default spark-shell log level to WARN. When running the 
spark-shell, the
# log level for this class is used to overwrite the root logger's log level, 
so that
# the user can have different defaults for the shell and regular Spark apps.
log4j.logger.org.apache.spark.repl.Main=WARN

# Settings to quiet third party logs that are too verbose
log4j.logger.org.spark_project.jetty=WARN
log4j.logger.org.spark_project.jetty.util.component.AbstractLifeCycle=ERROR
log4j.logger.org.apache.spark.repl.SparkIMain$exprTyper=INFO
log4j.logger.org.apache.spark.repl.SparkILoop$SparkILoopInterpreter=INFO
log4j.logger.org.apache.parquet=ERROR
log4j.logger.parquet=ERROR

# SPARK-9183: Settings to avoid annoying messages when looking up nonexistent 
UDFs in SparkSQL with Hive support
log4j.logger.org.apache.hadoop.hive.metastore.RetryingHMSHandler=FATAL
log4j.logger.org.apache.hadoop.hive.ql.exec.FunctionRegistry=ERROR
"""

_EXPORT_ENV = ','.join([
    'PATH',
    'LD_LIBRARY_PATH',
    'JAVA_HOME',
    'SPARK_CONF_DIR',
    'PYTHONPATH',
])


def main():
    """The main driver."""

    parser = argparse.ArgumentParser(
        usage='Start Spark stand-alone cluster inside a SLURM job.',
        description=_DESCRIPTION
    )
    parser.add_argument(
        '-l', '--log-level',
        help='The log level for Spark.', default='FATAL',
        choices=[
            'OFF',
            'FATAL',
            'ERROR',
            'WARN',
            'INFO',
            'DEBUG',
            'TRACE'
        ]
    )
    parser.add_argument(
        '-f', '--parallel-factor',
        help='The factor for default Spark parallelism wrt the number of CPUs.',
        type=float, default=1.0
    )
    args = parser.parse_args()

    env = JobEnv()
    env.make_dirs()
    env.gen_confs(args.parallel_factor, args.log_level)
    env.launch()

    print(_OUT.format(conf_dir=env.conf_dir))

    return 0


_DESCRIPTION = """
The output of this program should be given be the `eval` of the bash shell to
finish setting up the job environment.
"""

_OUT = """
export SPARK_CONF_DIR={conf_dir};
"""

if __name__ == '__main__':
    main()

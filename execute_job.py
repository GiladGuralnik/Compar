import os
import re
import subprocess
import time

from database import Database
from exceptions import FileError
from subprocess_handler import run_subprocess
from timer import Timer
import traceback
import logger
from unit_test import UnitTest


class ExecuteJob:

    CHECK_SQUEUE_SECOND_TIME = 30
    TRY_SLURM_RECOVERY_AGAIN_SECOND_TIME = 300

    def __init__(self, job, num_of_loops_in_files, db, db_lock, serial_run_time, relative_c_file_list,
                 slurm_partition, test_file_path, time_limit=None):
        self.job = job
        self.num_of_loops_in_files = num_of_loops_in_files
        self.db = db
        self.db_lock = db_lock
        self.serial_run_time_dict = serial_run_time  # {(<file_id_by_rel_path>, <loop_label>) : <run_time>, ... }
        self.relative_c_file_list = relative_c_file_list
        self.time_limit = time_limit
        self.slurm_partition = slurm_partition
        self.test_file_path = test_file_path

    def get_job(self):
        return self.job

    def set_job(self, job):
        self.job = job

    def save_successful_job(self):
        self.update_speedup()
        job_result_dict = self.job.get_job_results()
        self.db_lock.acquire()
        self.db.insert_new_combination(job_result_dict)
        self.db_lock.release()

    def save_combination_as_failure(self, error_msg):
        combination_dict = {
            '_id': self.job.combination.combination_id,
            'error': error_msg
        }
        self.db_lock.acquire()
        self.db.insert_new_combination(combination_dict)
        self.db_lock.release()

    def update_speedup(self):
        job_results = self.job.get_job_results()['run_time_results']
        for file_dict in job_results:
            if 'dead_code_file' not in file_dict.keys():
                for loop_dict in file_dict['loops']:
                    try:
                        if 'dead_code' not in loop_dict.keys():
                            if not self.serial_run_time_dict:  # it is serial running
                                loop_dict['speedup'] = 1.0
                            else:
                                serial_run_time_key = (file_dict['file_id_by_rel_path'], loop_dict['loop_label'])
                                serial_run_time = float(self.serial_run_time_dict[serial_run_time_key])
                                parallel_run_time = float(loop_dict['run_time'])
                                try:
                                    loop_dict['speedup'] = serial_run_time / parallel_run_time
                                except ZeroDivisionError:
                                    loop_dict['speedup'] = float('inf')

                    except KeyError as e:  # if one of the keys doesn't exists, just for debug.
                        error_msg = 'key error: ' + str(e) + f', in file {file_dict["file_id_by_rel_path"]}'
                        if 'missing_data' in file_dict.keys():
                            error_msg = file_dict['missing_data'] + f'\n{error_msg}'
                        file_dict['missing_data'] = error_msg

    def run(self, user_slurm_parameters):
        try:
            self.__run_with_sbatch(user_slurm_parameters)
            self.__analyze_job_exit_code()
            self.__analysis_output_file()
            self.update_dead_code_files()
            self.save_successful_job()
            if not UnitTest.run_unit_test(self.test_file_path, self.get_job().get_directory_path(),
                                          f"{self.get_job().get_directory_name()}.log"):
                self.db.set_error_in_combination(self.job.combination.combination_id, "Unit test failed.")
        except Exception as ex:
            if self.job.get_job_results()['run_time_results']:
                self.save_successful_job()
            else:
                self.save_combination_as_failure(str(ex))

    def update_dead_code_files(self):
        job_results = self.job.get_job_results()['run_time_results']
        results_file_ids = [file_dict['file_id_by_rel_path'] for file_dict in job_results]
        for file_dict in self.relative_c_file_list:
            file_id = file_dict['file_relative_path']
            if file_id not in results_file_ids:
                job_results.append({'file_id_by_rel_path': file_id, 'dead_code_file': True})

    def __run_with_sbatch(self, user_slurm_parameters):
        logger.info(f'Start running combination #{self.get_job().get_combination().get_combination_id()}')
        slurm_parameters = user_slurm_parameters
        dir_path = self.get_job().get_directory_path()
        dir_name = os.path.basename(dir_path)
        x_file = dir_name + ".x"
        sbatch_script_file = self.__make_sbatch_script_file(x_file)

        log_file = dir_name + ".log"
        x_file_path = os.path.join(dir_path, x_file)
        log_file_path = os.path.join(dir_path, log_file)
        slurm_parameters = " ".join(slurm_parameters)
        cmd = f'sbatch {slurm_parameters} -o {log_file_path} {sbatch_script_file} {x_file_path}'
        if self.get_job().get_exec_file_args():
            cmd += f' {" ".join([str(arg) for arg in self.get_job().get_exec_file_args()])} '
        stdout = ""
        batch_job_sent = False
        while not batch_job_sent:
            # TODO: add timeout instead of batch_job_sent var
            stderr = ''
            try:
                stdout, stderr, ret_code = run_subprocess(cmd)
                batch_job_sent = True
            except subprocess.CalledProcessError as ex:
                logger.info_error(f'Exception at {ExecuteJob.__name__}: {ex}\n{ex.output}\n{ex.stderr}')
                logger.debug_error(f'{traceback.format_exc()}')
                logger.info_error('sbatch command not responding (slurm is down?)')
                time.sleep(ExecuteJob.TRY_SLURM_RECOVERY_AGAIN_SECOND_TIME)
        result = stdout
        # set job id
        result = re.findall('[0-9]', str(result))
        result = ''.join(result)
        self.get_job().set_job_id(result)
        cmd = f"squeue -j {self.get_job().get_job_id()} --format %t"
        last_status = ''
        is_first_time = True
        is_finish = False
        while not is_finish:
            try:
                stdout, stderr = '', ''
                try:
                    stdout, stderr, ret_code = run_subprocess(cmd)
                except subprocess.CalledProcessError:  # check if squeue is not working or if the job finished
                    _, _, ret_code = run_subprocess('squeue')
                    if ret_code != 0:
                        raise
                    else:
                        is_finish = True
                current_status = ''
                try:
                    current_status = stdout.split('\n')[1]
                except IndexError:
                    if not is_finish:
                        logger.info_error(f'Warning: check the squeue command output: {stdout} {stderr}')
                        time.sleep(ExecuteJob.TRY_SLURM_RECOVERY_AGAIN_SECOND_TIME)
                        continue
                if current_status != last_status and current_status != '':
                    logger.info(f'Job {self.get_job().get_job_id()} status is {current_status}')
                    last_status = current_status
                if not is_finish and not is_first_time:
                    # not is_first_time - some times the job go to COMPLETE immediately (fast running)
                    time.sleep(ExecuteJob.CHECK_SQUEUE_SECOND_TIME)
                if is_first_time:
                    is_first_time = False
            except subprocess.CalledProcessError as ex:  # squeue command not responding (slurm is down?)
                logger.info_error(f'Exception at {ExecuteJob.__name__}: {ex}\n{ex.stdout}\n{ex.stderr}')
                logger.debug_error(f'{traceback.format_exc()}')
                logger.info_error('squeue command not responding (slurm is down?)')
                time.sleep(ExecuteJob.TRY_SLURM_RECOVERY_AGAIN_SECOND_TIME)
        logger.info(f'Job {self.get_job().get_job_id()} status is COMPLETE')

    def __make_sbatch_script_file(self, job_name=''):
        batch_file_path = os.path.join(self.get_job().get_directory_path(), 'batch_job.sh')
        batch_file = open(batch_file_path, 'w')
        command = '#!/bin/bash\n'
        command += f'#SBATCH --job-name={job_name}\n'
        if self.time_limit:
            command += f'#SBATCH --time={self.time_limit}\n'
        command += f'#SBATCH --partition={self.slurm_partition}\n'
        command += '$@\n'
        command += 'exit $?\n'
        batch_file.write(command)
        batch_file.close()
        return batch_file_path

    def __analysis_output_file(self):
        combination_id = self.get_job().get_combination().get_combination_id()
        logger.info(f'{ExecuteJob.__name__}: analyzing job run time results of #{combination_id} combination')
        for root, dirs, files in os.walk(self.get_job().get_directory_path()):
            for file in files:
                # total run time analysis
                if re.search(rf"{Timer.TOTAL_RUNTIME_FILENAME}$", file):
                    total_runtime_file_path = os.path.join(root, file)
                    with open(total_runtime_file_path, 'r') as f:
                        self.get_job().set_total_run_time(float(f.read()))
                # loops runtime analysis
                if re.search("_run_time_result.txt$", file):
                    loops_dict = {}
                    file_full_path = os.path.join(root, file)
                    file_id_by_rel_path = os.path.relpath(file_full_path, self.job.directory)
                    file_id_by_rel_path = file_id_by_rel_path.replace("_run_time_result.txt", ".c")
                    self.get_job().set_file_results(file_id_by_rel_path)
                    try:
                        with open(file_full_path, 'r') as input_file:
                            for line in input_file:
                                if ":" in line:
                                    loop_label, loop_runtime = line.replace('\n', '').split(':')
                                    loop_runtime = float(loop_runtime)
                                    loops_dict[loop_label] = loop_runtime
                        ran_loops = list(loops_dict.keys())
                        for i in range(1, self.num_of_loops_in_files[file_id_by_rel_path][0] + 1):
                            if str(i) not in ran_loops:
                                self.get_job().set_loop_in_file_results(file_id_by_rel_path, i, None, dead_code=True)
                            else:
                                self.get_job().set_loop_in_file_results(file_id_by_rel_path, str(i), loops_dict[str(i)])
                    except OSError as e:
                        raise FileError(str(e))

    def __analyze_job_exit_code(self):
        job_id = self.get_job().get_job_id()
        command = f"sacct -j {job_id} --format=exitcode"
        try:
            stdout, stderr, ret_code = run_subprocess(command)
            result = stdout.replace("\r", "").split("\n")
            if len(result) < 3:
                logger.info_error(f'Warning: sacct command - no results for job id: {job_id}.')
                return
            left_code, right_code = result[2].replace(" ", "").split(":")
            left_code, right_code = int(left_code), int(right_code)
            if left_code != 0 or right_code != 0:
                raise Exception(f"Job id: {job_id} ended with return code: {left_code}:{right_code}.")
        except subprocess.CalledProcessError as ex:
            logger.info_error(f'Warning: sacct command not responding (slurm is down?)\n{ex.output}\n{ex.stderr}')

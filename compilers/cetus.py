from compilers.parallelCompiler import ParallelCompiler
from exceptions import CompilationError, CombinationFailure
import subprocess
import shutil
import os
import exceptions as e
from fragmentator import Fragmentator
from subprocess_handler import run_subprocess
import logger
from globals import CetusConfig, GlobalsConfig


class Cetus(ParallelCompiler):
    NAME = 'cetus'

    @staticmethod
    def replace_labels(file_path: str, num_of_loops: int):
        with open(file_path, 'r+') as f:
            content = f.read()
            for loop_id in range(1, num_of_loops + 1):
                old_start_label = '/* ' + Fragmentator.get_start_label()[3:] + str(loop_id) + ' */'
                new_start_label = Fragmentator.get_start_label() + str(loop_id)
                old_end_label = '/* ' + Fragmentator.get_end_label()[3:] + str(loop_id) + ' */'
                new_end_label = Fragmentator.get_end_label() + str(loop_id)
                content = content.replace(old_start_label, new_start_label)
                content = content.replace(old_end_label, new_end_label)
            f.seek(0)
            f.write(content)
            f.truncate()

    def __init__(self, version: str, input_file_directory: str = None, compilation_flags: list = None,
                 file_list: list = None, include_dirs_list: list = None, **kwargs):
        super().__init__(version, compilation_flags, input_file_directory, file_list, include_dirs_list, **kwargs)

    def compile(self):
        super().compile()
        try:
            for file in self.get_file_list():
                Cetus.replace_line_in_code(file["file_full_path"], GlobalsConfig.OMP_HEADER, '')
                cwd_path = os.path.dirname(file["file_full_path"])
                self.copy_headers(cwd_path)
                logger.info(f'{Cetus.__name__} start to parallelizing {file["file_name"]}')
                command = [f'cetus {" ".join(self.get_compilation_flags())} {file["file_name"]}']
                stdout, stderr, ret_code = run_subprocess(command, cwd_path)
                log_file_path = f'{os.path.splitext(file["file_full_path"])[0]}{CetusConfig.LOG_FILE_SUFFIX}'
                logger.log_to_file(f'{stdout}\n{stderr}', log_file_path)
                logger.debug(f'{Cetus.__name__} {stdout}')
                logger.debug_error(f'{Cetus.__name__} {stderr}')
                logger.info(f'{Cetus.__name__} finish to parallelizing {file["file_name"]}')
                # Replace file from cetus output folder into original file folder
                if os.path.isdir(os.path.join(cwd_path, CetusConfig.OUTPUT_DIR_NAME)):
                    src_file = os.path.join(cwd_path, CetusConfig.OUTPUT_DIR_NAME, file["file_name"])
                    dst_file = file["file_full_path"]
                    shutil.copy(src_file, dst_file)
                    shutil.rmtree(os.path.join(cwd_path, CetusConfig.OUTPUT_DIR_NAME))

                Cetus.inject_line_in_code(file["file_full_path"], GlobalsConfig.OMP_HEADER)
            return True
        except subprocess.CalledProcessError as ex:
            log_file_path = f'{os.path.splitext(file["file_full_path"])[0]}{CetusConfig.LOG_FILE_SUFFIX}'
            logger.log_to_file(f'{ex.output}\n{ex.stderr}', log_file_path)
            raise CombinationFailure(f'cetus return with {ex.returncode} code: {str(ex)} : {ex.output} : {ex.stderr}')
        except Exception as ex:
            raise CompilationError(str(ex) + " files in directory " + self.get_input_file_directory() +
                                   " failed to be parallel!")

    @staticmethod
    def replace_line_in_code(file_full_path: str, old_line: str, new_line: str):
        with open(file_full_path, 'r') as input_file:
            c_code = input_file.read()
        e.assert_file_is_empty(c_code)
        c_code = c_code.replace(old_line, new_line)
        try:
            with open(file_full_path, 'w') as output_file:
                output_file.write(c_code)
        except OSError as err:
            raise e.FileError(str(err))

    @staticmethod
    def inject_line_in_code(file_full_path: str, new_line: str):
        with open(file_full_path, 'r') as input_file:
            c_code = input_file.read()
        e.assert_file_is_empty(c_code)
        c_code = new_line + c_code
        try:
            with open(file_full_path, 'w') as output_file:
                output_file.write(c_code)
        except OSError as err:
            raise e.FileError(str(err))

    def copy_headers(self, target_dir_path: str):
        for rel_path in self.include_dirs_list:
            full_path = os.path.join(self._input_file_directory, rel_path)
            for path, dirs, files in os.walk(full_path):
                for file in files:
                    if file.endswith('.h'):
                        try:
                            shutil.copyfile(os.path.join(path, file), os.path.join(target_dir_path, file))
                        except shutil.SameFileError:
                            pass

    def pre_processing(self, **kwargs):
        super().pre_processing(**kwargs)

    def post_processing(self, **kwargs):
        super().post_processing(**kwargs)
        if 'files_loop_dict' in kwargs:
            files_loop_dict = kwargs['files_loop_dict']
            for file_dict in self.get_file_list():
                self.replace_labels(file_dict['file_full_path'], files_loop_dict[file_dict['file_id_by_rel_path']][0])

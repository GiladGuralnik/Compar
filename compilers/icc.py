from compilers.binaryCompiler import BinaryCompiler
import os
from subprocess_handler import run_subprocess
import logger


class Icc(BinaryCompiler):
    NAME = 'icc'

    def __init__(self, version, compilation_flags=None, main_c_file=None, input_file_directory=None):
        super().__init__(self.NAME, version, compilation_flags, main_c_file, input_file_directory)

    def run_compiler(self):
        input_file_path_only = os.path.dirname(self.get_input_file_directory() + os.path.sep)
        dir_name = os.path.basename(input_file_path_only)

        logger.info(f'{Icc.__name__} start to compiling {self.get_main_c_file()}')
        stdout, stderr, ret_code = run_subprocess([self.get_compiler_name()] + ["-fopenmp"]
                                                  + self.get_compilation_flags() + [self.get_main_c_file()]
                                                  + ["-o"] + [dir_name + ".x"], self.get_input_file_directory())
        logger.debug(stdout)
        logger.debug_error(stderr)
        logger.info(f'{Icc.__name__} finish to compiling {self.get_main_c_file()}')

import os

from compar import Compar
from unit_test import UnitTest


class FileError(Exception):
    pass


class CompilationError(Exception):
    pass


class ExecutionError(Exception):
    pass


class UserInputError(Exception):
    pass


class FolderError(Exception):
    pass


class DatabaseError(Exception):
    pass


class CombinationFailure(Exception):
    pass


class MissingDataError(Exception):
    pass


class MakefileError(Exception):
    pass


class FragmentError(Exception):
    pass


class DeadCodeLoop(Exception):
    pass


class NoOptimalCombinationError(Exception):
    pass


class DeadCodeFile(Exception):
    pass


def assert_file_exist(file_path):
    if not os.path.exists(file_path):
        raise FileError(f'File {file_path} not exist')


def assert_file_from_format(file_path, _format):
    if not os.path.basename(file_path).split('.')[1].endswith(_format):
        raise FileError(f'File {file_path} should be in {_format} format')


def assert_file_is_empty(file):
    if not file:
        raise FileError(f'File {file} is empty')


def assert_only_files(folder_path):
    folder_content = os.listdir(folder_path)
    if len(folder_content) != len(list(filter(os.path.isfile,
                                              [os.path.join(folder_path, file) for file in folder_content]))):
        raise UserInputError('Input dir must contain only files!')


def assert_rel_path_starts_without_sep(path):
    if path.startswith(os.sep):
        raise UserInputError('Relative path should not start with separator!')


def assert_forbidden_characters(path):
    forbidden_characters = ["{", "}"]
    for char in forbidden_characters:
        if char in path:
            raise UserInputError(f'Path cannot contain any char from: {forbidden_characters}')


def assert_test_file_name(test_file_name):
    if test_file_name != UnitTest.UNIT_TEST_FILE_NAME:
        raise UserInputError(f'Unit test file must be named as: {UnitTest.UNIT_TEST_FILE_NAME}!')


def assert_test_file_function_name(test_file_path):
    if not UnitTest.check_if_test_exists(test_file_path):
        raise UserInputError(f'Unit test file must contain test named: "{UnitTest.UNIT_TEST_NAME}"!')


def assert_original_files_folder_exists(working_directory):
    original_files_path = os.path.join(working_directory, Compar.ORIGINAL_FILES_FOLDER_NAME)
    if not os.path.exists(original_files_path):
        raise UserInputError(f'Original files folder from the last Compar operation must be exist in'
                             f' {working_directory}')


def assert_folder_exist(folder_path):
    if not os.path.exists(folder_path):
        raise FolderError(f'Folder {folder_path} not exist')

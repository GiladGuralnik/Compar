import re
import shutil
from exceptions import FileError
from exceptions import assert_file_exist
from file_formator import format_c_code


class Fragmentator:
    __START_LOOP_LABEL_MARKER = '// START_LOOP_MARKER'
    __END_LOOP_LABEL_MARKER = '// END_LOOP_MARKER'

    @staticmethod
    def set_start_label(new_start_label):
        Fragmentator.__START_LOOP_LABEL_MARKER = new_start_label

    @staticmethod
    def set_end_label(new_end_label):
        Fragmentator.__END_LOOP_LABEL_MARKER = new_end_label

    def __init__(self, file_path):
        assert_file_exist(file_path)
        self.__file_path = file_path
        self.__file_content = ''
        self.__loops_list = []
        self.__fragments = []
        self.__occurrences_index_list = []

    def __reset_data(self):
        self.__file_content = ''
        self.__loops_list.clear()
        self.__fragments.clear()
        self.__occurrences_index_list.clear()

    def get_file_path(self):
        return self.__file_path

    def set_file_path(self, new_file_path):
        assert_file_exist(new_file_path)
        self.__file_path = new_file_path
        self.__reset_data()

    def get_fragments(self):
        return self.__fragments

    def __backup_file(self):
        new_extension = '.bak'
        try:
            shutil.copy(self.__file_path, self.__file_path + new_extension)
        except OSError as e:
            raise FileError(str(e))

    def __get_file_content(self):
        # format_c_code([self.__file_path, ])
        try:
            with open(self.__file_path, 'r') as input_file:
                self.__file_content = input_file.read()
        except FileNotFoundError:
            raise FileError('File {} not exist'.format(self.__file_path))
        if not self.__file_content:
            raise FileError('The file {} is empty'.format(self.__file_path))

    def __find_loops(self):
        lines = self.__file_content.split('\n')
        self.__occurrences_index_list = []

        current_loop = {
            'start_position_index': -1,
            'loop_lines': [],
            'with_brackets': True
        }
        found_start = False

        def save_and_reset_data_to_new_loop():
            nonlocal found_start
            loop = '\n'.join(current_loop['loop_lines'])
            current_occurrence_index = 1
            if loop in self.__loops_list:
                current_occurrence_index = self.__loops_list.count(loop) + 1
            self.__loops_list.append(loop)
            self.__occurrences_index_list.append(current_occurrence_index)
            found_start = False
            current_loop['start_position_index'] = -1
            current_loop['loop_lines'].clear()
            current_loop['with_brackets'] = True

        for line in lines:
            if not line:
                continue
            if found_start:
                indent_chars = line[:current_loop['start_position_index']]
                try:
                    first_char_after_indent = line[current_loop['start_position_index']]
                    is_indent_only_spaces = set(indent_chars) == set(' ')
                    if is_indent_only_spaces and len(indent_chars) == current_loop['start_position_index']:
                        if first_char_after_indent == ' ':
                            current_loop['loop_lines'].append(line)
                        else:
                            if current_loop['with_brackets'] and first_char_after_indent == '}':
                                current_loop['loop_lines'].append(line)
                            save_and_reset_data_to_new_loop()
                    else:
                        save_and_reset_data_to_new_loop()
                except IndexError:
                    # the line is shorter than the required indent, the loop is ended.
                    # the current line may be a new loop
                    save_and_reset_data_to_new_loop()
            if not found_start:  # NOTICE THE COMMENT BELOW!!!
                # it is not the opposite of "if found start"!!!!
                # because the "found start" flag can be changed during the above if statement

                for_loop_regex_result = re.search('^[ ]*for', line)
                if for_loop_regex_result:
                    found_start = True
                    current_loop['loop_lines'].append(line)
                    current_loop['start_position_index'] = re.search('for', for_loop_regex_result.string).start()
                    if not re.search(r'{[ ]*$|{[ ]*//[\w\W]*$', line):
                        current_loop['with_brackets'] = False

    def __write_to_file(self, content):
        try:
            with open(self.__file_path, 'w') as output_file:
                output_file.write(content)
        except OSError as e:
            raise FileError(str(e))

    def __create_list_of_fragments(self):
        for index, loop in enumerate(self.__loops_list, 1):
            loop_with_markers = {
                'start_label': self.__START_LOOP_LABEL_MARKER + str(index),
                'loop': loop,
                'end_label': self.__END_LOOP_LABEL_MARKER + str(index)
            }
            self.__fragments.append(loop_with_markers)

    def fragment_code(self):
        self.__backup_file()
        self.__get_file_content()
        self.__find_loops()
        self.__create_list_of_fragments()
        new_content = ''
        rest_of_the_content = self.__file_content
        for i, loop_fragment in enumerate(self.__fragments):
            loop_start_offset = rest_of_the_content.find(loop_fragment['loop'])
            loop_end_offset = loop_start_offset + len(loop_fragment['loop'])
            loop_with_markers = loop_fragment['start_label'] + '\n'
            loop_with_markers += loop_fragment['loop']
            loop_with_markers += '\n' + loop_fragment['end_label']
            new_content += rest_of_the_content[:loop_start_offset]
            new_content += loop_with_markers
            rest_of_the_content = rest_of_the_content[loop_end_offset:]
        new_content += rest_of_the_content
        self.__file_content = new_content
        self.__write_to_file(self.__file_content)
        return self.get_fragments()

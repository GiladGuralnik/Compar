import pymongo
from exceptions import DatabaseError, MissingDataError, DeadCodeLoop, DeadCodeFile, NoOptimalCombinationError
from job import Job
import logger
import traceback
import hashlib
import getpass
import compar
from combination import Combination
from combinator import generate_combinations


class Database:

    STATIC_DB_NAME = "compar_combinations"
    DYNAMIC_DB_NAME = "compar_results"
    DB = "mongodb://10.10.10.120:27017"
    SERIAL_COMBINATION_ID = 'serial'
    SERIAL_COMPILER_NAME = 'serial'

    def __init__(self, collection_name, mode):
        collection_name = f"{getpass.getuser()}_{collection_name}"
        logger.info(f'Initializing {collection_name} databases')
        self.mode = mode
        try:
            self.collection_name = collection_name
            self.connection = pymongo.MongoClient(self.DB)
            self.static_db = self.connection[self.STATIC_DB_NAME]
            self.dynamic_db = self.connection[self.DYNAMIC_DB_NAME]

            if self.collection_name in self.static_db.list_collection_names():
                self.static_db.drop_collection(self.collection_name)

            self.static_db.create_collection(self.collection_name)
            self.initialize_static_db()

            if self.mode != compar.ComparMode.CONTINUE:
                if self.collection_name in self.dynamic_db.list_collection_names():
                    self.dynamic_db.drop_collection(self.collection_name)
                self.dynamic_db.create_collection(self.collection_name)
            else:
                ids_in_static = [comb['_id'] for comb in self.static_db[self.collection_name].find({}, {"_id": 1})]
                ids_in_dynamic = [comb['_id'] for comb in self.dynamic_db[self.collection_name].find({}, {"_id": 1})]
                old_ids = [comb_id for comb_id in ids_in_dynamic if comb_id not in
                           ids_in_static + [self.SERIAL_COMBINATION_ID]]
                self.dynamic_db[self.collection_name].delete_many({'_id': {'$in': old_ids}})
                del ids_in_static, ids_in_dynamic, old_ids
                self.dynamic_db[self.collection_name].delete_one({'_id': Combination.COMPAR_COMBINATION_ID})
                self.dynamic_db[self.collection_name].delete_one({'_id': Combination.FINAL_RESULTS_COMBINATION_ID})
        except Exception as e:
            raise DatabaseError(str(e) + "\nFailed to initialize DB!")

    def initialize_static_db(self):
        try:
            combinations = generate_combinations()
            for combination in combinations:
                curr_combination_id = Database.generate_combination_id(combination)
                self.static_db[self.collection_name].update_one(
                    filter={
                        '_id': curr_combination_id
                    },
                    update={
                        '$setOnInsert': combination
                    },
                    upsert=True
                )
        except Exception as e:
            logger.info_error(f'Exception at {Database.__name__}: cannot initialize static DB: {e}')
            logger.debug_error(f'{traceback.format_exc()}')
            raise DatabaseError()
        finally:
            del combinations

    def close_connection(self):
        self.connection.close()

    def combination_has_results(self, combination_id):
        return self.get_combination_results(combination_id) is not None

    def combinations_iterator(self):
        try:
            for combination in self.static_db[self.collection_name].find():
                if self.combination_has_results(combination['_id']):
                    continue
                yield combination
        except Exception:
            logger.info_error(f"Execption at {Database.__name__}: get_next_combination")
            raise

    def insert_new_combination_results(self, combination_result):
        try:
            self.dynamic_db[self.collection_name].insert_one(combination_result)
            return True
        except Exception as e:
            logger.info_error(f'{Database.__name__} cannot update dynamic DB: {e}')
            logger.debug_error(f'{traceback.format_exc()}')
            return False

    def delete_combination(self, combination_id):
        try:
            self.dynamic_db[self.collection_name].delete_one({"_id": combination_id})
            return True
        except Exception as e:
            logger.info_error(f'Exception at {Database.__name__}: Could not delete combination: {e}')
            logger.debug_error(f'{traceback.format_exc()}')
            return False

    def find_optimal_loop_combination(self, file_id_by_rel_path, loop_label):
        best_speedup = 1
        best_combination_id = self.SERIAL_COMBINATION_ID
        best_loop = None
        loop_is_dead_code = True
        file_is_dead_code = True
        combinations = self.dynamic_db[self.collection_name].find({})
        for combination in combinations:
            if 'error' not in combination.keys():
                for file in combination['run_time_results']:
                    if file['file_id_by_rel_path'] == file_id_by_rel_path:
                        if 'dead_code_file' in file.keys():
                            file_is_dead_code = file_is_dead_code and True
                            break
                        else:
                            file_is_dead_code = False
                            for loop in file['loops']:
                                if loop['loop_label'] == loop_label:
                                    if 'dead_code' in loop.keys():
                                        loop_is_dead_code = loop_is_dead_code and True
                                    else:
                                        loop_is_dead_code = False
                                        if combination['_id'] == Database.SERIAL_COMBINATION_ID and not best_loop \
                                                and best_combination_id == Database.SERIAL_COMBINATION_ID:
                                            best_loop = loop
                                        if loop['speedup'] > best_speedup:
                                            best_speedup = loop['speedup']
                                            best_combination_id = combination['_id']
                                            best_loop = loop
                                    break
                            break
        del combinations
        if file_is_dead_code:
            raise DeadCodeFile(f'file {file_id_by_rel_path} is dead code!')
        if loop_is_dead_code:
            raise DeadCodeLoop(f'Loop {loop_label} in file {file_id_by_rel_path} is dead code!')
        if not best_loop:
            raise MissingDataError(f'Cannot find any loop in db, loop: {loop_label}, file: {file_id_by_rel_path}')
        return best_combination_id, best_loop

    def get_combination_results(self, combination_id):
        combination = None
        try:
            combination = self.dynamic_db[self.collection_name].find_one({"_id": combination_id})
        except Exception as e:
            logger.info_error(f'Exception at {Database.__name__}: Could not find results for combination: {e}')
            logger.debug_error(f'{traceback.format_exc()}')
        finally:
            return combination

    def get_combination_from_static_db(self, combination_id):
        combination = None
        if combination_id == self.SERIAL_COMBINATION_ID:
            return {
                "_id": Database.SERIAL_COMBINATION_ID,
                "compiler_name": Database.SERIAL_COMPILER_NAME,
                "parameters": {
                    "omp_rtl_params": [],
                    "omp_directives_params": [],
                    "compilation_params": []
                }
            }
        try:
            combination = self.static_db[self.collection_name].find_one({"_id": combination_id})
        except Exception as e:
            logger.info_error(f'Exception at {Database.__name__}: Could not find combination: {e}')
            logger.debug_error(f'{traceback.format_exc()}')
        finally:
            return combination

    def get_total_runtime_best_combination(self):
        best_combination = self.dynamic_db[self.collection_name].find_one(
            {"$and": [{"error": {"$exists": False}}, {"total_run_time": {"$ne": Job.RUNTIME_ERROR}}]},
            sort=[("total_run_time", 1)])
        if not best_combination:
            raise NoOptimalCombinationError("All Compar combinations finished with error.")
        return best_combination["_id"]

    def remove_unused_data(self, combination_id):
        self.dynamic_db[self.collection_name].update({"_id": combination_id}, {'$unset': {'run_time_results': ""}})

    def set_error_in_combination(self, combination_id, error):
        self.dynamic_db[self.collection_name].update_one(
            filter={
                '_id': combination_id,
            },
            update={
                '$set': {
                    'error': error
                }
            }
        )

    def delete_all_related_collections(self):
        if self.collection_name in self.static_db.list_collection_names():
            self.static_db.drop_collection(self.collection_name)
        if self.collection_name in self.dynamic_db.list_collection_names():
            self.dynamic_db.drop_collection(self.collection_name)

    @staticmethod
    def generate_combination_id(combination):
        fields = [f'compiler_name:{combination["compiler_name"]}']
        omp_rtl_params = combination['parameters']['omp_rtl_params']
        for omp_rtl_param in omp_rtl_params:
            fields.append(f'omp_rtl_params:{omp_rtl_param}')
        omp_directives_params = combination['parameters']['omp_directives_params']
        for omp_directives_param in omp_directives_params:
            fields.append(f'omp_directives_params:{omp_directives_param}')
        compilation_params = combination['parameters']['compilation_params']
        for compilation_param in compilation_params:
            fields.append(f'compilation_params:{compilation_param}')
        fields.sort()
        return hashlib.sha3_384(str(fields).encode()).hexdigest()

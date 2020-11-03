#! /usr/bin/python
import os
import glob
import re
import argparse
import logging
import subprocess
import json
import sys
from multiprocessing import Pool
from typing import Optional, List

logging.StreamHandler(sys.stdout)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

"""
How to modularize:
    - ImageDescriptionWriter
        - Initialized with a filename and config options
        - Forces a parse on "parseImage"
        - Get EXIF metadata function
        - write_metadata_field method
        - write_description method
        - parallelize writing
"""

REPLACEABLE_EXTENSIONS = [
    '.jpg',
    '.png',
    '.mov',
    '.avi',
    '.cr2',
]

REPLACEABLE_PATTERNS = [
    r'IMG_.*',
    r'DSCN.*',
    r'839A.*',
    r'MVI_.*'
]

DESC_KEY = 'Description'
NUM_THREADS = 8
SPACE_REPLACEMENT = '-'
DIR_SEPARATOR = '_'

class ImageRenamer:

    def __init__(self,
                 directory: str,
                 include_root: bool = False,
                 dry_run: bool = False,
                 all_files: bool = False):
        self.directory = directory
        self.dry_run = dry_run
        self.include_root = include_root
        self.all_files = all_files

        self.root_dir_length = len(directory)
        self.update_msg = "[DRY RUN] Updated" if dry_run else "Updated"

    @classmethod
    def get_path_components(cls, file_path: str) -> Optional[List[str]]:
        """
        Given a file path, break it into its constituants in the form
        (dir_string, filename_base, extension (with "."))
        """
        split = os.path.split(file_path)
        dir_string = split[0]
        filename = split[1]
        filename_base = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        return (dir_string, filename_base, ext)

    @staticmethod
    def clean_dirname(dirname: str) -> str:
        """
        Given a directory name, clean it for file-setting
            - remove any non-alphanumeric or "-_ " characters
            - replace spaces with dashes
            - lowercase the jawn
        """
        return re.sub(r'[^a-zA-Z0-9_\- ]', '', dirname)\
            .lower()\
            .replace(" ", "-")

    def write_directory_structure(self, file_path: str) -> int:
        """
        Given a full file path, create a description from the dir structure and replace if necessary

        Return codes:
            0  Updated
            1  Skipped
            -1 Error
        """
        try:
            (dir_string, filename_base, ext) = self.get_path_components(file_path)
            if self.all_files or any([re.match(r, filename_base) for r in REPLACEABLE_PATTERNS]):
                filename_dir_string = dir_string
                if not self.include_root:
                    filename_dir_string = filename_dir_string[len(self.directory):]

                cleaned_dir_components = [self.clean_dirname(d) for d in filename_dir_string.split("/")]
                cleaned_dir_components = [d for d in cleaned_dir_components if d]  # Remove any empty components

                new_filename_base = "_".join(cleaned_dir_components)

                if filename_base.startswith(new_filename_base):
                    logger.debug(f"Skipping file '{file_path}' because it seems to already be renamed")
                    return 1

                new_filename = f"{new_filename_base}_{filename_base}{ext}"
                new_file_path = f"{dir_string}/{new_filename}"

                logger.debug(f"Renaming file {file_path}  --->  {new_file_path}")
                if not self.dry_run:
                    os.rename(file_path, new_file_path)

                return 0
            else:
                logger.debug(f"Skipping file '{file_path}' because it is not in the list of acceptable file patterns")
                return 1
        except OSError as e:
            logger.warning(f"Unable to process image {file_path} (OSError)", e)
            return -1
        except Exception as e:
            logger.error(f"Unexpected error occured while processing image {file_path}.", e)
            return -1
        
        return -1

    def clean_directory_metadata(self, filepath: str) -> int:
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext == '.jpg':
                desc = self.get_description(filepath)
                if desc and self.existing_prefix in desc:
                    if not self.dry_run:
                        self.remove_description(filepath)
                    logger.debug(f"{self.update_msg} {filepath} -- Removed description")
                    return 0
                else:
                    logger.debug(f"NOT Updated {filepath}: '{desc}'")
                    return 1
            else:
                return 1
        except Exception as e:
            logger.error(f"Unexpected error occured while processing image {filepath}.", e)
            return -1


    def execute_on_files(self, func):
        files = glob.glob('{}/**/*.*'.format(self.directory), recursive=True)
        # files = [f for f in files if os.path.splitext(f)[1].lower() in REPLACEABLE_EXTENSIONS]

        logger.info("Found {} files in {}".format(len(files), self.directory))
        
        results = [func(f) for f in files]

        # with Pool(5) as p:
        #     results = p.map(func, files)

        # Count the values for logging
        updated_count = results.count(0)
        skipped_count = results.count(1)
        errored_count = results.count(-1)

        logger.info(f'{self.update_msg} {updated_count} files, Skipped {skipped_count} files, Failed {errored_count}')

    def write_metadata(self):
        self.execute_on_files(self.write_directory_structure)

    def clean_metadata(self):
        self.execute_on_files(self.clean_directory_metadata)

def __main__(args):
    if args.v:
        logger.setLevel(level=logging.DEBUG)
    if args.q:
        logger.setLevel(level=logging.ERROR)

    if args.dry_run:
        logger.info('Running in DRY RUN mode.  No files will be modified.')

    renamer = ImageRenamer(args.dir, args.include_root, args.dry_run, args.all)

    if args.action == 'write':
        renamer.write_metadata()
    elif args.action == 'clean':
        renamer.clean_metadata()

parser = argparse.ArgumentParser(description='Rename images in a directory based on their directory structure')
parser.add_argument('action', help='Write or clean the metadata from the files.', choices=['write', 'clean'], default='write')
parser.add_argument('dir', metavar='DIR', help='The root directory which to recurse through.')
parser.add_argument('-f', action='store_true', help='Force rewriting of existing descriptions.')
parser.add_argument('--include-root', action='store_true', help='Include the root directory in the naming')
parser.add_argument('-v', action='store_true', help='Verbose')
parser.add_argument('-q', action='store_true', help='Quiet (minimize output)')
parser.add_argument('-d', '--dry-run', action='store_true', help='Dry run (don\'t write any changes)')
parser.add_argument('-a', '--all', action='store_true', help='Do not restrict replacement to photo-looking patterns')
args = parser.parse_args()

__main__(args)

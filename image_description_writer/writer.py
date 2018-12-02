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
from typing import Optional

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

ALLOWED_EXT = [
    '.jpg'
]

DESC_KEY = 'Description'
NUM_THREADS = 8

class ImageDescriptionWriter:

    def __init__(self,
                 directory: str,
                 prefix: str,
                 existing_prefix: str = None,
                 force: bool = False,
                 dry_run: bool = False):
        self.directory = directory
        self.prefix = prefix
        self.existing_prefix = existing_prefix or prefix
        self.force = force
        self.dry_run = dry_run

        self.root_dir_length = len(directory)
        self.update_msg = "[DRY RUN] Updated" if dry_run else "Updated"

    def exiftool_exists() -> bool:
        # TODO: Implement this
        pass

    @staticmethod
    def get_field(file_path: str, field_name: str) -> Optional[object]:
        """
        Given a file path and a field name, get that field from the Exif data using exiftool
        """
        try:
            cmd = ['exiftool',
                '-ignoreMinorErrors',
                '-json',
                '-{}'.format(field_name), file_path
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                logger.warn(f'Unable to get field "{field_name}" for image {file_path}')
                return None
            else:
                result_json = json.loads(proc.stdout.decode('UTF-8'))
                return result_json[0].get(field_name)
        except subprocess.CalledProcessError as err:
            logger.error('Call to exiftool failed:', err)
            return None

    @classmethod
    def get_description(cls, file_path: str) -> Optional[str]:
        """
        Given a file path, get the Description exif field
        """
        return cls.get_field(file_path, DESC_KEY)

    @staticmethod
    def set_field(file_path: str, field_name: str, value: str, overwrite: bool = True) -> bool:
        try:
            cmd = ['exiftool',
                '-ignoreMinorErrors',
                f'-{field_name}={value}'.format(field_name)
            ]
            if overwrite:
                cmd.append('-overwrite_original')
            cmd.append(file_path)
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                logger.warning(f'Unable to set field "{field_name}" to "{value}" for image {file_path}')
                return False
            else:
                return True
        except subprocess.CalledProcessError as err:
            logger.error('Call to exiftool failed:', err)
            return False

    @classmethod
    def set_description(cls, file_path: str, value: str) -> bool:
        """
        Given a file path and a description string, write the Description field
        of the file
        """
        return cls.set_field(file_path, DESC_KEY, value)

    @classmethod
    def remove_description(cls, file_path: str):
        """
        Given a file path, remove the description metadata on the file
        """
        return cls.set_description(file_path, '')

    def write_directory_structure(self, filepath: str) -> int:
        """
        Given a file path, create a description, parse the existing description
        and replace if necessary.

        Return codes:
            0  Updated
            1  Skipped
            -1 Error
        """
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext == '.jpg':
                # Pull out exif data from the image
                desc = self.get_description(filepath)
                # import ipdb; ipdb.set_trace()
                if not desc or self.existing_prefix in desc or self.force:
                    # Clean up the path and split the path components into "tags"
                    trimmed_path = filepath[self.root_dir_length:]
                    split_path = ' '.join(trimmed_path.split('/'))
                    new_desc = f'{self.prefix} {split_path}'

                    # Only write to the file if dry_run is false and we actually have updates
                    if new_desc != desc:
                        if not self.dry_run:
                            # Update the exif dict and write it to the file
                            self.set_description(filepath, new_desc)
                        logger.debug(f"{self.update_msg} {filepath}: '{new_desc}'")
                        return 0
                    else:
                        logger.debug(f"NOT Updated (already written) {filepath}: '{desc}'")
                else:
                    logger.debug(f"NOT Updated {filepath}: '{desc}'")
                    return 1
        except OSError as e:
            logger.warning(f"Unable to process image {filepath} (OSError)")
            return -1
        except TypeError as e:
            print(e)
            logger.warning(f"Unable to process image {filepath} (TypeError)")
            return -1
        except Exception as e:
            logger.error(f"Unexpected error occured while processing image {filepath}.", e)
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
        files = [f for f in files if os.path.splitext(f)[1].lower() in ALLOWED_EXT]

        logger.info("Found {} files in {}".format(len(files), self.directory))

        with Pool(5) as p:
            results = p.map(func, files)

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

    imgWriter = ImageDescriptionWriter(args.dir, args.prefix, args.existing_prefix, args.f, args.dry_run)

    if args.action == 'write':
        imgWriter.write_metadata()
    elif args.action == 'clean':
        imgWriter.clean_metadata()

parser = argparse.ArgumentParser(description='Write EXIF metadata to files based on their directory structure')
parser.add_argument('action', help='Write or clean the metadata from the files.', choices=['write', 'clean'], default='write')
parser.add_argument('dir', metavar='DIR', help='The root directory which to recurse through.')
parser.add_argument('-f', action='store_true', help='Force rewriting of existing descriptions.')
parser.add_argument('--prefix', help='The string with which to prepend the descriptions', default='[EXIF writer]')
parser.add_argument('--existing-prefix', help='An alternative prefix which to search for as safe to replace')
parser.add_argument('-v', action='store_true', help='Verbose')
parser.add_argument('-q', action='store_true', help='Quiet (minimize output)')
parser.add_argument('-d', '--dry-run', action='store_true', help='Dry run (don\'t write any changes)')
args = parser.parse_args()

__main__(args)

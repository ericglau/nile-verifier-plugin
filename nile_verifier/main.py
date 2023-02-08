import os
import time
import asyncclick as click
import logging
import re
from os.path import basename, splitext
from nile.common import get_class_hash
from nile_verifier.api import Api
from yaspin import yaspin
from yaspin.spinners import Spinners
from starkware.cairo.lang.compiler import cairo_compile

@click.command()
@click.argument("main_file", nargs=1)
@click.option("--network", nargs=1, required=True)
@click.option("--compiler_version", nargs=1, default="0.10.3")
@click.option("--cairo_path", nargs=1)
def verify(main_file, network, compiler_version, cairo_path):
    """
    Command for automatically verify the sourcecode of a contract on starkscan.co.
    """
    api = Api(network)
    contract_name = get_contract_name(main_file)
    class_hash = hex(get_class_hash(contract_name))

    if api.is_hash_verifiable(class_hash):
        import_search_paths = get_import_search_paths(cairo_path)

        logging.info(f"🔎  Verifying {contract_name} on {network}...")
        job_id = api.create_job({
            "main_file_path": basename(main_file),
            "class_hash": class_hash,
            "name": contract_name,
            "compiler_version": compiler_version,
            "is_account_contract": check_is_account(main_file),
            "files": get_files(main_file, import_search_paths),
        })

        status = 'PENDING'
        with yaspin(Spinners.earth, text="Waiting for verification result") as sp:
            while status == 'PENDING':
                time.sleep(1)
                status, response = api.get_job_status(job_id)

        if status == 'FAILED':
            logging.error("💥  Verification failed:")
            logging.error(response['error_message'])
        else:
            scanner_url = api.get_scanner_link(class_hash)
            logging.info(f"✅  Success! {scanner_url}")


def check_is_account(main_file):
    # to do: improve detection
    contract_name = get_contract_name(main_file)
    return contract_name.endswith("Account")

def get_files(main_file, import_search_paths, files = {}, include_path=False):
    print(f"processing contract {main_file}")

    contract_filename = basename(main_file)
    key = contract_filename if not include_path else main_file
    if key in files:
        # this is already processed in a shallower level of recursion
        print(f"already processed {files}")
        return files

    found_contract = False
    for import_search_path in import_search_paths:
        contract_abs_path = f"{import_search_path}/{main_file}"
        if os.path.exists(contract_abs_path):
            found_contract = True
            with open(contract_abs_path) as f:
                print(f"reading file {contract_filename} in path {contract_abs_path}")
                file_content = f.read()

                files[key] = file_content

                regex = "^from\s(.*?)\simport"
                regex_compiled = re.compile(regex, re.MULTILINE)
                result = regex_compiled.findall(file_content)
                print(f"regex result: {result}")

                iterator = map(to_cairo_file_path, result)
                imported_files = list(iterator)
                print(f"imported files: {imported_files}")

                for imported_file in imported_files:
                    recursive_files = get_files(imported_file, import_search_paths, files, include_path=True)
                    files.update(recursive_files)
            break

    if found_contract is False:
        raise Exception(
                f"Could not find {main_file} in any of the following paths: {import_search_paths}"
            )

    print(f"all keys {files.keys()}")
    return files

def to_cairo_file_path(filepath):
    return f"{filepath.replace('.', '/')}.cairo"

def get_contract_name(path):
    return splitext(basename(path))[0]

# Import search path order according to
# https://www.cairo-lang.org/docs/how_cairo_works/imports.html#import-search-paths and
# https://github.com/starkware-libs/cairo-lang/blob/v0.10.3/src/starkware/cairo/lang/compiler/cairo_compile.py#L152
def get_import_search_paths(cairo_path):
    """
    Get import search paths in the following order:
    1. --cairo_path parameter
    2. CAIRO_PATH environment variable
    3. current directory
    4. standard library directory relative to the compiler path

    Arguments:
    `cairo_path` - The --cairo_path parameter as a colon-separated list
    """
    search_paths = []

    # --cairo_path parameter
    print(f"cairo_path param {cairo_path}")
    if cairo_path is not None:
        search_paths.extend(cairo_path.split(":"))

    # CAIRO_PATH environment variable
    envVar = os.getenv('CAIRO_PATH')
    print(f"os env var {envVar}")
    search_paths.extend(envVar.split(":"))

    # current directory and standard library directory relative to the compiler path
    starkware_src = os.path.join(os.path.dirname(cairo_compile.__file__), "../../../..")
    search_paths.extend([os.curdir, starkware_src])
    print(f"cairo_paths {search_paths}")

    absolute_search_paths = [
        os.path.abspath(path)
        for path in search_paths
        # if path is not None and os.path.isdir(path)
    ]
    print(f"absolute_search_paths {absolute_search_paths}")
    return absolute_search_paths

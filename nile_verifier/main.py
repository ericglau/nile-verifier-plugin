import os
import time
import asyncclick as click
import logging
import re
from os.path import basename, splitext, exists
from nile.common import get_class_hash
from nile_verifier.api import Api
from yaspin import yaspin
from yaspin.spinners import Spinners
from starkware.cairo.lang.compiler import cairo_compile

@click.command()
@click.argument("main_file", nargs=1)
@click.option("--network", nargs=1, required=True)
@click.option("--compiler_version", nargs=1, default="0.10.2")
def verify(main_file, network, compiler_version):
    """
    Command for automatically verify the sourcecode of a contract on starkscan.co.
    """
    api = Api(network)
    contract_name = get_contract_name(main_file)
    class_hash = hex(get_class_hash(contract_name))

    if api.is_hash_verifiable(class_hash):
        logging.info(f"🔎  Verifying {contract_name} on {network}...")
        job_id = api.create_job({
            "main_file_path": basename(main_file),
            "class_hash": class_hash,
            "name": contract_name,
            "compiler_version": compiler_version,
            "is_account_contract": check_is_account(main_file),
            "files": get_files(main_file),
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

def get_files(main_file, include_path=False):
    print(f"processing files {main_file}")

    cairo_paths = getCairoPaths()

    # to do: support multifile
    contract_paths = [main_file]

    files = {}
    for contract_path in contract_paths:
        contract_filename = basename(contract_path)
        
        # possible_file_locations = []
        for cairo_path in cairo_paths:
            contract_abs_path = f"{cairo_path}/{contract_path}"
            if os.path.exists(contract_abs_path):
                print(f"GOOD path {contract_abs_path} exists")
                with open(contract_abs_path) as f:
                    key = contract_filename if not include_path else contract_path
                    print(f"saving as key {key}")
                    files[key] = f.read()
                    print(f"reading file {contract_filename} in path {contract_abs_path}") #, content {files[contract_filename]}")

                    regex = "^from\s(.*?)\simport"
                    regex_compiled = re.compile(regex, re.MULTILINE)
                    result = regex_compiled.findall(files[key])
                    print(f"regex result: {result}")

                    iterator = map(to_cairo_file_path, result)
                    imported_files = list(iterator)
                    print(f"imported files: {imported_files}")

                    for imported_file in imported_files:
                        recursive_files = get_files(imported_file, include_path=True)
                        files.update(recursive_files)
            else:
                print(f"ERROR path {contract_abs_path} does not exist")
        # possible_file_locations = [
        #     os.path.abspath(path)
        #     for path in cairo_paths
        #     if path is not None and os.path.isdir(path)
        # ]


    # print(f"files {files}")
    print(f"all keys {files.keys()}")
    return files

def to_cairo_file_path(filepath):
    return f"{filepath.replace('.', '/')}.cairo"

def append_basedir(basedir, filepath):
    return f"{basedir}/{filepath}"

def get_contract_name(path):
    return splitext(basename(path))[0]

# list of cairo search paths
def getCairoPaths():
    # TODO search paths: according to https://github.com/starkware-libs/cairo-lang/blob/54d7e92a703b3b5a1e07e9389608178129946efc/src/starkware/cairo/lang/compiler/cairo_compile.py
    # 1. --cairo_path
    # 2. CAIRO_PATH
    # 3. cwd
    # 4. standard library directory relative to the compiler path

    cairo_path = [] # TODO support initial value to be passed in
    starkware_src = os.path.join(os.path.dirname(cairo_compile.__file__), "../../../..")
    cairo_path = [
        os.path.abspath(path)
        for path in cairo_path + [os.curdir, starkware_src]
        if path is not None and os.path.isdir(path)
    ]
    print(f"cairo_path {cairo_path}")
    return cairo_path

    # package = os.path.dirname(os.path.abspath(__file__))
    # print(f"os package dir {package}")
    # return (f"{package}/artifacts", f"{package}/artifacts/abis")
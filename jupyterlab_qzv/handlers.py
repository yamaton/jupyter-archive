import datetime
import json
import logging
import os
import pathlib
import shutil
import tarfile
from pathlib import Path
from typing import Optional
import zipfile

from jupyter_core.utils import ensure_async
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url2path, url_path_join
from tornado import ioloop, web


QIIME_DIR_NAME = "_qiime"
QIIME_TIMESTAMP_FILE = "_created"

def make_reader(archive_path: Path):
    archive_format = "".join(archive_path.suffixes)
    if archive_format.endswith(".qzv"):
        archive_file = zipfile.ZipFile(archive_path, mode="r")
    else:
        raise ValueError("'{}' is not a valid archive format.".format(archive_format))
    return archive_file


def get_uuid(qzv_path: pathlib.Path) -> Optional[str]:
    """Extracted root directory should be of UUID format
    """
    # Open the QZV file
    with zipfile.ZipFile(qzv_path, mode='r') as myzip:
        # Get the list of all files and directories in the zip
        p = Path(myzip.namelist()[0])
        uuid = p.parts[0] if p.parts else None

    return uuid


def write_timestamp(uuid_str: str) -> None:
    """Record zip-extraction date to ~/_qiime/{uuid_str}/_created
    """
    p = Path.home() / QIIME_DIR_NAME / uuid_str / QIIME_TIMESTAMP_FILE
    with p.open("w") as f:
        date = datetime.date.today().isoformat()
        print(date, file=f)


def prepare_qiime_dir() -> Path:
    root = Path.home() / QIIME_DIR_NAME
    root.mkdir(exist_ok=True)
    return root


def cleanup_qiime_dir(interval_threshold=10) -> None:
    """Remove over-10-day-old directories in ~/_qiime for cleanup"""
    root = prepare_qiime_dir()
    paths = root.glob(f"*/{QIIME_TIMESTAMP_FILE}")

    today = datetime.datetime.today()
    for p in paths:
        with p.open() as f:
            datestr = f.read().strip()
        creation_date = datetime.datetime.strptime(datestr, "%Y-%m-%d")
        delta = today - creation_date
        if delta.days > interval_threshold:
            dirpath = p.parent
            try:
                shutil.rmtree(dirpath)
                logging.info(f"Cleaning up outdated directory: {dirpath}")
            except OSError as e:
                logging.error(f"Error: {e.filename} - {e.strerror}.")



class ExtractQzvHandler(APIHandler):
    @web.authenticated
    async def get(self, qzv_path):

        # /extract-qzv/ requests must originate from the same site
        self.check_xsrf_cookie()
        cm = self.contents_manager

        if await ensure_async(cm.is_hidden(qzv_path)) and not cm.allow_hidden:
            self.log.info("Refusing to serve hidden file, via 404 Error")
            raise web.HTTPError(404)

        hubuser = os.environ.get("JUPYTERHUB_USER", "jovyan")
        if not hubuser:
            msg = f"Failed to get JuphterHub username"
            self.log.error(msg)
            self.set_status(500)
            self.write(json.dumps({"data": msg}))
            raise web.HTTPError(500)

        qzv_path = pathlib.Path(cm.root_dir) / url2path(qzv_path)
        uuid_str = get_uuid(qzv_path)
        if uuid_str is None:
            msg = f"Failed to get UUID from the QZV file: {qzv_path.name}"
            self.log.error(msg)
            self.set_status(500)
            self.write(json.dumps({"data": msg}))
            raise web.HTTPError(500)

        cleanup_qiime_dir()
        await ioloop.IOLoop.current().run_in_executor(None, self.extract_qzv, qzv_path)
        write_timestamp(uuid_str)

        # slash at the tail matters
        service_prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")
        url = os.path.join(service_prefix,  f"/shiny/{QIIME_DIR_NAME}/{uuid_str}/data/#")
        self.finish(json.dumps({"data": url}))


    def extract_qzv(self, archive_path):
        archive_destination = prepare_qiime_dir()
        self.log.info("Begin extraction of {} to {}.".format(archive_path, archive_destination))

        archive_reader = make_reader(archive_path)

        if isinstance(archive_reader, tarfile.TarFile):
            # Check file path to avoid path traversal
            # See https://nvd.nist.gov/vuln/detail/CVE-2007-4559
            with archive_reader as archive:
                for name in archive_reader.getnames():
                    if os.path.relpath(archive_destination / name, archive_destination).startswith(os.pardir):
                        error_message = f"The archive file includes an unsafe file path: {name}"
                        self.log.error(error_message)
                        raise web.HTTPError(400, reason=error_message)
            # Re-open stream
            archive_reader = make_reader(archive_path)

        with archive_reader as archive:
            archive.extractall(archive_destination)

        self.log.info("Finished extracting {} to {}.".format(archive_path, archive_destination))



def setup_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    handlers = [
        (url_path_join(base_url, r"/extract-qzv/(.*)"), ExtractQzvHandler),
    ]
    web_app.add_handlers(host_pattern, handlers)

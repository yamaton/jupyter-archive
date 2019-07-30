import os
import zipfile
import tarfile

from tornado import gen, web
from notebook.base.handlers import IPythonHandler


class ZipStream():
    def __init__(self, handler):
        self.handler = handler
        self.position = 0

    def write(self, data):
        self.position += len(data)
        self.handler.write(data)

    def tell(self):
        return self.position

    def flush(self):
        self.handler.flush()


def make_writer(handler, archive_format="zip"):
    fileobj = ZipStream(handler)

    if archive_format == "zip":
        archive_file = zipfile.ZipFile(fileobj, mode='w')
        archive_file.add = archive_file.write
    elif archive_format == "tgz":
        archive_file = tarfile.TarFile(fileobj=fileobj, mode='w')
    else:
        raise ValueError("'{}' is not a valid archive format.".format(archive_format))
    return archive_file


class ArchiveHandler(IPythonHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @web.authenticated
    @gen.coroutine
    def get(self):

        # TODO: Switch everything to pathlib.

        archive_path = self.get_argument('archivePath')
        archive_token = self.get_argument('archiveToken')
        archive_format = self.get_argument('archiveFormat', 'zip')

        archive_path = os.path.abspath(archive_path)
        archive_name = os.path.basename(archive_path)
        archive_filename = "{}.{}".format(archive_name, archive_format)

        # We gonna send out event streams!
        self.set_header('content-type', 'application/octet-stream')
        self.set_header('cache-control', 'no-cache')
        self.set_header(
            'content-disposition',
            'attachment; filename={}'.format(archive_filename)
        )

        self.log.info('Archiving {}.'.format(archive_filename))

        archive_writer = make_writer(self, archive_format)
        with archive_writer as writer:
            for root, dirs, files in os.walk(archive_path):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    writer.add(file_path, os.path.join(root[len(archive_path):], filename))

        self.set_cookie("archiveToken", archive_token)
        self.log.info('Finished archiving {}.'.format(archive_filename))

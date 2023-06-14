import platform
import shutil
import tarfile
import zipfile

import pytest

from tornado.httpclient import HTTPClientError

@pytest.mark.parametrize(
    "format, mode",
    [
        ("zip", "r"),
        ("tgz", "r|gz"),
        ("tar.gz", "r|gz"),
        ("tbz", "r|bz2"),
        ("tbz2", "r|bz2"),
        ("tar.bz", "r|bz2"),
        ("tar.bz2", "r|bz2"),
        ("txz", "r|xz"),
        ("tar.xz", "r|xz"),
    ],
)

def _create_archive_file(root_dir, file_name, format, mode):
    # Create a dummy directory.
    archive_dir_path = root_dir / file_name
    archive_dir_path.mkdir(parents=True)

    (archive_dir_path / "extract-test1.txt").write_text("hello1")
    (archive_dir_path / "extract-test2.txt").write_text("hello2")
    (archive_dir_path / "extract-test3.md").write_text("hello3")

    # Make an archive
    archive_dir_path = root_dir / file_name
    # The request should fail when the extension has an unnecessary prefix.
    archive_path = archive_dir_path.parent / f"{archive_dir_path.name}.{format}"
    if format == "zip":
        with zipfile.ZipFile(archive_path, mode=mode) as writer:
            for file_path in archive_dir_path.rglob("*"):
                if file_path.is_file():
                    writer.write(file_path, file_path.relative_to(root_dir))
    else:
        with tarfile.open(str(archive_path), mode=mode) as writer:
            for file_path in archive_dir_path.rglob("*"):
                if file_path.is_file():
                    writer.add(file_path, file_path.relative_to(root_dir))

    # Remove the directory
    shutil.rmtree(archive_dir_path)

    return archive_dir_path, archive_path


@pytest.mark.parametrize(
    "file_name",
    [
        ('archive'),
        ('archive.hello'),
        ('archive.tar.gz'),
    ],
)
@pytest.mark.parametrize(
    "format, mode",
    [
        ("zip", "w"),
        ("tgz", "w|gz"),
        ("tar.gz", "w|gz"),
        ("tbz", "w|bz2"),
        ("tbz2", "w|bz2"),
        ("tar.bz", "w|bz2"),
        ("tar.bz2", "w|bz2"),
        ("txz", "w|xz"),
        ("tar.xz", "w|xz"),
    ],
)
async def test_extract(jp_fetch, jp_root_dir, file_name, format, mode):
    archive_dir_path, archive_path = _create_archive_file(jp_root_dir, file_name, format, mode)

    r = await jp_fetch("extract-qzv", archive_path.relative_to(jp_root_dir).as_posix(), method="GET")
    assert r.code == 200
    assert archive_dir_path.is_dir()

    n_files = len(list(archive_dir_path.glob("*")))
    assert n_files == 3


@pytest.mark.parametrize(
    "format, mode",
    [
        ("zip", "w"),
        ("tgz", "w|gz"),
        ("tar.gz", "w|gz"),
        ("tbz", "w|bz2"),
        ("tbz2", "w|bz2"),
        ("tar.bz", "w|bz2"),
        ("tar.bz2", "w|bz2"),
        ("txz", "w|xz"),
        ("tar.xz", "w|xz"),
    ],
)
async def test_extract_failure(jp_fetch, jp_root_dir, format, mode):
    # The request should fail when the extension has an unnecessary prefix.
    prefixed_format = f"prefix{format}"
    archive_dir_path, archive_path = _create_archive_file(jp_root_dir, "extract-qzv-dir", prefixed_format, mode)

    with pytest.raises(Exception) as e:
        await jp_fetch("extract-qzv", archive_path.relative_to(jp_root_dir).as_posix(), method="GET")
    assert e.type == HTTPClientError
    assert not archive_dir_path.exists()


@pytest.mark.parametrize(
    "file_path",
    [
        ("../../../../../../../../../../tmp/test"),
        ("../test"),
    ],
)
async def test_extract_path_traversal(jp_fetch, jp_root_dir, file_path):
    unsafe_file_path = jp_root_dir / "test"
    archive_path = jp_root_dir / "test.tar.gz"
    open(unsafe_file_path, 'a').close()
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(unsafe_file_path, file_path)

    with pytest.raises(Exception) as e:
        await jp_fetch("extract-qzv", archive_path.relative_to(jp_root_dir).as_posix(), method="GET")
    assert e.type == HTTPClientError
    assert e.value.code == 400

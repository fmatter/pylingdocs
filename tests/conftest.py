import logging
import os
import pathlib
import shutil
import pytest
from pycldf import Dataset


log = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def data():
    return pathlib.Path(__file__).parent / "data"


@pytest.fixture
def working_dir(tmp_path, data):
    shutil.copyfile(data / "structure.yaml", tmp_path / "structure.yaml")
    os.chdir(tmp_path)


@pytest.fixture
def md_path(data):
    return data / "cldf" / "metadata.json"


@pytest.fixture
def dataset(md_path):
    return Dataset.from_metadata(md_path)

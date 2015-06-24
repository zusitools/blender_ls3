# coding=utf-8

import os
import io
from unittest.mock import patch

class MockFile():
  """A file for MockFS that is based on a BytesIO/StringIO object
  but does not free the buffer when close() is called."""

  def __init__(self, filename, is_binary):
    self.closed = True
    self.contents = io.BytesIO() if is_binary else io.StringIO()
    self.filename = filename

  def open(self):
    self.closed = False
    self.contents.seek(0)

  def close(self):
    self.closed = True
    self.contents.flush()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
    return True

  def read(self, count = 0):
    if self.closed:
      raise ValueError("I/O on closed file")
    return self.contents.read(count) if count != 0 else self.contents.read()

  def write(self, contents):
    if self.closed:
      raise ValueError("I/O on closed file")
    return self.contents.write(contents)

class MockFS():
  """A simple overlay file system that redirects writes to MockFiles stored in memory."""
  def __init__(self):
    self.files = {}
    self.originalOpen = open
    self.originalOsPathExists = os.path.exists

  def open(self, filename, mode):
    if "w" not in mode and filename in self.files:
      f = self.files[filename]
      f.open()
      return f

    if "w" in mode:
      mockfile = MockFile(filename, "b" in mode)
      mockfile.open()
      self.files[filename] = mockfile
      return mockfile
    else:
      return self.originalOpen(filename, mode)

  def path_exists(self, path):
    return path in self.files or self.originalOsPathExists(path)

  def start(self):
    self._open_patch = patch('builtins.open', side_effect=lambda filename, mode, encoding='UTF-8': self.open(filename, mode))
    self._open_patch.start()
    self._pathexists_patch = patch('os.path.exists', side_effect=lambda path: self.path_exists(path))
    self._pathexists_patch.start()

  def stop(self):
    self._open_patch.stop()
    self._pathexists_patch.stop()


"""Shared pytest fixtures for Commander Forge AI backend tests."""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: deck generation calls (up to 180s)")

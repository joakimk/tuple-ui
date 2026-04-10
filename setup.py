#!/usr/bin/env python3
from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="tuple-ui",
    version="1.0.0",
    description="A lightweight system tray application for controlling Tuple (pair programming tool)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Joakim",
    license="MIT",
    py_modules=["tuple_ui"],
    install_requires=[
        "PyQt6>=6.0.0",
    ],
    entry_points={
        "gui_scripts": [
            "tuple-ui=tuple_ui:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
)

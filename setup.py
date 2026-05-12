from setuptools import setup, find_packages
import os

# Read dependencies from requirements.txt
def read_requirements():
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

setup(
    name="smugmug-downloader",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "requests-oauthlib>=1.3.1",
        "rich>=13.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-bdd>=7.1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "smd=src.cli:main",
        ],
    },
    description="A Python CLI tool to download all galleries (albums) from a SmugMug account.",
    python_requires=">=3.8",
)

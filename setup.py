from setuptools import setup, find_packages

setup(
    name="papertrade-client",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "eth-account>=0.14.0",
        "mnemonic>=0.20",
        "click>=8.0",
        "httpx>=0.27",
        "rich>=13.0",
    ],
    entry_points={"console_scripts": ["papertrade=cli:cli"]},
    python_requires=">=3.10",
)

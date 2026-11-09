from setuptools import setup, find_packages

setup(
    name="dp4500",
    version="1.0.0",
    description="Python SDK for DigitalPersona (U.are.U) 4500 Fingerprint Reader",
    long_description=open("README.md").read() if open("README.md", "r") else "",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "pillow>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "dp4500=dp4500.cli:main",
        ],
    },
)

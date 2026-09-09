from setuptools import setup, find_packages

setup(
    name="openvision",
    version="0.1.0",
    description="Universal Schematic Viewer for Technology-Mapped Netlists",
    author="OpenVision Team",
    packages=find_packages(),
    package_data={
        "openvision.gui": ["logo/*.png"],
    },
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.5.0",
        "pytest>=8.0.0",
        "rich>=13.0.0",
        "pyparsing>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "openvision=openvision.cli:main",
        ],
    },
)

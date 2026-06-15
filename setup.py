"""Setup configuration for battery_limit"""

from setuptools import setup, find_packages

setup(
    name="battery-limit",
    version="0.1.0",
    description="电池限制管理工具",
    author="Developer",
    author_email="dev@example.com",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.950",
        ],
    },
)
